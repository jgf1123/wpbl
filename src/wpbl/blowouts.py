"""Half-innings big enough to count as a blowout, and what happened in them.

    pixi run blowouts [threshold]      # default 4 runs

Defining the threshold from the distribution of runs per half-inning takes one
correction. Half of all half-innings are scoreless, and that mass of zeros
drags the mean down and inflates the standard deviation, so an unconditional
mean + 1 SD lands at 2.64 -- meaning three runs, which happens in one
half-inning in six and is common rather than remarkable.

Taking mean + 1 SD *among half-innings that actually scored* -- the right
conditional, since a scoreless inning was never a blowout candidate -- gives
3.70, meaning four runs. That is also the 95th percentile of all half-innings,
happens about one time in eleven, and is a little over half of what an average
team scores in an entire seven-inning game. Four is the default here; pass a
different number to move it.

Censored half-innings are excluded from the distribution: a walk-off or a
weather-shortened game stops the moment the result is settled, so its total is
a floor rather than a count, and including them would bias the threshold down.
They are still eligible for the list itself -- a truncated inning that already
cleared the bar genuinely cleared it.
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

DEFAULT_THRESHOLD = 4
HALF_KEY = ["game_id", "batting_team_id", "inning", "half"]


def half_innings(scope: str = "default") -> pd.DataFrame:
    """Every half-inning a team actually batted, with the runs it scored.

    The threshold is fit on scope="training"; the list reports the default
    scope (see tables.read)."""
    plays = tables.read("plays", scope)
    line = tables.read("line_score", scope)
    games = tables.read("games", scope).set_index("game_id")

    batted = (plays.dropna(subset=["batting_team_id"]).groupby(HALF_KEY)
              .size().rename("plays").reset_index()
              .rename(columns={"batting_team_id": "team_id"}))
    frame = batted.merge(
        line[["game_id", "team_id", "team_name", "opponent_team_name", "inning", "runs"]],
        on=["game_id", "team_id", "inning"], how="left")

    # A half-inning that ended the game early could not run its course.
    final_play = plays.sort_values("sequence").groupby("game_id").tail(1).set_index("game_id")
    censored = []
    for row in frame.itertuples():
        game = games.loc[row.game_id]
        tail = final_play.loc[row.game_id]
        is_last = (tail["inning"] == row.inning and tail["half"] == row.half
                   and tail["batting_team_id"] == row.team_id)
        weather = "weather" in str(game.get("status", "")).lower()
        walk_off = row.half == "bottom" and game["home_score"] > game["away_score"]
        censored.append(bool(is_last and (weather or walk_off)))
    frame["censored"] = censored
    frame["date"] = frame["game_id"].map(games["game_date"])
    return frame


def thresholds(runs: pd.Series) -> None:
    scoring = runs[runs > 0]
    print(f"runs per half-inning, {len(runs)} uncensored half-innings")
    print(f"  scoreless: {(runs == 0).mean() * 100:.0f}%   "
          f"mean {runs.mean():.2f}   sd {runs.std():.2f}   max {int(runs.max())}")
    print(f"  unconditional mean+1sd = {runs.mean() + runs.std():.2f}  "
          f"-> >={int(np.ceil(runs.mean() + runs.std()))} runs, "
          f"{(runs >= np.ceil(runs.mean() + runs.std())).mean() * 100:.0f}% of half-innings")
    cut = np.ceil(scoring.mean() + scoring.std())
    print(f"  among scoring innings, mean+1sd = {scoring.mean() + scoring.std():.2f}  "
          f"-> >={int(cut)} runs, {(runs >= cut).mean() * 100:.0f}% of half-innings")
    print(f"  95th percentile of all half-innings: {np.percentile(runs, 95):.0f} runs")


def pitchers_for(plays: pd.DataFrame, people: pd.Series, row) -> str:
    """Who was on the mound while the runs scored, in order."""
    window = plays[(plays["game_id"] == row.game_id) & (plays["inning"] == row.inning)
                   & (plays["half"] == row.half)].sort_values("sequence")
    seen, names = set(), []
    for play in window.itertuples():
        name = people.get(play.pitcher_id, play.pitcher_name)
        if pd.notna(name) and name not in seen:
            seen.add(name)
            names.append(str(name).split()[-1])
    return ", ".join(names)


def main() -> None:
    pd.set_option("display.width", 250)
    threshold = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_THRESHOLD

    training = half_innings("training")
    thresholds(training.loc[~training["censored"], "runs"])
    frame = half_innings()

    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    people = pd.read_parquet(OUT_DIR / "players.parquet").set_index("player_id")["person_name"]

    big = frame[frame["runs"] >= threshold].sort_values(
        ["runs", "date"], ascending=[False, True]).copy()
    big["pitchers"] = [pitchers_for(plays, people, row) for row in big.itertuples()]

    print(f"\n\n=== {len(big)} half-innings of {threshold}+ runs ===\n")
    table = pd.DataFrame({
        "date": big["date"].astype(str).str.slice(5),
        "R": big["runs"].astype(int),
        "inn": [f'{"T" if h == "top" else "B"}{i}' for h, i in zip(big["half"], big["inning"])],
        "scored by": big["team_name"].map(CODES),
        "off": big["opponent_team_name"].map(CODES),
        "pitchers": big["pitchers"],
        "": ["(walk-off/called, cut short)" if c else "" for c in big["censored"]],
    })
    print(table.to_string(index=False))

    print(f"\nby team scoring them:")
    print(big["team_name"].map(CODES).value_counts().to_string())
    print(f"\nby team allowing them:")
    print(big["opponent_team_name"].map(CODES).value_counts().to_string())


if __name__ == "__main__":
    main()
