"""How many pitches a game, a start, and a stint actually take.

    pixi run pitches

A stint is one pitcher's continuous appearance in one game. Averaging stint
length naively gets two things wrong.

The first is that it pools two populations that have nothing to do with each
other: a start runs about 70 pitches, a relief appearance about 35, and the
pooled "47" describes nobody. Every figure here is reported by role.

The second is right-censoring. Every team's last pitcher of a game was still
on the mound when it ended -- she was never removed, so her count is a floor
rather than a finished stint. That is 50 of 141 stints, all of them relief.

Kaplan-Meier is the standard fix and is reported, but it should be read as an
upper bound rather than the answer, because the censoring here is badly
informative: a reliever entering the 7th is censored 100% of the time by
arithmetic, one entering the 4th only 18% of the time. KM treats a closer
stopped at 19 pitches as though she would have carried on like anyone else at
19 pitches, when in fact her work was finished. The honest pair of numbers is
the descriptive mean (what usage actually looks like) and the uncensored mean
(how long a stint runs when a manager is the one who ends it).

Announced-but-never-pitched starters are excluded throughout: one exists, from
the Aug 30 game, where the posted starter moved to left field before facing a
batter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.parse import OUT_DIR


def stints() -> pd.DataFrame:
    """Every real pitching appearance, flagged for censoring and entry inning."""
    pitching = (pd.read_parquet(OUT_DIR / "pitching.parquet")
                .sort_values(["game_id", "team_id", "appear_order"]))
    real = pitching[pitching["bf"] > 0].copy()

    last = real.groupby(["game_id", "team_id"])["appear_order"].transform("max")
    real["censored"] = real["appear_order"] == last

    starts = pd.read_parquet(OUT_DIR / "pitching_stints.parquet")
    entered = starts.set_index(
        ["game_id", "pitching_team_id", "pitcher_id"])["entered_inning"].to_dict()
    real["entered"] = [entered.get((g, t, p)) for g, t, p
                       in zip(real["game_id"], real["team_id"], real["player_id"])]
    real["role"] = np.where(real["is_starter"], "starter", "reliever")
    return real


def kaplan_meier(times, events) -> tuple[float, float]:
    """Restricted mean survival time, and where the curve ends."""
    t = np.asarray(times, float)
    e = np.asarray(events, bool)
    survival, area, previous = 1.0, 0.0, 0.0
    for point in np.unique(t[e]):
        at_risk = (t >= point).sum()
        removed = ((t == point) & e).sum()
        area += survival * (point - previous)
        previous = point
        survival *= 1 - removed / at_risk
    area += survival * (t.max() - previous)
    return area, survival


def describe(name: str, values: pd.Series) -> None:
    print(f"  {name:34s} n={len(values):3d}  mean {values.mean():5.1f}  "
          f"median {values.median():5.1f}  sd {values.std():4.1f}  "
          f"range {int(values.min())}-{int(values.max())}")


def main() -> None:
    pd.set_option("display.width", 240)
    real = stints()

    print("=== pitches per game ===")
    describe("both teams, one game", real.groupby("game_id")["pitches"].sum())
    describe("one team, one game", real.groupby(["game_id", "team_id"])["pitches"].sum())

    print("\n=== pitches per start ===")
    starters = real[real["is_starter"]]
    describe("starters", starters["pitches"])
    print(f"  mean {starters['ip_outs'].mean() / 3:.2f} IP of 7; longest outing "
          f"{starters['ip_outs'].max() / 3:.1f} IP; they throw "
          f"{starters['pitches'].sum() / real['pitches'].sum() * 100:.0f}% of all pitches")
    print(f"  no starter finished a game, so no start is censored "
          f"({int(starters['censored'].sum())} censored)")

    print("\n=== pitches per stint ===")
    describe("all stints pooled", real["pitches"])
    print("  -- but that pools two unrelated populations:")
    for role, block in real.groupby("role"):
        describe(f"  {role}s", block["pitches"])

    print("\n=== censoring: the game ended before the manager did ===")
    relief = real[real["role"] == "reliever"]
    print(f"  {int(real['censored'].sum())} of {len(real)} stints censored "
          f"({real['censored'].mean() * 100:.0f}%), every one of them relief\n")
    describe("relief, removed by a change", relief.loc[~relief["censored"], "pitches"])
    describe("relief, game ended first", relief.loc[relief["censored"], "pitches"])

    print("\n  censoring is not independent of stint length -- it is set by when")
    print("  she entered, which is exactly what determines how long she can go:")
    by_entry = relief.dropna(subset=["entered"])
    print(by_entry.groupby(by_entry["entered"].astype(int)).agg(
        n=("pitches", "size"), censored=("censored", "sum"),
        censor_rate=("censored", "mean"), mean_pitches=("pitches", "mean")).round(2).to_string())

    print("\n=== the two defensible answers ===")
    for label, block in (("relievers", relief), ("all stints", real)):
        area, final = kaplan_meier(block["pitches"], ~block["censored"])
        uncensored = block.loc[~block["censored"], "pitches"].mean()
        print(f"  {label}:")
        print(f"    what usage looks like (all stints)        {block['pitches'].mean():5.1f} pitches")
        print(f"    when a manager ends it (uncensored only)  {uncensored:5.1f} pitches")
        print(f"    Kaplan-Meier upper bound                  {area:5.1f} pitches "
              f"(curve reaches S={final:.2f})")


if __name__ == "__main__":
    main()
