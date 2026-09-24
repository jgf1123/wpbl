"""How much a pitcher's arm carries in a week, and what the ceiling looks like.

    pixi run workload

A per-appearance count says how hard one outing was; it says nothing about
whether a staff is being run into the ground. The unit that matters is the
week, because this league starts its pitchers roughly once every seven days and
plays about three games in that span.

Four things, in the order the argument runs:

    rest between starts   -- the cadence the rotation actually keeps
    rolling 7-day load    -- what an arm carries at each appearance
    stints per 7 days     -- how often starters and relievers actually take the mound
    per pitcher           -- span, rest, and pitches per outing, starts and relief apart
    peak per pitcher      -- her usual 7-day load, and the ceiling she reached
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

from wpbl import tables
from wpbl.usage_chart import CODES

WINDOW = 7          # days; the natural unit for a once-a-week rotation
MIN_APPEARANCES = 3  # below this a "peak" is one outing, not a workload


def appearances() -> pd.DataFrame:
    """Every real outing, with the 7-day load the pitcher was carrying.

    Every game the feed has, postseason included and TRAINING_EXCLUDED games
    too: an arm carries the pitches it threw whether or not the game is fit to
    train a model on.
    """
    pitching = tables.read("pitching", "all")
    pitching = pitching[pitching["bf"] > 0].copy()
    # The feed's count, corrected where it cut pitch strings short
    # (parse.estimate_pitch_counts): a tired arm threw the pitches either way.
    pitching["pitches"] = pitching["pitches_est"]
    pitching["date"] = pd.to_datetime(pitching["game_date"])

    # The window is INCLUSIVE of the outing being measured: the seven days
    # ending today, which is what "her load this week" means. This is why the
    # module does not reuse relievers.recent_load -- that one deliberately
    # counts only the days BEFORE a game, because it answers a different
    # question ("what was she carrying when the manager chose?"). Adding the
    # current outing to that window would silently span eight days.
    loads, contains_start, stints = [], [], []
    for row in pitching.itertuples():
        window = pitching[(pitching["person_id"] == row.person_id)
                          & (pitching["date"] > row.date - pd.Timedelta(days=WINDOW))
                          & (pitching["date"] <= row.date)]
        loads.append(float(window["pitches"].sum()))
        contains_start.append(bool(window["is_starter"].any()))
        stints.append(len(window))
    pitching["load"] = loads
    pitching["week_with_start"] = contains_start
    # Outings in the same inclusive window, including today's. A start that is
    # the only appearance in seven days is 1; a second relief outing inside
    # the window makes it 2. The window looks backward, so the first of two
    # close outings still reads as 1.
    pitching["stints_7d"] = stints
    pitching["started"] = pitching["is_starter"]
    return pitching


def rest_between_starts(pitching: pd.DataFrame) -> pd.Series:
    starts = pitching[pitching["is_starter"]].sort_values(["person_id", "date"])
    gaps = []
    for _, group in starts.groupby("person_id"):
        gaps.extend(group["date"].diff().dt.days.dropna().tolist())
    return pd.Series(gaps, dtype=float)


def rest_between_stints(pitching: pd.DataFrame) -> pd.DataFrame:
    """Days from one stint to the next, for the same pitcher.

    Calendar difference, so pitching on consecutive days is 1. The gap is
    filed under the role of the later outing: how long she had been off the
    mound when she started, or when she relieved.
    """
    rows = []
    ordered = pitching.sort_values(["person_id", "date", "game_id"])
    for _, group in ordered.groupby("person_id"):
        days = group["date"].diff().dt.days
        for started, gap in zip(group["is_starter"].iloc[1:], days.iloc[1:]):
            rows.append({"started": bool(started), "days": float(gap)})
    return pd.DataFrame(rows)


def pitcher_season(pitching: pd.DataFrame) -> pd.DataFrame:
    """One row per pitcher with enough outings to describe a workload.

    Span and the gaps between appearances are calendar days, so consecutive
    dates count as 1. Pitches per start and per relief outing are blank when
    she never pitched in that role.
    """
    rows = []
    ordered = pitching.sort_values(["person_id", "date", "game_id"])
    for person_id, group in ordered.groupby("person_id"):
        if len(group) < MIN_APPEARANCES:
            continue
        gaps = group["date"].diff().dt.days.dropna()
        starts = group.loc[group["is_starter"], "pitches"]
        relief = group.loc[~group["is_starter"], "pitches"]
        rows.append({
            "person_id": person_id,
            "pitcher": group["person_name"].iloc[-1],
            "team": group["team_name"].iloc[-1],
            "span": int((group["date"].iloc[-1] - group["date"].iloc[0]).days),
            "app": len(group),
            "gs": int(group["is_starter"].sum()),
            "gap_mean": float(gaps.mean()) if len(gaps) else float("nan"),
            "gap_median": float(gaps.median()) if len(gaps) else float("nan"),
            "p_mean": float(group["pitches"].mean()),
            "p_median": float(group["pitches"].median()),
            "s_mean": float(starts.mean()) if len(starts) else float("nan"),
            "s_median": float(starts.median()) if len(starts) else float("nan"),
            "r_mean": float(relief.mean()) if len(relief) else float("nan"),
            "r_median": float(relief.median()) if len(relief) else float("nan"),
        })
    return (pd.DataFrame(rows)
            .sort_values(["app", "pitcher"], ascending=[False, True])
            .reset_index(drop=True))


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

    print(f"\n\n=== stints in the same {WINDOW}-day window, by role of this outing ===")
    print("  counted at every appearance; the window includes today and looks back")
    for role, block in frame.assign(
            role=np.where(frame["started"], "starters", "relievers")).groupby("role"):
        counts = block["stints_7d"].value_counts().sort_index()
        bits = "  ".join(f"{int(k)}:{int(n)}" for k, n in counts.items())
        print(f"  {role:12s} n={len(block):3d}  mean {block['stints_7d'].mean():.2f}  "
              f"median {block['stints_7d'].median():.0f}   ({bits})")
    print("  both sit near 1-2 because a count is only taken on a day she pitches")

    print("\n\n=== days since her previous stint, by role of this outing ===")
    print("  consecutive days count as 1; first outing of the season has no gap")
    between = rest_between_stints(frame)
    for started, label in ((True, "starters"), (False, "relievers")):
        gaps = between.loc[between["started"] == started, "days"]
        counts = gaps.value_counts().sort_index()
        print(f"\n  {label}  n={len(gaps)}  mean {gaps.mean():.1f}  median {gaps.median():.0f}")
        print("   days  outings")
        for days, n in counts.items():
            print(f"   {int(days):4d}  {'#' * int(n)} {int(n)}")

    print(f"\n\n=== per pitcher, span and outing size "
          f"(min {MIN_APPEARANCES} appearances) ===")
    print("  span = days from first appearance to last (consecutive dates are 1)")
    print("  gaps = days between consecutive appearances; P all outings, S starts, R relief")
    print(f"  {'':4s}{'pitcher':22s}{'span':>5s}{'app':>4s}{'GS':>4s}"
          f"{'gap~':>6s}{'gap|':>6s}{'P~':>6s}{'P|':>6s}"
          f"{'S~':>6s}{'S|':>6s}{'R~':>6s}{'R|':>6s}")
    print("  ~ mean, | median; - = she never pitched in that role")

    def cell(value: float) -> str:
        return f"{'-':>6s}" if value != value else f"{value:6.1f}"

    for row in pitcher_season(frame).itertuples(index=False):
        print(f"  {CODES.get(row.team, '?'):4s}{row.pitcher:22s}"
              f"{row.span:5d}{row.app:4d}{row.gs:4d}"
              f"{cell(row.gap_mean)}{cell(row.gap_median)}"
              f"{cell(row.p_mean)}{cell(row.p_median)}"
              f"{cell(row.s_mean)}{cell(row.s_median)}"
              f"{cell(row.r_mean)}{cell(row.r_median)}")

    print(f"\n\n=== {WINDOW}-day load per pitcher "
          f"(min {MIN_APPEARANCES} appearances) ===")
    print("  usual = median of the same rolling windows as the peak")
    peak = (frame.groupby(["person_id", "person_name", "team_name"])
            .agg(apps=("load", "size"), peak=("load", "max"),
                 usual=("load", "median"), starts=("started", "sum"),
                 pitches=("pitches", "sum"), bf=("bf", "sum"),
                 outs=("ip_outs", "sum"))
            .reset_index())
    # Per batter faced and per inning are different questions. Pitches per
    # batter is efficiency at the plate; pitches per inning folds in whether
    # the defence turned those batters into outs, so a pitcher with a leaky
    # defence behind her looks worse on the second and unchanged on the first.
    peak["per_bf"] = peak["pitches"] / peak["bf"]
    peak["per_ip"] = peak["pitches"] / (peak["outs"] / 3)
    peak = peak[peak["apps"] >= MIN_APPEARANCES].sort_values(
        ["usual", "peak"], ascending=False)
    print(f"  {'':4s}{'pitcher':22s}{'app':>4s}{'GS':>4s}{'usual':>7s}{'peak':>6s}"
          f"{'P/BF':>7s}{'P/IP':>7s}")
    for row in peak.itertuples():
        print(f"  {CODES.get(row.team_name, '?'):4s}{row.person_name:22s}"
              f"{row.apps:4d}{int(row.starts):4d}{row.usual:7.0f}{row.peak:6.0f}"
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
    team_games = tables.read("team_games", "all")
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
