"""Expected runs from each base-out state to the end of the half-inning.

    pixi run re

Standard RE24: for every plate appearance, record the state the batter walked
into and the runs the team went on to score for the rest of that half-inning,
including runs on the play itself. Averaging over a state gives its run
expectancy.

Extra innings are included, not just regulation: an extra half-inning starts
with a runner already placed on second, nobody out, and its plate appearances
are pooled into the "_2_" (runner on 2nd) bucket alongside ordinary leadoff
doubles -- exactly the state most starved for samples otherwise, so this is
where the extra data actually helps. An extra half-inning is excluded only if
it did not run its natural course: a walk-off (the home team takes the lead
batting, ending the game before a third out is needed) or the game being
called (weather). Using either would understate how many runs a state
normally goes on to produce, since play stopped the instant the very outcome
being measured occurred -- the same reasoning already applied to the bottom of
the 7th in win_probability.py's own half-inning totals. Half-innings whose
narrative runs do not tie out to the line score are excluded too, regardless
of inning.

Read the sample sizes before the means. With 24 games this matrix is correctly
built but thinly populated, and the report prints the diagnostics that say so:
cells below a usable sample, and orderings that are logically impossible and can
therefore only be noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.parse import OUT_DIR

LAST_INNING = 7          # regulation length
MIN_SAMPLE = 50          # below this a cell's mean is not worth reading
BASE_ORDER = ["___", "1__", "_2_", "__3", "12_", "1_3", "_23", "123"]

# Adding a runner can never lower the run expectancy of a state. Each key must
# come out at or below every state it maps to, at equal outs.
DOMINATED_BY = {
    "___": ["1__", "_2_", "__3"], "1__": ["12_", "1_3"], "_2_": ["12_", "_23"],
    "__3": ["1_3", "_23"], "12_": ["123"], "1_3": ["123"], "_23": ["123"],
}


def _base_code(play) -> str:
    return (("1" if pd.notna(play.first_base) else "_")
            + ("2" if pd.notna(play.second_base) else "_")
            + ("3" if pd.notna(play.third_base) else "_"))


def incomplete_extra_halves(games: pd.DataFrame, plays: pd.DataFrame) -> set[tuple]:
    """Half-inning keys, matching the (game_id, batting_team_id, inning, half)
    layout used elsewhere here, for extra-inning halves that did not run their
    natural course.

    Regulation is untouched by this -- the bottom of the 7th has its own,
    separate handling where it already lived (win_probability.py excludes it
    from the half-inning total for the same underlying reason: it is only
    played when the home team is not already ahead, and it stops the instant
    a go-ahead run scores). Only extra innings are checked here.

    An extra half-inning's own natural end is: the top always completes (nothing
    can end the game during the visiting team's turn), and the bottom completes
    unless the home team takes the lead batting. Both are detectable from the
    game's own recorded result without needing to trace outs play by play: a
    half stopped early is, by construction, the very last half-inning the game
    has any plays for -- if the game continued, something must have followed
    it and it therefore ran its course.
    """
    incomplete = set()
    for game_id, game_plays in plays.groupby("game_id"):
        extra = game_plays[game_plays["inning"] > LAST_INNING]
        if extra.empty:
            continue
        game = games.loc[game_id]
        last = game_plays.sort_values("sequence").iloc[-1]
        last_inning, last_half = int(last["inning"]), last["half"]
        if last_inning <= LAST_INNING:
            continue
        called = "weather" in str(game.get("status", "")).lower()
        walked_off = last_half == "bottom" and game["home_score"] > game["away_score"]
        if called or walked_off:
            incomplete.add((game_id, last["batting_team_id"], last_inning, last_half))
    return incomplete


def states() -> pd.DataFrame:
    """One row per plate appearance: the state faced, and runs scored from it on."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    line = pd.read_parquet(OUT_DIR / "line_score.parquet")
    games = pd.read_parquet(OUT_DIR / "games.parquet").set_index("game_id")
    plays = plays.copy()

    key = ["game_id", "batting_team_id", "inning", "half"]
    damaged = set(map(tuple, plays.loc[plays["play_kind"].isin(
        ["plate_appearance_unknown", "empty"]), key].values))
    narrative = plays.groupby(key)["runs_scored"].sum().rename("narrative").reset_index()
    scored = line.groupby(["game_id", "team_id", "inning"])["runs"].sum().rename("line").reset_index()
    merged = narrative.merge(scored, left_on=["game_id", "batting_team_id", "inning"],
                             right_on=["game_id", "team_id", "inning"])
    damaged |= set(map(tuple, merged.loc[merged["narrative"] != merged["line"], key].values))
    damaged |= incomplete_extra_halves(games, plays)

    plays["half_key"] = list(map(tuple, plays[key].values))
    plays = plays[~plays["half_key"].isin(damaged)]

    rows = []
    for _, half in plays.groupby("half_key"):
        half = half.sort_values("sequence")
        total = half["runs_scored"].sum()
        already = 0
        for play in half.itertuples():
            if play.play_kind == "plate_appearance":
                rows.append((_base_code(play), int(play.outs_before), total - already,
                             play.inning, play.half))
            already += play.runs_scored
    frame = pd.DataFrame(rows, columns=["bases", "outs", "runs_rest", "inning", "half"])
    frame.attrs["half_innings"] = plays["half_key"].nunique()
    frame.attrs["excluded"] = len(damaged)
    return frame


