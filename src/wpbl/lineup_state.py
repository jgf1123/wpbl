"""Which summary of the base-out state says most about the fourth batter's PA?

    pixi run python -m wpbl.lineup_state

Her contribution is the run value of her plate appearance: runs scored during it
plus the change in run expectancy (RE24 from markov.py; three outs = 0), for the
PAs she actually takes. A state summary is informative to the extent that knowing
it, before her PA, pins down that run value: eta-squared = between-state variance
/ total variance. Compared: (runners, outs), (lead runner's base, outs), the full
24 base-out states (ceiling), and outs alone / nothing as floors. Also the same for
the two parts of a run value, runs scored and outs made.
"""
from __future__ import annotations

import os
for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from wpbl import markov
from wpbl.lineup_start import LINEUPS, build, propagate

RE = markov.run_expectancy()


def re_of(outs: int, bases: str) -> float:
    return 0.0 if outs >= 3 else markov.re_of(RE, bases, outs)


def lead(bases: str) -> str:
    return "none" if bases == "___" else "3rd" if bases[2] != "_" else "2nd" if bases[1] != "_" else "1st"


SUMMARIES = {
    "nothing": lambda o, b: 0,
    "outs": lambda o, b: o,
    "lead runner only": lambda o, b: lead(b),
    "scoring position (y/n), outs": lambda o, b: (o, lead(b) in ("2nd", "3rd")),
    "(runners, outs)": lambda o, b: (o, b.count("1") + b.count("2") + b.count("3")),
    "(lead runner base, outs)": lambda o, b: (o, lead(b)),
    "full base-out state": lambda o, b: (o, b),
}


def rows_for(label: str) -> pd.DataFrame:
    nine, order, cards, steals, _ = build(label)
    pairs = defaultdict(float)
    propagate(order, cards, steals, pairs)
    rows = []
    for (before, after), w in pairs.items():
        o0, b0, r0 = before
        if after[0] == "over":
            o1, b1, r1 = 3, "___", after[1]
        else:
            o1, b1, r1 = after
        runs = r1 - r0
        rows.append(dict(w=w, outs=o0, bases=b0, runs=runs, made=o1 - o0,
                         value=runs + re_of(o1, b1) - re_of(o0, b0)))
    frame = pd.DataFrame(rows)
    frame["w"] /= frame["w"].sum()
    return frame


def eta2(frame: pd.DataFrame, group, column: str) -> float:
    w, y = frame["w"].to_numpy(), frame[column].to_numpy()
    mean = (w * y).sum()
    total = (w * (y - mean) ** 2).sum()
    keys = [str(group(o, b)) for o, b in zip(frame["outs"], frame["bases"])]
    means = pd.Series(w * y).groupby(keys).sum() / pd.Series(w).groupby(keys).sum()
    fitted = np.array([means[k] for k in keys])
    return float((w * (fitted - mean) ** 2).sum() / total)


def main() -> None:
    pd.set_option("display.width", 200)
    labels = sys.argv[1:] or list(LINEUPS)
    out = {name: [] for name in SUMMARIES}
    for label in labels:
        frame = rows_for(label)
        print(f"\n===== {label}: P(has a 4th PA) handled separately; run value of her PA "
              f"averages {np.average(frame['value'], weights=frame['w']):+.3f} runs "
              f"(sd {np.sqrt(np.average((frame['value'] - np.average(frame['value'], weights=frame['w'])) ** 2, weights=frame['w'])):.3f})")
        table = pd.DataFrame({name: {col: eta2(frame, g, col) for col in ("value", "runs", "made")}
                              for name, g in SUMMARIES.items()}).T
        print((100 * table).round(1).rename(columns={"value": "run value", "runs": "runs scored",
                                                     "made": "outs made"}).to_string())
        for name in SUMMARIES:
            out[name].append(table.loc[name, "value"])
        if label == labels[0]:
            for name in ("(runners, outs)", "(lead runner base, outs)"):
                g = SUMMARIES[name]
                keys = [str(g(o, b)) for o, b in zip(frame["outs"], frame["bases"])]
                agg = frame.assign(k=keys).groupby("k").apply(
                    lambda d: pd.Series({"P(state)": d["w"].sum(),
                                         "run value": np.average(d["value"], weights=d["w"]),
                                         "runs scored": np.average(d["runs"], weights=d["w"]),
                                         "outs made": np.average(d["made"], weights=d["w"])}),
                    include_groups=False)
                print(f"\n  {label}: given {name}, her PA on average"); print(agg.round(3).to_string())
    print("\n===== run-value eta-squared (%) across lineups")
    print((100 * pd.DataFrame(out, index=labels)).round(1).to_string())


if __name__ == "__main__":
    main()
