"""How much a situation can swing the game.

Leverage here is the standard deviation of the win probabilities reachable
from a state, over the runs the batting team might still score in that
half-inning. It is ex-ante -- a property of the situation, not of what
happened -- and it folds inning, score, and base-out state into one number,
which is what lets the same index serve both the inning-start question ("how
much does the coming inning matter") and the mid-inning one.

Values are reported as an index normalised so that the mean over every
half-inning start actually played is 1.00, so "twice as important as an
average inning" reads directly off the number.

An extra inning starts with a runner already placed on second rather than
bases empty, which the index accounts for.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.parse import OUT_DIR
from wpbl.win_probability import Model, REGULATION

LEADOFF_BASES = "___"
EXTRA_LEADOFF_BASES = "_2_"


def raw_leverage(model: Model, inning: int, half: str, outs: int,
                 bases: str, diff: int) -> float:
    """Standard deviation of the win probability this half-inning can still
    produce, from the given state. `diff` is home minus away."""
    pmf = model.state[(bases, outs)]
    batting_is_home = half == "bottom"
    outcomes = []
    for runs, prob in enumerate(pmf):
        if prob == 0:
            continue
        after = diff + runs if batting_is_home else diff - runs
        if half == "bottom":
            if inning >= REGULATION:
                wp = 1.0 if after > 0 else (0.5 if after == 0 else 0.0)
            else:
                wp = model._lookup(model.top[inning + 1], after)
        elif inning > REGULATION:
            wp = model._lookup(model.extra_bottom, after)
        else:
            wp = model._lookup(model.bottom[inning], after)
        outcomes.append((prob, wp))
    mean = sum(p * w for p, w in outcomes)
    return float(sum(p * (w - mean) ** 2 for p, w in outcomes) ** 0.5)


def leadoff_bases(inning: int) -> str:
    return EXTRA_LEADOFF_BASES if inning > REGULATION else LEADOFF_BASES


def inning_leverage(model: Model, inning: int, half: str, diff: int) -> float:
    """Raw leverage of a half-inning at its start, before anyone bats."""
    return raw_leverage(model, inning, half, 0, leadoff_bases(inning), diff)


def calibrate(model: Model, half_starts: pd.DataFrame) -> float:
    """The scale factor making an average half-inning start read 1.00.

    Calibrated on half-inning starts rather than on all base-out states,
    because the index is mainly used to compare innings to one another.
    """
    values = [inning_leverage(model, row.inning, row.half, int(row.diff))
              for row in half_starts.itertuples()]
    return float(np.mean(values))


def half_inning_starts() -> pd.DataFrame:
    """One row per half-inning actually batted, with the score at its start."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["batting_team_id", "pitching_team_id"])
            .sort_values(["game_id", "sequence"]))
    first = live.groupby(["game_id", "inning", "half"], sort=False).head(1)
    return first.assign(
        diff=first["home_score_before"] - first["away_score_before"])[
        ["game_id", "inning", "half", "batting_team_id", "pitching_team_id", "diff"]]


class Leverage:
    """The index, calibrated once against the season's half-inning starts."""

    def __init__(self, model: Model | None = None):
        self.model = model or Model()
        self.scale = calibrate(self.model, half_inning_starts())

    def inning(self, inning: int, half: str, diff: int) -> float:
        return inning_leverage(self.model, inning, half, diff) / self.scale

    def state(self, inning: int, half: str, outs: int, bases: str, diff: int) -> float:
        return raw_leverage(self.model, inning, half, outs, bases, diff) / self.scale


def main() -> None:
    pd.set_option("display.width", 220)
    lev = Leverage()
    starts = half_inning_starts()
    values = np.array([lev.inning(r.inning, r.half, int(r.diff)) for r in starts.itertuples()])

    print(f"calibrated on {len(starts)} half-inning starts; raw scale {lev.scale:.4f}")
    print(f"  mean {values.mean():.3f} (1.000 by construction)   median {np.median(values):.2f}"
          f"   max {values.max():.2f}")
    print("\npercentiles:")
    for p in (10, 25, 50, 75, 90, 95, 99):
        print(f"  {p:2d}th  {np.percentile(values, p):.2f}")

    print("\nleverage of a half-inning start, by inning and score (home team's lead):")
    grid = pd.DataFrame(
        {d: {f"{'T' if h == 'top' else 'B'}{i}": round(lev.inning(i, h, d), 2)
             for i in range(1, REGULATION + 1) for h in ("top", "bottom")}
         for d in range(-4, 5)})
    print(grid.to_string())


if __name__ == "__main__":
    main()
