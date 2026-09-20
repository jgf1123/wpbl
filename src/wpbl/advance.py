"""What happens on the bases, for each line of a dice card.

    pixi run advance

A card says how often a batter strikes out, walks, singles. It does not say
where the runners end up, and that is most of what a plate appearance is worth:
a single with a runner on second scores her two thirds of the time with two out
and a third of the time with none. This module estimates, for every card line
and every base-out state, the distribution over the state the next batter
inherits and the runs that scored on the way -- league-average base-running,
the same for every batter, which is the same assumption `markov.py` makes.

WHERE THE NUMBERS COME FROM

The feed gives the state before each play and the runs on it; the state after
is the next play's state, exactly as in `markov.py`. It also **names** the
runner standing on each base, which settles what would otherwise be guesswork.
A single that turns _23 into 12_ with one run could be the runner from third
scoring or the runner from second scoring, and the two are not worth the same;
the names say which woman is now on second, so nothing has to be inferred.

What the names cannot settle is which of the women who left the bases scored
and which were put out, since neither is standing anywhere afterwards. The
play's runs and outs say how many of each, and they are assigned from the lead
runner back: a trailing runner cannot score while the runner ahead of her is
thrown out at the plate. Only 5 hits in the season leave any doubt, and the
reconstruction agrees with the feed's own runs and outs on every one of them,
which is a check worth having -- an account that had to be guessed at could
not be wrong in a way the data would notice.

Advance rates are then fit per runner, per base, per out count -- the batter
included, since she too takes the extra base or is thrown out -- and composed
back into state transitions, runners drawn independently and the accounts
baseball forbids dropped. Fitting per runner rather than per state is what
makes them estimable: a double with a runner on first and nobody out has 7
plays in the season, but a runner on first when a double is hit has 44. Where
a state has MIN_CELL plays of its own, those are used instead of the
composition, so independence is only leaned on where the data is thin.

Strikeouts, free passes, home runs and outs are not composed. Their state
transitions are read off the plays directly, because the interesting variation
is not in runner advancement but in the play itself -- the double play, the
sacrifice fly, the force at second -- and a cell thin enough to be noise
(fewer than MIN_CELL plays) borrows from the same base state at other out
counts, then from the structural rule if it is still thin.

Plays that are not plate appearances -- steals, wild pitches, pickoffs -- are
kept as their own operator: from each state, how often the next play is a
running play rather than a batter, and where it leads. The chain then steps
play by play, as `markov.py` does, so the running game is inside these numbers
rather than bolted on.
"""

from __future__ import annotations

import itertools
from functools import lru_cache

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import contact
from wpbl.dice import TO_LINE
from wpbl.run_expectancy import BASE_ORDER, HALF_KEY, _base_code, damaged_halves

LINES = ["K", "FP", "HR", "1B", "2B", "ROE", "OUT"]          # the card's seven lines
STATES = [(bases, outs) for outs in range(3) for bases in BASE_ORDER]
SLOT = {state: i for i, state in enumerate(STATES)}
OVER = len(STATES)                      # the half-inning is over: three outs
MIN_CELL = 25                           # below this a cell borrows from the other out counts
HIT_BASE = {"single": 1, "reached_on_error": 1, "double": 2, "triple": 3}


def occupied(bases: str) -> list[int]:
    return [i + 1 for i, ch in enumerate(bases) if ch != "_"]


def as_bases(reached) -> str:
    held = set(reached)
    return "".join(str(b) if b in held else "_" for b in (1, 2, 3))


def forced(runners: list[int], batter_to: int) -> set[int]:
    """Runners who cannot hold: every base between the batter's and theirs is full."""
    full = set(runners) | {batter_to}
    return {r for r in runners if all(b in full for b in range(batter_to, r))}


def witnessed(before: dict, after: dict, batter: str, runs: int, outs_added: int):
    """Where each runner on base actually went, by name, and where the batter
    ended up: 0 = out, 1-3 = that base, 4 = scored.

    The feed names the runner standing on each base, so a runner who is on the
    bases before the play and after it needs no inference at all -- she is the
    same woman, and the two bases say what she did. The only thing left to
    settle is which of the women who left the bases scored and which were put
    out, and the play's runs and outs say how many of each. They are assigned
    from the lead runner back, since a trailing runner cannot score while the
    runner ahead of her is thrown out at the plate and still on the field.
    """
    where = {name: base for base, name in after.items()}
    dests, gone = {}, []
    for base in sorted(before, reverse=True):
        runner = before[base]
        if runner in where:
            dests[base] = where[runner]
        else:
            gone.append(base)
    batter_dest = where.get(batter, None)
    if batter_dest is None:
        gone.append(0)                          # the batter is out, or she scored
    else:
        dests[0] = batter_dest
    for i, base in enumerate(sorted(gone, reverse=True)):
        dests[base] = 4 if i < runs else 0
    ambiguous = len(gone) > 1 and 0 < runs < len(gone)
    return dests, ambiguous, len(gone) - runs != outs_added


