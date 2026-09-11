"""How much a pitcher's arm carries in a week, and what the ceiling looks like.

    pixi run workload

A per-appearance count says how hard one outing was; it says nothing about
whether a staff is being run into the ground. The unit that matters is the
week, because this league starts its pitchers roughly once every seven days and
plays about three games in that span.

Four things, in the order the argument runs:

    rest between starts   -- the cadence the rotation actually keeps
    rolling 7-day load    -- what an arm carries at each appearance
    peak per pitcher      -- the ceiling anyone has actually reached
    team weekly totals    -- how a staff divides ~400 pitches

The window here is inclusive of the outing being measured -- the seven days
ending today. relievers.recent_load looks deliberately similar but answers a
different question, counting only the days BEFORE a game, because availability
is about what an arm had already absorbed when the manager was choosing.

A caution on reading the ceilings. The largest weekly loads here are what the
busiest arms happened to reach across thirty games, not a limit anyone tested.
They say what has been survived for one month, which is not the same as what is
sustainable over a full season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

WINDOW = 7          # days; the natural unit for a once-a-week rotation
MIN_APPEARANCES = 3  # below this a "peak" is one outing, not a workload


def appearances() -> pd.DataFrame:
    """Every real outing, with the 7-day load the pitcher was carrying."""
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    pitching = pitching[pitching["bf"] > 0].copy()
    pitching["date"] = pd.to_datetime(pitching["game_date"])

    # The window is INCLUSIVE of the outing being measured: the seven days
    # ending today, which is what "her load this week" means. This is why the
    # module does not reuse relievers.recent_load -- that one deliberately
    # counts only the days BEFORE a game, because it answers a different
    # question ("what was she carrying when the manager chose?"). Adding the
    # current outing to that window would silently span eight days.
    loads, contains_start = [], []
    for row in pitching.itertuples():
        window = pitching[(pitching["person_id"] == row.person_id)
                          & (pitching["date"] > row.date - pd.Timedelta(days=WINDOW))
                          & (pitching["date"] <= row.date)]
        loads.append(float(window["pitches"].sum()))
        contains_start.append(bool(window["is_starter"].any()))
    pitching["load"] = loads
    pitching["week_with_start"] = contains_start
    pitching["started"] = pitching["is_starter"]
    return pitching


def rest_between_starts(pitching: pd.DataFrame) -> pd.Series:
    starts = pitching[pitching["is_starter"]].sort_values(["person_id", "date"])
    gaps = []
    for _, group in starts.groupby("person_id"):
        gaps.extend(group["date"].diff().dt.days.dropna().tolist())
    return pd.Series(gaps, dtype=float)


def main() -> None:
    pd.set_option("display.width", 250)
    frame = appearances()

    print("=== rest between consecutive starts ===")
    gaps = rest_between_starts(frame)
    counts = gaps.value_counts().sort_index()
    print("   days  starts")
    for days, n in counts.items():
        print(f"   {int(days):4d}  {'#' * n} {n}")
    print(f"\n  median {gaps.median():.0f} days; on 3 days or fewer: "
          f"{int((gaps <= 3).sum())} of {len(gaps)}")
    print("  a once-a-week rotation, not the four-days-rest convention")

    print(f"\n\n=== rolling {WINDOW}-day load, measured at every appearance ===")
    # A week containing a start is a different animal from a pure relief week.
    frame = frame.assign(kind=np.where(frame["week_with_start"],
                                       "week with a start", "relief only"))
    for kind, block in frame.groupby("kind"):
        v = block["load"]
        print(f"  {kind:20s} n={len(v):3d}  median {v.median():5.1f}  mean {v.mean():5.1f}"
              f"  90th {np.percentile(v, 90):5.1f}  max {v.max():5.1f}")

    print(f"\n\n=== peak {WINDOW}-day load reached, per pitcher "
          f"(min {MIN_APPEARANCES} appearances) ===")
    peak = (frame.groupby(["person_id", "person_name", "team_name"])
            .agg(apps=("load", "size"), peak=("load", "max"),
                 median=("load", "median"), starts=("started", "sum"),
                 pitches=("pitches", "sum"), bf=("bf", "sum"),
                 outs=("ip_outs", "sum"))
            .reset_index())
    # Per batter faced and per inning are different questions. Pitches per
    # batter is efficiency at the plate; pitches per inning folds in whether
    # the defence turned those batters into outs, so a pitcher with a leaky
    # defence behind her looks worse on the second and unchanged on the first.
    peak["per_bf"] = peak["pitches"] / peak["bf"]
    peak["per_ip"] = peak["pitches"] / (peak["outs"] / 3)
    peak = peak[peak["apps"] >= MIN_APPEARANCES].sort_values("peak", ascending=False)
    print(f"  {'':4s}{'pitcher':22s}{'app':>4s}{'GS':>4s}{'peak':>7s}{'median':>8s}"
          f"{'P/BF':>7s}{'P/IP':>7s}")
    for row in peak.itertuples():
        print(f"  {CODES.get(row.team_name, '?'):4s}{row.person_name:22s}"
              f"{row.apps:4d}{int(row.starts):4d}{row.peak:7.0f}{row.median:8.0f}"
              f"{row.per_bf:7.2f}{row.per_ip:7.1f}")
    lg_bf = peak["pitches"].sum() / peak["bf"].sum()
    lg_ip = peak["pitches"].sum() / (peak["outs"].sum() / 3)
    print()
    print(f"  league, these pitchers: {lg_bf:.2f} pitches per batter faced, "
          f"{lg_ip:.1f} per inning")
    by_role = frame.assign(role=np.where(frame["started"], "starts", "relief"))
    r = by_role.groupby("role").agg(p=("pitches", "sum"), b=("bf", "sum"),
                                    o=("ip_outs", "sum"))
    for role, row in r.iterrows():
        print(f"    {role:8s} {row['p'] / row['b']:.2f} per batter, "
              f"{row['p'] / (row['o'] / 3):.1f} per inning")

    print("\n  how many pitchers ever reached a given weekly load:")
    for threshold in (60, 80, 100, 120, 140, 160):
        n = int((peak["peak"] >= threshold).sum())
        print(f"    >= {threshold:3d} pitches in {WINDOW} days: {n:2d} of {len(peak)}")

    print("\n\n=== what a staff throws in a full three-game week ===")
    team_games = pd.read_parquet(OUT_DIR / "team_games.parquet")
    team_games["date"] = pd.to_datetime(team_games["game_date"])
    rows = []
    for team, side in frame.groupby("team_name"):
        for day in pd.date_range(side["date"].min() + pd.Timedelta(days=WINDOW - 1),
                                 side["date"].max()):
            window = side[(side["date"] > day - pd.Timedelta(days=WINDOW))
                          & (side["date"] <= day)]
            if window["game_id"].nunique() < 3:
                continue        # only weeks with a full slate are comparable
            rows.append({"team": CODES.get(team, "?"),
                         "pitches": window["pitches"].sum(),
                         "pitchers": window["person_id"].nunique(),
                         "outings": len(window)})
    weeks = pd.DataFrame(rows)
    print(weeks.groupby("team").agg(
        windows=("pitches", "size"), pitches=("pitches", "mean"),
        pitchers=("pitchers", "mean"), outings=("outings", "mean")).round(2).to_string())
    print(f"\n  overall {weeks['pitches'].mean():.0f} pitches across "
          f"{weeks['pitchers'].mean():.1f} pitchers "
          f"({weeks['pitches'].mean() / weeks['pitchers'].mean():.0f} each) "
          f"in {weeks['outings'].mean():.1f} outings")
    print("  windows overlap by a day, so they are not independent observations")


if __name__ == "__main__":
    main()
