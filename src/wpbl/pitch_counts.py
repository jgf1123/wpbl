"""How many pitches a game, a start, and a stint actually take.

    pixi run pitches
    pixi run pitches --by-player

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

`--by-player` adds a per-pitcher table after the league summary: total pitches,
appearances, starts, relief outings, and mean pitches per start and per relief
outing. Sorted by total pitches.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.usage_chart import CODES


def stints() -> pd.DataFrame:
    """Every real pitching appearance, flagged for censoring and entry inning.

    Every game the feed has, TRAINING_EXCLUDED games included: pitch counts
    feed pitcher workload and fatigue, which count every pitch thrown.
    """
    pitching = (tables.read("pitching", "all")
                .sort_values(["game_id", "team_id", "appear_order"]))
    real = pitching[pitching["bf"] > 0].copy()
    # The feed's count, corrected where it cut pitch strings short
    # (parse.estimate_pitch_counts).
    real["pitches"] = real["pitches_est"]

    last = real.groupby(["game_id", "team_id"])["appear_order"].transform("max")
    real["censored"] = real["appear_order"] == last

    starts = tables.read("pitching_stints", "all")
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


def by_player(real: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher: totals and role-specific mean pitch counts."""
    rows = []
    for _, group in real.groupby("person_id"):
        starts = group.loc[group["is_starter"], "pitches"]
        relief = group.loc[~group["is_starter"], "pitches"]
        rows.append({
            "tm": CODES.get(group["team_name"].iloc[-1], "?"),
            "pitcher": group["person_name"].iloc[-1],
            "pitches": int(group["pitches"].sum()),
            "app": len(group),
            "gs": int(group["is_starter"].sum()),
            "rp": int((~group["is_starter"]).sum()),
            "per_start": float(starts.mean()) if len(starts) else float("nan"),
            "per_relief": float(relief.mean()) if len(relief) else float("nan"),
        })
    return (pd.DataFrame(rows)
            .sort_values(["pitches", "pitcher"], ascending=[False, True])
            .reset_index(drop=True))


def print_by_player(real: pd.DataFrame) -> None:
    table = by_player(real)
    print("\n=== pitches by pitcher ===")
    print(f"  {'':4s}{'pitcher':21s}{'P':>5s}{'App':>5s}{'GS':>4s}{'RP':>4s}"
          f"{'/start':>8s}{'/relief':>8s}")
    for row in table.itertuples(index=False):
        per_s = f"{row.per_start:7.1f}" if row.per_start == row.per_start else f"{'-':>7s}"
        per_r = f"{row.per_relief:7.1f}" if row.per_relief == row.per_relief else f"{'-':>7s}"
        print(f"  {row.tm:4s}{row.pitcher:21s}{row.pitches:5d}{row.app:5d}"
              f"{row.gs:4d}{row.rp:4d}{per_s}{per_r}")


def main() -> None:
    pd.set_option("display.width", 240)
    by_player_flag = "--by-player" in sys.argv[1:]
    unknown = [a for a in sys.argv[1:] if a.startswith("-") and a != "--by-player"]
    if unknown:
        sys.exit(f"unknown option: {unknown[0]}")

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

    if by_player_flag:
        print_by_player(real)


if __name__ == "__main__":
    main()