@lru_cache(maxsize=1)
def plays() -> pd.DataFrame:
    """Training plays, each tagged with its card line and, for hits, its event."""
    raw = tables.read("plays", "training")
    line_score = tables.read("line_score", "training")
    games = tables.read("games", "training").set_index("game_id")
    damaged = damaged_halves(raw, line_score, games)
    frame = raw.copy()
    frame["half_key"] = list(map(tuple, frame[HALF_KEY].values))
    frame = frame[~frame["half_key"].isin(damaged)].copy()
    frame["bases"] = [_base_code(play) for play in frame.itertuples()]
    label, event = [], []
    for play in frame.itertuples():
        if play.play_kind == "plate_appearance":
            outcome = contact(play.event_type, play.narrative)
            card = TO_LINE.get(outcome, "OUT")
            label.append({"BB": "FP", "HBP": "FP"}.get(card, card))
            event.append(outcome)
        else:
            label.append("RUN")
            event.append(play.event_type)
    frame["label"] = label
    frame["event"] = event
    return frame


@lru_cache(maxsize=1)
def moves() -> pd.DataFrame:
    """Every play as a move between base-out states, with the runs on it.

    The last half-inning a game has plays for may have been cut short -- a
    walk-off, or a game called -- so its final play leads nowhere we can
    observe, and that one transition is censored rather than recorded as an
    inning that ended in three outs when it did not.
    """
    frame = plays()
    stopped = {game: block.sort_values("sequence")["half_key"].iloc[-1]
               for game, block in frame.groupby("game_id")}
    rows = []
    for key, half in frame.groupby("half_key", sort=False):
        live = [p for p in half.sort_values("sequence").itertuples() if p.outs_before < 3]
        for i, play in enumerate(live):
            if i + 1 < len(live):
                nxt = live[i + 1]
                target, target_outs = nxt.bases, int(nxt.outs_before)
            elif stopped.get(play.game_id) == key:
                continue
            else:
                target, target_outs = None, 3
            rows.append(dict(label=play.label, event=play.event, bases=play.bases,
                             outs=int(play.outs_before), t_bases=target, t_outs=target_outs,
                             runs=int(play.runs_scored),
                             before=occupants(play), after=occupants(nxt) if target else {},
                             batter=play.batter_name))
    return pd.DataFrame(rows)


def occupants(play) -> dict:
    """Who is standing on each base, by name."""
    return {base: getattr(play, field)
            for base, field in ((1, "first_base"), (2, "second_base"), (3, "third_base"))
            if isinstance(getattr(play, field), str)}


