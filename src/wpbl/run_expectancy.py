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
# Two separate monotonicities have to hold, and checking only the first misses
# most of the breakage. Adding a runner can never lower a state's run
# expectancy: each key must come out at or below every state it maps to, at
# equal outs.
DOMINATED_BY = {
    "___": ["1__", "_2_", "__3"], "1__": ["12_", "1_3"], "_2_": ["12_", "_23"],
    "__3": ["1_3", "_23"], "12_": ["123"], "1_3": ["123"], "_23": ["123"],
}

# Advancing a runner cannot lower it either -- same runners, each at least as
# far along and at least one further on. That is a different relation from
# adding one, and nothing above captures it: 1__ -> _2_ keeps one runner and
# moves her up, so neither state contains the other.
ADVANCES_TO = {
    "1__": ["_2_", "__3"], "_2_": ["__3"],
    "12_": ["1_3", "_23"], "1_3": ["_23"],
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
    for cluster, (_, half) in enumerate(plays.groupby("half_key")):
        half = half.sort_values("sequence")
        total = half["runs_scored"].sum()
        already = 0
        for play in half.itertuples():
            if play.play_kind == "plate_appearance":
                rows.append((_base_code(play), int(play.outs_before), total - already,
                             play.inning, play.half, cluster))
            already += play.runs_scored
    frame = pd.DataFrame(rows, columns=["bases", "outs", "runs_rest", "inning", "half",
                                        "half_id"])
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


BOOTSTRAP = 4000
BOOTSTRAP_SEED = 20260906


def bootstrap_grid(frame: pd.DataFrame, index: str, order=None):
    """Percentile intervals from resampling half-innings, not plate appearances.

    Two reasons the textbook 1.96*sd/sqrt(n) interval is wrong here. The runs
    a state goes on to produce are heavily right-skewed and pile up on zero,
    so a symmetric normal interval misplaces both ends and can reach below
    zero. More seriously, plate appearances in the same half-inning all
    inherit that half-inning's remaining runs, so they are not independent
    observations: eight of them from one big inning carry roughly one
    inning's worth of information, not eight. Resampling whole half-innings
    keeps that correlation intact and widens the intervals to something
    honest.
    """
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    clusters = frame["half_id"].to_numpy()
    unique = np.unique(clusters)
    by_cluster = {c: frame.index[clusters == c].to_numpy() for c in unique}

    cells = frame.groupby([index, "outs"]).size().index
    draws = {cell: np.empty(BOOTSTRAP) for cell in cells}
    for b in range(BOOTSTRAP):
        picked = rng.choice(unique, size=len(unique), replace=True)
        rows = np.concatenate([by_cluster[c] for c in picked])
        sample = frame.loc[rows]
        means = sample.groupby([index, "outs"])["runs_rest"].mean()
        for cell in cells:
            draws[cell][b] = means.get(cell, np.nan)

    lo = pd.Series({cell: np.nanpercentile(v, 2.5) for cell, v in draws.items()})
    hi = pd.Series({cell: np.nanpercentile(v, 97.5) for cell, v in draws.items()})
    lo = lo.unstack()
    hi = hi.unstack()
    if order:
        lo, hi = lo.reindex(order), hi.reindex(order)
    return lo, hi


def impossible_orderings(mean: pd.DataFrame) -> list[str]:
    """Every ordering the game's own logic forbids: more outs worth more runs,
    an added runner worth less, or an advanced runner worth less."""
    broken = []
    for bases in mean.index:
        for fewer, more in ((0, 1), (1, 2)):
            if mean.loc[bases, more] > mean.loc[bases, fewer]:
                broken.append(f"outs:      {bases} {fewer} out ({mean.loc[bases, fewer]:.2f})"
                              f" below {more} out ({mean.loc[bases, more]:.2f})")
    for outs in mean.columns:
        for base, richer in DOMINATED_BY.items():
            for other in richer:
                if mean.loc[other, outs] < mean.loc[base, outs]:
                    broken.append(f"added runner: {outs} out, {other} "
                                  f"({mean.loc[other, outs]:.2f}) below {base} "
                                  f"({mean.loc[base, outs]:.2f})")
        for base, ahead in ADVANCES_TO.items():
            for other in ahead:
                if mean.loc[other, outs] < mean.loc[base, outs]:
                    broken.append(f"advanced runner: {outs} out, {base} "
                                  f"({mean.loc[base, outs]:.2f}) -> {other} "
                                  f"({mean.loc[other, outs]:.2f})")
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


def interval_table(mean, lo, hi, count, order) -> str:
    """One cell per state: the estimate with its interval and sample size."""
    header = f"{'state':20s}" + "".join(f"{str(o) + ' out':>28s}" for o in (0, 1, 2))
    out = [header]
    for row in order:
        cells = [f"{mean.loc[row, o]:5.2f} [{lo.loc[row, o]:4.2f}, {hi.loc[row, o]:4.2f}]"
                 f" n={int(count.loc[row, o]):4d}" for o in (0, 1, 2)]
        out.append(f"{row:20s}" + "  ".join(cells))
    return chr(10).join(out)



def main() -> None:
    pd.set_option("display.width", 250)
    frame = states()
    print(f"{len(frame)} plate appearances across {frame.attrs['half_innings']} half-innings "
          f"({frame.attrs['excluded']} half-innings excluded for data loss)\n")

    mean, count, ci = grid(frame, "bases", BASE_ORDER)
    lo, hi = bootstrap_grid(frame, "bases", BASE_ORDER)
    print("=== RE24: expected runs from a state to the end of the half-inning ===")
    print(f"    estimate [95% interval, {BOOTSTRAP} cluster-bootstrap resamples]")
    print()
    print(interval_table(mean, lo, hi, count, BASE_ORDER))

    thin = int((count < MIN_SAMPLE).sum().sum())
    broken = impossible_orderings(mean)
    print(f"\ncells with fewer than {MIN_SAMPLE} observations: {thin} of 24")
    print(f"logically impossible orderings: {len(broken)}")
    for line in broken:
        print(f"   {line}")

    frame = frame.assign(pooled=frame["bases"].map(pool))
    pmean, pcount, pci = grid(frame, "pooled", POOL_ORDER)
    plo, phi = bootstrap_grid(frame, "pooled", POOL_ORDER)
    print()
    print()
    print("=== pooled into four groups (usable at this sample size) ===")
    print(interval_table(pmean, plo, phi, pcount, POOL_ORDER))

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
