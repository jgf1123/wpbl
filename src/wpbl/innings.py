"""Runs scored and allowed per inning, by team.

    pixi run innings

The 8th is excluded: it is a tiebreaker inning played with a runner already on
second, so its runs are not comparable to a normal inning.

The denominator is half-innings a team actually came to bat, taken from the
play-by-play -- not games played. The line score records a 0 for the bottom of
the last inning even when the home team was ahead and never batted, and
averaging those 13 phantom zeros would understate late scoring.
"""

from __future__ import annotations

import pandas as pd

from wpbl.parse import OUT_DIR

LAST_INNING = 7   # the 8th is the tiebreaker inning


def opportunities() -> pd.DataFrame:
    """One row per half-inning a team actually batted, with the runs it scored."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    line = pd.read_parquet(OUT_DIR / "line_score.parquet")

    batted = (plays.dropna(subset=["batting_team_id"])
              .groupby(["game_id", "batting_team_id", "inning"]).size()
              .rename("plays").reset_index()
              .rename(columns={"batting_team_id": "team_id"}))
    frame = batted.merge(
        line[["game_id", "team_id", "team_name", "inning", "runs",
              "opponent_team_id", "opponent_team_name"]],
        on=["game_id", "team_id", "inning"], how="left")
    return frame[frame["inning"] <= LAST_INNING]


def by_inning(frame: pd.DataFrame, team_col: str):
    mean = frame.pivot_table(index=team_col, columns="inning", values="runs", aggfunc="mean")
    count = frame.pivot_table(index=team_col, columns="inning", values="runs", aggfunc="size")
    overall = frame.groupby(team_col)["runs"].sum() / frame.groupby(team_col).size()
    mean = mean.round(2)
    mean["1-7"] = overall.round(2)
    # Innings 1-6 are the clean comparison: every team bats in all of them.
    early = frame[frame["inning"] < LAST_INNING]
    mean["1-6"] = (early.groupby(team_col)["runs"].sum()
                   / early.groupby(team_col).size()).round(2)
    return mean, count


def main() -> None:
    pd.set_option("display.width", 240)
    frame = opportunities()

    scored, scored_n = by_inning(frame, "team_name")
    against = frame.rename(columns={"team_name": "batting_team",
                                    "opponent_team_name": "team_name"})
    allowed, allowed_n = by_inning(against, "team_name")

    print("=== runs SCORED per inning (mean over innings actually batted) ===")
    print(scored.to_string())
    print("\n    innings batted:")
    print(scored_n.to_string())

    print("\n=== runs ALLOWED per inning ===")
    print(allowed.to_string())
    print("\n    innings faced:")
    print(allowed_n.to_string())

    print("\n=== league, by inning ===")
    league = frame.groupby("inning")["runs"].agg(["mean", "sum", "size"]).round(2)
    league.columns = ["mean", "runs", "half_innings"]
    print(league.to_string())

    dropped = 48 * LAST_INNING - len(frame)
    print(f"\n{len(frame)} half-innings counted; {dropped} never batted "
          f"(home team already ahead, or a weather-shortened game).")


if __name__ == "__main__":
    main()
