"""Run expectancy from a Markov chain of base-out transitions.

    pixi run markov

run_expectancy.py averages, for each of the 24 base-out states, the runs that
actually scored from there to the end of the half-inning. That is unbiased and
simple, and on 2,121 plate appearances it is also noisy: the runner-on-second
cells rest on 55 observations at nobody out, and the resulting table says a
runner on second is worth no more than a runner on first -- which the game
flatly contradicts. A runner on second scored 73% of the time with nobody out
against 51% from first; she is doubled off in the next plate appearance 0.7% of
the time against 6.9%; a single scores her 41% of the time against 2%.

This estimates the same quantity a different way. Every play is a transition
from one base-out state to another, with runs scored on the way. Fit the
transition probabilities, then solve

    RE(s) = sum_t P(s -> t) * (runs on the play + RE(t)),   RE(3 outs) = 0

so a state is worth what the states it leads to are worth. Each state still
supplies only its own transitions, but the value of everything downstream is
estimated from every play that ever reached those states, and that is where the
variance reduction comes from. Orderings then hold unless the transitions
themselves say otherwise, rather than holding by luck.

Two costs, stated plainly. The chain is memoryless -- what happens next depends
on the state alone, so a fast runner on first and a slow one are the same
runner, and a good hitter at the plate and a poor one are the same batter. And
an error in one transition row propagates to every state upstream of it, where
the cell-mean table would have kept it local.

Baserunning plays are transitions like any other, so steals, wild pitches and
pickoffs are inside these numbers rather than outside them -- which is what
makes this table usable for the running game, where the pooled table is blind.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.run_expectancy import (BASE_ORDER, HALF_KEY, MIN_SAMPLE, _base_code,
                                 damaged_halves, grid, impossible_orderings, states)

BOOTSTRAP = 1000
SEED = 20260912
CHAIN = [(bases, outs) for outs in range(3) for bases in BASE_ORDER]
SLOT = {state: i for i, state in enumerate(CHAIN)}


def transitions() -> pd.DataFrame:
    """Every play as a move between base-out states, with runs scored on it."""
    plays = tables.read("plays", "training")
    line = tables.read("line_score", "training")
    games = tables.read("games", "training").set_index("game_id")
    damaged = damaged_halves(plays, line, games)
    plays = plays.copy()
    plays["half_key"] = list(map(tuple, plays[HALF_KEY].values))
    plays = plays[~plays["half_key"].isin(damaged)]

    # The last half-inning a game has plays for may have been cut short -- a
    # walk-off, or a game called -- so its final play leads nowhere we can
    # observe. Censor that one transition instead of recording an inning that
    # ended in three outs when it did not.
    stopped = {game: block.sort_values("sequence")["half_key"].iloc[-1]
               for game, block in plays.groupby("game_id")}

    rows = []
    for key, half in plays.groupby("half_key", sort=False):
        live = [p for p in half.sort_values("sequence").itertuples() if p.outs_before < 3]
        for i, play in enumerate(live):
            if i + 1 < len(live):
                nxt = live[i + 1]
                target = SLOT[(_base_code(nxt), int(nxt.outs_before))]
            elif stopped.get(play.game_id) == key:
                continue
            else:
                target = -1                   # three outs: the absorbing state
            rows.append({"half": key,
                         "start": SLOT[(_base_code(play), int(play.outs_before))],
                         "target": target, "runs": float(play.runs_scored)})
    return pd.DataFrame(rows)


def solve(start: np.ndarray, target: np.ndarray, runs: np.ndarray) -> np.ndarray:
    """Expected runs to the end of the half-inning, one value per state."""
    n = len(CHAIN)
    visits = np.bincount(start, minlength=n).astype(float)
    scored = np.bincount(start, weights=runs, minlength=n)
    counts = np.zeros((n, n))
    moved = target >= 0
    np.add.at(counts, (start[moved], target[moved]), 1.0)
    seen = visits > 0
    probability = np.zeros((n, n))
    probability[seen] = counts[seen] / visits[seen, None]
    immediate = np.zeros(n)
    immediate[seen] = scored[seen] / visits[seen]
    return np.linalg.solve(np.eye(n) - probability, immediate)


def run_distributions(moves: pd.DataFrame, max_runs: int) -> dict:
    """Runs from each state to the end of the half-inning, as a distribution
    rather than an average: P(k more runs | state) for k = 0..max_runs, with
    anything beyond max_runs lumped into the last entry.

    The same chain as solve(), keeping the runs on each transition instead of
    only their mean:

        D(s)[k] = sum over plays from s of P(play) * D(t)[k - runs on the play]

    with D(3 outs) = certainly zero more runs. Iterated to a fixed point, which
    it reaches because every path ends in the third out. Win probability needs
    the whole distribution -- whether a team scores enough, not how many it
    expects -- which is why this exists beside solve().
    """
    n, absorb = len(CHAIN), len(CHAIN)
    start = moves["start"].to_numpy()
    target = np.where(moves["target"].to_numpy() < 0, absorb, moves["target"].to_numpy())
    runs = np.minimum(moves["runs"].to_numpy().astype(int), max_runs)
    visits = np.bincount(start, minlength=n).astype(float)
    step = np.zeros((n, n + 1, max_runs + 1))            # [from, to, runs on the play]
    np.add.at(step, (start, target, runs), 1.0)
    seen = visits > 0
    step[seen] /= visits[seen, None, None]

    dist = np.zeros((n + 1, max_runs + 1))
    dist[absorb, 0] = 1.0
    for _ in range(10_000):
        new = np.zeros_like(dist)
        new[absorb, 0] = 1.0
        for r in np.unique(runs):
            shifted = np.zeros_like(dist)                # r runs banked on the play
            shifted[:, r:] = dist[:, :max_runs + 1 - r]
            if r:
                shifted[:, max_runs] += dist[:, max_runs + 1 - r:].sum(1)
            new[:n] += step[:, :, r] @ shifted
        done = np.abs(new - dist).max() < 1e-13
        dist = new
        if done:
            break
    return {state: dist[i] for state, i in SLOT.items()}


def as_table(values: np.ndarray) -> pd.DataFrame:
    frame = pd.DataFrame(values.reshape(3, len(BASE_ORDER)).T,
                         index=BASE_ORDER, columns=[0, 1, 2])
    frame.columns.name = "outs"
    return frame


@lru_cache(maxsize=1)
def run_expectancy() -> dict:
    """The fitted table, keyed by (bases, outs). This is the run expectancy the
    rest of the repo uses -- batters, pitchers, relievers and the game
    timeline all price plays off it. Cached, so the chain is fit once per
    process rather than once per caller."""
    moves = transitions()
    values = solve(moves["start"].to_numpy(), moves["target"].to_numpy(),
                   moves["runs"].to_numpy())
    return {state: float(values[i]) for state, i in SLOT.items()}


def re_of(table: dict, bases: str, outs: int) -> float:
    """Runs still expected in the half-inning from this state; 0 once it is over."""
    return 0.0 if outs >= 3 else table[(bases, outs)]


def main() -> None:
    pd.set_option("display.width", 220)
    moves = transitions()
    start = moves["start"].to_numpy()
    target = moves["target"].to_numpy()
    runs = moves["runs"].to_numpy()
    value = solve(start, target, runs)
    table = as_table(value)

    blocks = [block.index.to_numpy() for _, block in moves.groupby("half", sort=False)]
    rng = np.random.default_rng(SEED)
    draws = []
    for _ in range(BOOTSTRAP):
        picked = np.concatenate([blocks[i] for i in rng.integers(0, len(blocks), len(blocks))])
        sample = moves.loc[picked]
        draws.append(solve(sample["start"].to_numpy(), sample["target"].to_numpy(),
                           sample["runs"].to_numpy()))
    lo, hi = np.percentile(np.array(draws), [2.5, 97.5], axis=0)

    visits = np.bincount(start, minlength=len(CHAIN))
    print(f"{len(moves)} transitions from {len(blocks)} half-innings\n")
    print("=== run expectancy, Markov chain ===")
    print(f"  value [95% interval] then transitions out of the state; "
          f"! fewer than {MIN_SAMPLE}\n")
    print(f"  {'bases':7s}" + "".join(f"{f'{o} out':>27s}" for o in range(3)))
    for bases in BASE_ORDER:
        line = f"  {bases:7s}"
        for outs in range(3):
            i = SLOT[(bases, outs)]
            thin = "!" if visits[i] < MIN_SAMPLE else " "
            line += f"{table.loc[bases, outs]:8.2f} [{lo[i]:4.2f},{hi[i]:4.2f}]{visits[i]:5d}{thin}"
        print(line)

    cells, counts, _ = grid(states(), "bases")
    cells = cells.reindex(BASE_ORDER)
    print("\n=== cell means for comparison ===")
    print(f"  {'bases':7s}" + "".join(f"{f'{o} out  cell markov    diff':>29s}" for o in range(3)))
    for bases in BASE_ORDER:
        line = f"  {bases:7s}"
        for outs in range(3):
            cell = cells.loc[bases, outs]
            markov = table.loc[bases, outs]
            line += f"{cell:14.2f}{markov:7.2f}{markov - cell:+8.2f}"
        print(line)

    print("\n=== checks ===")
    for label, frame in (("cell means", cells), ("markov", table)):
        bad = impossible_orderings(frame)
        print(f"  {label:11s} impossible orderings: {len(bad)}")
        for note in bad[:8]:
            print(f"      {note}")
    total = moves.groupby("half")["runs"].sum()
    print(f"  runs per half-inning: observed {total.mean():.3f}, "
          f"markov empty-bases {table.loc['___', 0]:.3f}, "
          f"cell-mean empty-bases {cells.loc['___', 0]:.3f}")

    print("\n=== what moving a runner is worth (the running game) ===")

    def gain(before, after, extra=0.0):
        landing = 0.0 if after[1] >= 3 else value[SLOT[after]]
        return landing + extra - value[SLOT[before]]

    for outs in range(3):
        steal2 = gain(("1__", outs), ("_2_", outs))
        caught2 = gain(("1__", outs), ("___", outs + 1))
        steal3 = gain(("_2_", outs), ("__3", outs))
        caught3 = gain(("_2_", outs), ("___", outs + 1))
        print(f"  {outs} out: steal 2nd {steal2:+.3f}, caught {caught2:+.3f}, "
              f"break-even {-caught2 / (steal2 - caught2):.0%}   |   "
              f"steal 3rd {steal3:+.3f}, caught {caught3:+.3f}, "
              f"break-even {-caught3 / (steal3 - caught3):.0%}")

    print("\n=== a single from first vs from second ===")
    print("  from second the runner scores and the batter stands on first;")
    print("  from first she reaches second or third, with nothing banked")
    for outs in range(3):
        banked = value[SLOT[("1__", outs)]] + 1.0
        to_second = value[SLOT[("12_", outs)]]
        to_third = value[SLOT[("1_3", outs)]]
        print(f"  {outs} out: single with a runner on 2nd {banked:5.2f}   "
              f"with a runner on 1st: 1st and 2nd {to_second:5.2f}, "
              f"1st and 3rd {to_third:5.2f}   difference {banked - to_second:+.2f} "
              f"and {banked - to_third:+.2f}")


if __name__ == "__main__":
    main()