def advance_rates(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """P(destination | runner's base, outs, hit type), watching each named runner."""
    rows, ambiguous, disagree = [], 0, 0
    for play in frame[frame["event"].isin(HIT_BASE)].itertuples():
        if not isinstance(play.t_bases, str) or play.t_outs == 3:
            continue
        dests, unsure, mismatch = witnessed(play.before, play.after, play.batter,
                                            play.runs, play.t_outs - play.outs)
        ambiguous += unsure
        disagree += mismatch
        for base, dest in dests.items():
            rows.append(dict(event=play.event, outs=play.outs, base=base,
                             dest=dest, weight=1.0))
    counts = (pd.DataFrame(rows).pivot_table(index=["event", "base", "outs"], columns="dest",
                                             values="weight", aggfunc="sum", fill_value=0.0))
    return counts, {"scored or out unclear": ambiguous,
                    "runs and outs do not add up": disagree}


def rate_table(counts: pd.DataFrame) -> dict:
    """The advance rates as probabilities, pooling a thin (base, outs) cell over
    out counts. Destinations the data never shows keep probability zero."""
    pooled = counts.groupby(level=["event", "base"]).sum()
    table = {}
    for key, row in counts.iterrows():
        use = row if row.sum() >= MIN_CELL else pooled.loc[key[:2]]
        table[key] = (use / use.sum()).to_dict()
    return table


def hit_transitions(rates: dict, event: str, bases: str, outs: int) -> dict:
    """P(state the next batter inherits, runs | this state, this kind of hit).

    Each runner's destination is drawn from her own rate -- the batter included,
    since she too sometimes takes the extra base or is thrown out -- and then
    the accounts baseball forbids, passing the runner ahead or two runners on a
    base, are dropped and what is left is renormalised. Runners are taken from
    the lead back, so a trailing runner is the one held up.
    """
    runners = occupied(bases)
    least = HIT_BASE[event]
    must = forced(runners, least)
    choices = []
    for runner in [0] + runners:    # the batter is behind everyone, so she comes first
        row = rates[(event, runner, outs)]
        floor = least if runner == 0 else runner
        allowed = {dest: p for dest, p in row.items()
                   if p > 0 and (dest in (0, 4) or (dest >= floor
                                                    and not (runner in must and dest == runner)))}
        if not allowed:                         # the season never saw it; she takes the base
            allowed = {min(floor, 4): 1.0}
        choices.append([(runner, dest, p) for dest, p in allowed.items()])
    out = {}
    for combo in itertools.product(*choices):
        dests = [dest for _, dest, _ in combo]
        live = [d for d in dests if d not in (0, 4)]
        if len(set(live)) != len(live) or sorted(live) != live:
            continue
        moving = [d for d in dests if d != 0]
        if any(a > b for a, b in zip(moving, moving[1:])):
            continue
        probability = float(np.prod([p for _, _, p in combo]))
        runs = sum(d == 4 for d in dests)
        new_outs = outs + sum(d == 0 for d in dests)
        if new_outs >= 3:
            key = (OVER, runs)
        else:
            key = (SLOT[(as_bases(live), new_outs)], runs)
        out[key] = out.get(key, 0.0) + probability
    total = sum(out.values())
    return {key: p / total for key, p in out.items()}


def observed_transitions(frame: pd.DataFrame, label: str, borrow: bool = True) -> dict:
    """P(next state, runs | state) read straight off the plays with this label,
    a thin cell borrowing from the same base state at other out counts. With
    borrow off, a cell thinner than MIN_CELL is left out entirely, for callers
    that have something better to fall back on."""
    rows = frame[frame["label"] == label]
    by_cell, by_bases = {}, {}
    for (bases, outs), block in rows.groupby(["bases", "outs"]):
        by_cell[(bases, outs)] = block
    for bases, block in rows.groupby("bases"):
        by_bases[bases] = block
    out = {}
    for bases, outs in STATES:
        block = by_cell.get((bases, outs))
        if block is None or len(block) < MIN_CELL:
            if not borrow:
                continue
            borrowed = by_bases.get(bases)
            if borrowed is not None and (block is None or len(borrowed) > len(block)):
                block = borrowed                # same bases, any out count
        if block is None or len(block) == 0:
            continue
        counts = {}
        for play in block.itertuples():
            added = play.t_outs - play.outs
            if outs + added >= 3:
                key = (OVER, play.runs)         # runs that beat the third out still count
            elif not isinstance(play.t_bases, str):
                continue        # the inning ended there, so where the runners stood is unrecorded
            else:
                key = (SLOT[(play.t_bases, outs + added)], play.runs)
            counts[key] = counts.get(key, 0.0) + 1.0
        total = sum(counts.values())
        out[(bases, outs)] = {key: n / total for key, n in counts.items()}
    return out


def structural(label: str, bases: str, outs: int) -> dict:
    """The rule the play would follow if nothing unusual happened: everyone
    scores on a home run, forced runners move on a free pass, the batter is out
    and the runners hold on a strikeout or an out. Used only where the season
    has no plays of that line from that state at all."""
    runners = occupied(bases)
    if label == "HR":
        return {(SLOT[("___", outs)], len(runners) + 1): 1.0}
    if label == "FP":
        moved, pushed = [1], 0
        for runner in runners:
            if all(b in set(runners) | {1} for b in range(1, runner + 1)):
                if runner == 3:
                    pushed += 1
                else:
                    moved.append(runner + 1)
            else:
                moved.append(runner)
        return {(SLOT[(as_bases(moved), outs)], pushed): 1.0}
    if outs + 1 >= 3:
        return {(OVER, 0): 1.0}
    return {(SLOT[(bases, outs + 1)], 0): 1.0}


@lru_cache(maxsize=1)
def operators() -> dict:
    """For every card line, and for the running game, the transition out of each
    of the 24 base-out states: {(next state, runs on the play): probability}."""
    frame = moves()
    counts, notes = advance_rates(frame)
    rates = rate_table(counts)
    hit_share = (frame[frame["label"] == "2B"]["event"].value_counts(normalize=True).to_dict())
    built = {"notes": notes, "hit_share": hit_share}
    for label in LINES:
        rows = []
        if label in ("1B", "ROE", "2B"):
            events = {"1B": {"single": 1.0}, "ROE": {"reached_on_error": 1.0},
                      "2B": hit_share}[label]
            thick = observed_transitions(frame, label, borrow=False)
            for bases, outs in STATES:
                if (bases, outs) in thick:
                    rows.append(thick[(bases, outs)])    # its own plays, where it has enough
                    continue
                mixed = {}
                for event, share in events.items():
                    for key, p in hit_transitions(rates, event, bases, outs).items():
                        mixed[key] = mixed.get(key, 0.0) + share * p
                rows.append(mixed)
        else:
            seen = observed_transitions(frame, label)
            for bases, outs in STATES:
                rows.append(seen.get((bases, outs)) or structural(label, bases, outs))
        built[label] = rows
    running = observed_transitions(frame, "RUN")
    built["RUN"] = [running.get(state) or {(SLOT[state], 0): 1.0} for state in STATES]
    plays_from = frame.groupby(["bases", "outs"]).size()
    run_plays = frame[frame["label"] == "RUN"].groupby(["bases", "outs"]).size()
    share = (run_plays / plays_from).fillna(0.0)
    built["run_share"] = np.array([float(share.get(state, 0.0)) for state in STATES])
    return built


def step_matrix(card: np.ndarray, ops: dict | None = None):
    """One play, for a batter with this card: the chance of each next state and
    the runs expected on the way. With probability run_share the next play is a
    running play instead, which the batter's card has no say in."""
    ops = ops or operators()
    move = np.zeros((len(STATES), len(STATES) + 1))
    scored = np.zeros(len(STATES))
    for i, _ in enumerate(STATES):
        rate = ops["run_share"][i]
        mix = [(1.0 - rate, [(ops[line][i], card[j]) for j, line in enumerate(LINES)]),
               (rate, [(ops["RUN"][i], 1.0)])]
        for outer, parts in mix:
            for table, weight in parts:
                for (target, runs), p in table.items():
                    move[i, target] += outer * weight * p
                    scored[i] += outer * weight * p * runs
    return move, scored


def run_expectancy(card: np.ndarray) -> np.ndarray:
    """Runs still expected in the half-inning from each state, if every batter
    the rest of the way carries this card."""
    move, scored = step_matrix(card)
    within = move[:, :len(STATES)]
    return np.linalg.solve(np.eye(len(STATES)) - within, scored)


def league_card() -> np.ndarray:
    """The league's own plate appearance, as a card."""
    share = plays()
    share = share[share["label"] != "RUN"]["label"].value_counts(normalize=True)
    return np.array([float(share.get(line, 0.0)) for line in LINES])


def main() -> None:
    from wpbl import markov

    ops = operators()
    for note, n in ops["notes"].items():
        print(f"hits where {note}: {n}")
    print(f"the 2B line is {ops['hit_share']} by event")

    counts, _ = advance_rates(moves())
    rates = rate_table(counts)
    print("\nwhere a runner ends up, % (4 = scored, 0 = out on the bases)")
    shown = pd.DataFrame({key: {dest: 100 * p for dest, p in row.items()}
                          for key, row in rates.items()}).T.round(1).fillna(0.0)
    shown.index.names = ["event", "base", "outs"]
    print(shown.loc[["single", "double"]].to_string())

    mine = run_expectancy(league_card())
    theirs = markov.run_expectancy()
    table = pd.DataFrame({
        "bases": [b for b, _ in STATES], "outs": [o for _, o in STATES],
        "card chain": mine.round(3),
        "markov.py": [round(markov.re_of(theirs, b, o), 3) for b, o in STATES]})
    table["difference"] = (table["card chain"] - table["markov.py"]).round(3)
    print("\nruns expected to the end of the half-inning, league-average batter")
    print(table.to_string(index=False))
    print(f"\nlargest difference {table['difference'].abs().max():.3f} runs; "
          f"mean absolute {table['difference'].abs().mean():.3f}")


if __name__ == "__main__":
    main()