def grid(frame: pd.DataFrame, index: str, order=None):
    mean = frame.pivot_table(index=index, columns="outs", values="runs_rest", aggfunc="mean")
    count = frame.pivot_table(index=index, columns="outs", values="runs_rest", aggfunc="size")
    sd = frame.pivot_table(index=index, columns="outs", values="runs_rest", aggfunc="std")
    if order:
        mean, count, sd = mean.reindex(order), count.reindex(order), sd.reindex(order)
    return mean, count, 1.96 * sd / np.sqrt(count)


def impossible_orderings(mean: pd.DataFrame) -> list[str]:
    """Relationships that must hold in any real run environment. Any that fail
    are measuring sampling noise, not baseball."""
    broken = []
    for base in mean.index:
        for outs in (0, 1):
            if mean.loc[base, outs] < mean.loc[base, outs + 1]:
                broken.append(f"{base}: {outs} out ({mean.loc[base, outs]:.2f}) "
                              f"below {outs + 1} out ({mean.loc[base, outs + 1]:.2f})")
    for base, better in DOMINATED_BY.items():
        for state in better:
            for outs in (0, 1, 2):
                if mean.loc[state, outs] < mean.loc[base, outs]:
                    broken.append(f"{outs} out: {state} ({mean.loc[state, outs]:.2f}) "
                                  f"below {base} ({mean.loc[base, outs]:.2f})")
    return broken


def pool(bases: str) -> str:
    if bases == "___":
        return "bases empty"
    if bases == "1__":
        return "runner on 1st only"
    if bases == "123":
        return "bases loaded"
    return "scoring position"


POOL_ORDER = ["bases empty", "runner on 1st only", "scoring position", "bases loaded"]


def main() -> None:
    pd.set_option("display.width", 250)
    frame = states()
    print(f"{len(frame)} plate appearances across {frame.attrs['half_innings']} half-innings "
          f"({frame.attrs['excluded']} half-innings excluded for data loss)\n")

    mean, count, ci = grid(frame, "bases", BASE_ORDER)
    print("=== expected runs, rest of inning ===")
    print(mean.round(2).to_string())
    print("\n=== sample size ===")
    print(count.astype(int).to_string())
    print("\n=== 95% confidence interval, +/- ===")
    print(ci.round(2).to_string())

    thin = int((count < MIN_SAMPLE).sum().sum())
    broken = impossible_orderings(mean)
    print(f"\ncells with fewer than {MIN_SAMPLE} observations: {thin} of 24")
    print(f"logically impossible orderings: {len(broken)}")
    for line in broken:
        print(f"   {line}")

    frame = frame.assign(pooled=frame["bases"].map(pool))
    pmean, pcount, pci = grid(frame, "pooled", POOL_ORDER)
    print("\n\n=== pooled (usable at this sample size) ===")
    print(pmean.round(2).to_string())
    print("\n=== sample size ===")
    print(pcount.astype(int).to_string())
    print("\n=== 95% confidence interval, +/- ===")
    print(pci.round(2).to_string())

    print("\n\n=== by outs alone ===")
    outs = frame.groupby("outs")["runs_rest"].agg(["mean", "size", "std"])
    outs["ci"] = 1.96 * outs["std"] / np.sqrt(outs["size"])
    print(outs[["mean", "size", "ci"]].round(3).to_string())

    empty = mean.loc["___", 0]
    print(f"\nThis league scores {empty:.2f} runs per half-inning from bases empty, nobody out "
          f"-- roughly double a major-league environment, so an MLB run-expectancy\n"
          f"table would be badly wrong here.")


if __name__ == "__main__":
    main()
