"""Context-neutral runs per plate appearance for every printed dice card.

    pixi run card-runs
    pixi run card-runs --team BOS
    pixi run card-runs --csv card_runs.csv

Each printed card meets the league-average opponent on the d100, cell for cell,
and the half-inning is played from empty bases by the game's own rules
(engine.apply_line, the d12 enumerated, running plays at 6 in 100). The figure
is E[runs per half-inning] / E[plate appearances per half-inning], solved
exactly, not sampled.

  batters   her card against the league pitcher's season card: runs per PA in
            an inning that she bats all of
  pitchers  each column, fresh / fading / gassed, against the league batter:
            runs per batter faced. `avg` weights the columns by how often play
            reaches them (dice.COLUMN_SHARE)

The league against itself is the reference line (0.2065 on v0.6.0). A batter
above it and a pitcher below it are better than average. A batter's figure is
for nine of her in a row, so it spreads a little wider than her value inside a
real lineup would.

Reads the printed CSVs in data/dice/, so it rates the cards the game plays,
rounding included. PA 0 marks a generic batter card.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from wpbl import engine
from wpbl.dice import COLUMN_SHARE
from wpbl.play_wp import (B_SPAN, CARD_LINES, DICE_DIR, P_SPAN, STATES, FixedDie, faces,
                          league_table, state_index)

LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
RUN = 0.06                                   # running-play faces per d100 roll
COLUMNS = ("fresh", "fading", "gassed")


def runs_per_pa(outcome):
    """outcome(outs, bases) -> [(prob, line)], summing to 1 - RUN."""
    n = len(STATES)
    Q = np.zeros((n, n))                     # transitions that stay in the half-inning
    runs = np.zeros(n)                       # expected runs per roll, by state
    pa = np.zeros(n)                         # expected plate appearances ended per roll
    for outs, bases in STATES:
        i = state_index(outs, bases)
        b, r = engine.advance_all(bases) if any(bases) else (bases, 0)
        Q[i, state_index(outs, b)] += RUN
        runs[i] += RUN * r                   # a run on a running play stands
        for p, line in outcome(outs, bases):
            dies = range(12) if line in ("1B", "OUT") else [0]
            for d in dies:
                q = p / len(dies)
                nb, made, r = engine.apply_line(line, bases, outs, FixedDie(d))
                pa[i] += q
                if outs + made < 3:          # runs on the third out do not count
                    Q[i, state_index(outs + made, nb)] += q
                    runs[i] += q * r
    visits = np.linalg.inv(np.eye(n) - Q)[state_index(0, (False, False, False))]
    return float(visits @ runs) / float(visits @ pa)


def from_shares(shares):
    """A PA distribution over LINES (any scale) as the 94 non-running cells."""
    s = np.asarray(shares, float)
    pairs = list(zip(s / s.sum() * (1 - RUN), LINES))
    return lambda outs, bases: pairs


def from_table(table):
    """A Table's 94 non-running faces as [(prob, line)]."""
    counts = pd.Series([l for l in map(table.read, range(100)) if l != "RUN"]).value_counts()
    pairs = [(c / 100, l) for l, c in counts.items()]
    return lambda outs, bases: pairs


def read(name):
    return pd.read_csv(DICE_DIR / f"cards_{name}.csv", comment="#", dtype=str)


def batters(lg):
    rows = []
    for _, r in read("batters").iterrows():
        table = engine.Table.from_lines(lg.p_line, faces(r, CARD_LINES, "", B_SPAN))
        rows.append({"player": r["player"], "team": r["team"], "position": r["position"],
                     "PA": int(r["PA"]), "runs/PA": runs_per_pa(from_table(table))})
    return pd.DataFrame(rows)


def pitchers(lg):
    rows = []
    for _, r in read("pitchers").iterrows():
        row = {"player": r["player"], "team": r["team"], "stamina": int(r["stamina"]),
               "BF": int(r["BF"])}
        for col in COLUMNS:
            table = engine.Table.from_lines(faces(r, CARD_LINES, f"{col} ", P_SPAN), lg.b_line)
            row[col] = runs_per_pa(from_table(table))
        row["avg"] = sum(COLUMN_SHARE[c] * row[c] for c in COLUMNS)
        rows.append(row)
    return pd.DataFrame(rows)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="card-runs")
    ap.add_argument("--team", default=None, help="BOS, LAQ, NYH or SFF")
    ap.add_argument("--csv", default=None, help="also write both tables to this file")
    a = ap.parse_args(sys.argv[1:] if argv is None else argv)
    lg = league_table()
    league = runs_per_pa(from_table(lg))
    version = (DICE_DIR / "cards_batters.csv").read_text(encoding="utf-8").split(" -- ")[1].split(",")[0]
    B, P = batters(lg), pitchers(lg)
    if a.team:
        B, P = B[B["team"] == a.team], P[P["team"] == a.team]
    pd.set_option("display.width", 200)
    fmt = lambda x: f"{x:.3f}"
    print(f"Context-neutral runs per PA, cards {version}. League against itself: {league:.4f}")
    print(f"\nBATTERS vs the league pitcher (higher is better; PA 0 = generic card)")
    print(B.sort_values(["team", "runs/PA"], ascending=[True, False])
          .to_string(index=False, float_format=fmt))
    print(f"\nPITCHERS vs the league batter, per batter faced (lower is better)")
    print(f"avg = {' + '.join(f'{COLUMN_SHARE[c]:.3f} {c}' for c in COLUMNS)}")
    print(P.sort_values(["team", "avg"]).to_string(index=False, float_format=fmt))
    if a.csv:
        out = pd.concat([B.assign(side="batter").rename(columns={"runs/PA": "avg"}),
                         P.assign(side="pitcher").rename(columns={"BF": "PA"})], ignore_index=True)
        out.insert(0, "league", league)
        out.to_csv(a.csv, index=False)
        print(f"\nwrote {a.csv}")


if __name__ == "__main__":
    main()
