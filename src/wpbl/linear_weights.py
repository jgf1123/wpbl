"""Linear weights: what each kind of contact is worth, before context.

    pixi run weights
    pixi run weights --error=drop --hbp=split

The context-neutral batter rating gives every plate appearance the league's
average run value for its outcome. This prints the table of those values and
the audit trail behind it:

  1. how the feed's labels map onto contact outcomes (batters.contact), so every
     plate appearance can be seen landing somewhere -- nothing is dropped;
  2. each outcome's value with a 95% interval;
  3. a check on that value's own context.

The check. An outcome's value is its mean run value over the situations in
which it happened, and those mixes differ from outcome to outcome. The
reweighted estimate takes the outcome's mean within each base-out state and
averages those means using the league's overall mix of states instead. If the
two agree, the simple average is not being flattered by where it happened and
is the one to publish: it is the steadier of the two, because the reweighted
one leans on every thin cell. Both are shown at two resolutions -- the 12
states of the pooled run-expectancy table and the full 24 -- so the price of
finer states shows up as interval width.

Where an outcome never occurred in some state, its reweighted mean is taken
over the states where it did, and "cover" reports what share of all plate
appearances those states hold.

Intervals come from a cluster bootstrap over half-innings, the unit within
which plays are dependent. The run-expectancy table is held fixed.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from wpbl.batters import (ERROR_CHOICES, HBP_CHOICES, neutral_values, option,
                          plate_appearances)
from wpbl.run_expectancy import pool

BOOTSTRAP = 2000
SEED = 20260911

LABELS = {"home_run": "Home run", "triple": "Triple", "double": "Double",
          "single": "Single", "reached_on_error": "Reached on error",
          "free_pass": "Walk or HBP", "walk": "Walk", "hit_by_pitch": "Hit by pitch",
          "flyout": "Flyout", "groundout": "Groundout", "lineout": "Lineout",
          "popup": "Popup", "foul_out": "Foul out", "strikeout": "Strikeout",
          "out": "Other out"}


def cell_arrays(kept: pd.DataFrame, outcomes: list, states: list, key: pd.Series):
    """Per half-inning sums and counts of run value: (halves, outcomes, states)."""
    halves = np.sort(kept["half_id"].unique())
    h = np.searchsorted(halves, kept["half_id"].to_numpy())
    o = pd.Index(outcomes).get_indexer(kept["outcome"])
    s = pd.Index(states).get_indexer(key)
    sums = np.zeros((len(halves), len(outcomes), len(states)))
    counts = np.zeros_like(sums)
    np.add.at(sums, (h, o, s), kept["run_value"].to_numpy())
    np.add.at(counts, (h, o, s), 1)
    return sums, counts


def estimate(sums: np.ndarray, counts: np.ndarray):
    """Simple mean, reweighted mean and coverage from (outcomes, states) totals."""
    with np.errstate(invalid="ignore", divide="ignore"):
        simple = sums.sum(1) / counts.sum(1)
        mix = counts.sum(0) / counts.sum()
        seen = counts > 0
        means = np.divide(sums, counts, out=np.zeros_like(sums), where=seen)
        weight = np.where(seen, mix, 0.0)
        cover = weight.sum(1)
        return simple, (means * weight).sum(1) / cover, cover


def bootstrap(sums: np.ndarray, counts: np.ndarray, rng) -> np.ndarray:
    """2.5th and 97.5th percentiles, shape (2 bounds, 2 estimates, outcomes)."""
    n = sums.shape[0]
    draws = []
    for _ in range(BOOTSTRAP):
        taken = np.bincount(rng.integers(0, n, n), minlength=n).astype(float)
        simple, reweighted, _ = estimate(np.tensordot(taken, sums, axes=1),
                                         np.tensordot(taken, counts, axes=1))
        draws.append((simple, reweighted))
    return np.nanpercentile(np.array(draws), [2.5, 97.5], axis=0)


def signed(value: float) -> str:
    return f"{value:+.2f}".replace("-", "−")


def main() -> None:
    error = option("error", ERROR_CHOICES, sys.argv[1:])
    hbp = option("hbp", HBP_CHOICES, sys.argv[1:])
    frame = plate_appearances("training")

    print(f"{len(frame)} training plate appearances.  --error={error}  --hbp={hbp}")
    print("\n=== feed label -> contact outcome ===")
    for (event, outcome), n in frame.groupby(["event", "outcome"]).size().items():
        mark = "" if event == outcome else "   <- reclassified"
        print(f"   {event:18s} -> {outcome:18s}{n:5d}{mark}")
    leftover = int((frame["outcome"] == "out").sum())
    if leftover:
        print(f"  WARNING: {leftover} plays matched no contact rule and stay 'out'")

    kept, _ = neutral_values(frame, error, hbp)
    present = set(kept["outcome"])
    outcomes = [o for o in LABELS if o in present] + sorted(present - set(LABELS))
    keys = {"12": pd.Series([f"{pool(b, o)} {o}" for b, o in zip(kept["bases"], kept["outs"])],
                            index=kept.index),
            "24": kept["bases"] + " " + kept["outs"].astype(str)}

    rng = np.random.default_rng(SEED)
    results = {}
    for label, key in keys.items():
        states = sorted(key.unique())
        sums, counts = cell_arrays(kept, outcomes, states, key)
        simple, reweighted, cover = estimate(sums.sum(0), counts.sum(0))
        results[label] = {"simple": simple, "reweighted": reweighted, "cover": cover,
                          "bounds": bootstrap(sums, counts, rng),
                          "n": counts.sum(0).sum(1), "cells": (counts.sum(0) > 0).sum(1),
                          "states": len(states)}

    base = results["12"]
    order = np.argsort(-base["simple"])
    print(f"\n=== run value per outcome: simple average vs reweighted to the league's "
          f"base-out mix ===")
    print("   95% intervals from a cluster bootstrap over half-innings; cells = states "
          "in which the outcome occurred")
    print(f"   {'outcome':17s}{'n':>5s}   {'simple':>22s}   "
          f"{'reweighted, 12 states':>32s}   {'reweighted, 24 states':>32s}")
    for i in order:
        s_lo, s_hi = base["bounds"][0][0][i], base["bounds"][1][0][i]
        line = (f"   {LABELS.get(outcomes[i], outcomes[i]):17s}{int(base['n'][i]):5d}   "
                f"{base['simple'][i]:+.3f} [{s_lo:+.3f},{s_hi:+.3f}]")
        for label in ("12", "24"):
            r = results[label]
            lo, hi = r["bounds"][0][1][i], r["bounds"][1][1][i]
            line += (f"   {r['reweighted'][i]:+.3f} [{lo:+.3f},{hi:+.3f}] "
                     f"{int(r['cells'][i]):2d}/{r['states']:2d} {r['cover'][i]:4.0%}")
        print(line)

    print("\n   how far reweighting moves each value, and what it costs in precision:")
    width = base["bounds"][1][0] - base["bounds"][0][0]
    for label in ("12", "24"):
        r = results[label]
        shift = r["reweighted"] - base["simple"]
        rwidth = r["bounds"][1][1] - r["bounds"][0][1]
        outside = [LABELS.get(outcomes[i], outcomes[i]) for i in range(len(outcomes))
                   if not base["bounds"][0][0][i] <= r["reweighted"][i] <= base["bounds"][1][0][i]]
        worst = int(np.argmax(np.abs(shift)))
        print(f"   {label} states: largest shift {shift[worst]:+.3f} "
              f"({LABELS.get(outcomes[worst], outcomes[worst])}); median interval "
              f"{np.median(rwidth / width):.2f}x as wide as the simple average's; "
              f"outside the simple interval: {', '.join(outside) or 'none'}")

    print("\n=== markdown for the post (simple average) ===\n")
    print("| Outcome | Run value | Low | High | Times |")
    print("|---|---|---|---|---|")
    for i in order:
        print(f"| {LABELS.get(outcomes[i], outcomes[i])} | {signed(base['simple'][i])} | "
              f"{signed(base['bounds'][0][0][i])} | {signed(base['bounds'][1][0][i])} | "
              f"{int(base['n'][i])} |")


if __name__ == "__main__":
    main()
