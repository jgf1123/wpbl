"""Play the dice game: one d100 and one d12 resolve a plate appearance.

    pixi run engine

This is the game as a player would run it, not a model of it. Every number it
uses is printed on a card or in the spec's tables, and every random choice is a
die roll against those tables. That is the point: section 9 of the spec asks
whether the printed game reproduces the league, and only a thing that plays by
the printed rules can answer.

THE TABLE (spec section 4)

    00-32  read the PITCHER's card      33 cells
    33-36  double                        4 cells
    37-38  reached on error              2 cells
    39-44  running play                  6 cells   advance everyone, ROLL AGAIN
    45-99  read the BATTER's card       55 cells

WHERE THE RUNNERS GO (spec section 2, and analysis/dice/advance rates)

Fixed per line, which is the spec's design rule: 2,663 plate appearances cannot
support runner-by-runner rules, so each line moves the runners one way, with one
variant where the data shows a real coin flip.

    K            batter out, runners hold
    BB, HBP      batter to 1st, forced runners advance one
    HR           everybody scores
    1B           batter to 1st, runner from 3rd scores, runner from 1st to 2nd;
                 the runner from 2nd SCORES on a Single+ and stops at 3rd
                 otherwise -- 42% with 0-1 out, always with 2 outs (the coin flip)
    2B           batter to 2nd, runners from 2nd and 3rd score, runner from 1st
                 to 3rd
    ROE          batter to 1st, every runner advances one
    OUT          a d12 picks the flavour, read per force state (section 8)
    running play every runner advances one, then roll again

The out flavours use the same move() the coverage test used, so the game and the
94%-of-plays check are running the same rules rather than two readings of them.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BAND_CELLS, BAND_START, BAT_START, B_CELLS, RUN_START,
                       PRINT_ORDER, P_CELLS, arrange, cards, league_card,
                       line_weights, played_lines, plate_appearances, to_cells)

BASE_ORDER = ["___", "1__", "_2_", "__3", "12_", "1_3", "_23", "123"]
INNINGS = 7                        # WPBL plays seven (36 of 39 training games;
                                   # one went 6, two went 8)

# --- the single, off the same d12 -------------------------------------------
# "+" means what it means on B / F / FB: EVERY runner takes the extra base. The
# middle level needs its own mark because only the lead runner moves up.
#
#   Single    runner from 2nd -> 3rd,   runner from 1st -> 2nd
#   Single.   runner from 2nd SCORES,   runner from 1st -> 2nd
#   Single+   runner from 2nd SCORES,   runner from 1st -> 3rd
#
# The three levels are one event, not two independent ones: in 103 singles with
# runners on 1st and 2nd, the runner from 1st reached 3rd in 0 of the 47 where
# the runner from 2nd held, and 21 of the 56 where she scored.
#   (first bullet face, first plus face) on a d12 read 1-12
SINGLE_D12 = {0: (8, 11), 1: (8, 11), 2: (5, 10)}

# --- steals, at league rate (spec section 9 check 1) -------------------------
# Steals are a manager's decision, not a card line, so the game proper has no
# rate for them. The league check needs one anyway: without steals the engine
# reproduces the no-steal half-inning and nothing else, because 17% of real
# half-innings contain one and those are scoreless 28.7% of the time against
# 55.4% for the rest. Attempts per plate appearance, measured by state.
STEAL_RATE = {"1__": 0.145, "1_3": 0.370, "_2_": 0.047, "12_": 0.035}
STEAL_OK = {2: 0.83, 3: 0.88}      # success stealing 2nd (103 tries) / 3rd (24)
# d12, per force state: (roll -> flavour). Spec section 8.
# Face order follows the rulebook's Outs Table, which reads flavour-first so the
# two columns line up on the page. Only WHICH face gives which flavour differs
# from an earlier ordering; the counts, and so the probabilities, are the same.
D12_NO_FORCE = ["B"] * 5 + ["B+"] * 7
D12_FORCE = ["FB+"] * 2 + ["F+"] * 2 + ["B"] * 6 + ["B+"] * 2


def move(bases, batter_out, out_runner, plus):
    """One out flavour applied. bases: (1st, 2nd, 3rd) occupied.
    Returns (bases after, outs made, runs). Forced runners advance when the
    batter is safe; unforced runners advance only on a +."""
    on = [i + 1 for i in range(3) if bases[i]]
    forced = set()
    for base in (1, 2, 3):                       # the unbroken chain from 1st
        if base in on:
            forced.add(base)
        else:
            break
    batter_safe = not batter_out
    made = int(batter_out) + int(out_runner is not None)
    after, runs = set(), 0
    for base in sorted(on, reverse=True):
        if base == out_runner:
            continue
        step = 1 if (batter_safe and base in forced) or plus else 0
        if base + step >= 4:
            runs += 1
        else:
            after.add(base + step)
    if batter_safe:
        after.add(1)
    return tuple(i in after for i in (1, 2, 3)), made, runs


def apply_line(line, bases, outs, rng):
    """Resolve one card line. Returns (bases after, outs made, runs)."""
    on1, on2, on3 = bases
    if line == "K":
        return bases, 1, 0
    if line in ("BB", "HBP"):
        return move(bases, batter_out=False, out_runner=None, plus=False)
    if line == "HR":
        return (False, False, False), 0, 1 + sum(bases)
    if line == "1B":
        bullet_face, plus_face = SINGLE_D12[min(outs, 2)]
        d = int(rng.integers(1, 13))
        scored = d >= bullet_face          # Single. or Single+ : runner from 2nd scores
        plus = d >= plus_face              # Single+ as well: runner from 1st takes 3rd
        runs = int(on3) + int(on2 and scored)
        third = (on2 and not scored) or (on1 and plus)
        second = on1 and not plus
        return (True, bool(second), bool(third)), 0, runs
    if line == "2B":
        return (False, True, on1), 0, int(on2) + int(on3)
    if line == "ROE":
        runs = int(on3)
        return (True, on1, on2), 0, runs
    if line == "OUT":
        table = D12_FORCE if on1 else D12_NO_FORCE
        flavour = table[rng.integers(0, 12)]
        plus = flavour.endswith("+")
        if flavour.startswith("FB"):
            return move(bases, True, 1, plus)
        if flavour.startswith("F"):
            return move(bases, False, 1, plus)
        return move(bases, True, None, plus)
    raise ValueError(line)


class Table:
    """The printed d100: a pitcher's cells, a batter's cells, and the bands."""

    def __init__(self, pitcher_cells, batter_cells):
        # to_cells hands these over in TREE_LINES order. The printed card, and
        # so this table, reads them low number to high in PRINT_ORDER.
        p_order, self.p = arrange(np.asarray(pitcher_cells, int), "P")
        b_order, self.b = arrange(np.asarray(batter_cells, int), "B")
        assert self.p.sum() == P_CELLS and self.b.sum() == B_CELLS
        self.p_line = np.repeat(p_order, self.p)
        self.b_line = np.repeat(b_order, self.b)
        self._layout()

    @classmethod
    def from_lines(cls, p_line, b_line):
        """Build from already-expanded cell labels, so a sampled matchup costs nothing."""
        self = cls.__new__(cls)
        self.p_line, self.b_line = p_line, b_line
        self._layout()
        return self

    def _layout(self):
        """Where the bands sit, in the rulebook's Matchup Table order."""
        self.run = RUN_START                       # 33-38 running play
        self.roe = BAND_START                      # 39-40 reached on error
        self.two = self.roe + BAND_CELLS["ROE"]    # 41-44 double
        self.bat = BAT_START                       # 45-99 batter

    def read(self, roll):
        if roll < self.run:
            return self.p_line[roll]
        if roll < self.roe:
            return "RUN"
        if roll < self.two:
            return "ROE"
        if roll < self.bat:
            return "2B"
        return self.b_line[roll - self.bat]


def advance_all(bases):
    """A running play: every runner moves up one. The batter is still at bat."""
    on1, on2, on3 = bases
    return (False, on1, on2), int(on3)


def plate_appearance(table, bases, outs, rng):
    """Roll until a roll ends the plate appearance.

    Returns (bases, outs made, runs already in, runs on the final play, line).
    The two run counts are kept apart because a run that scored on a wild pitch
    stands even if the batter then makes the third out, while runs on the out
    itself do not -- the batter is retired before reaching first, so the inning
    ends first. The line comes back so a fatigue track can charge the pitches that
    outcome really costs (spec 7.2): a walk is 5.40 and contact about 3.2.
    """
    early = 0
    while True:
        line = table.read(int(rng.integers(0, 100)))
        if line == "RUN":
            if any(bases):                      # bases empty: a plain reroll
                bases, r = advance_all(bases)
                early += r
            continue
        b, made, r = apply_line(line, bases, outs, rng)
        return b, made, early, r, line


def steal(bases, rng):
    """One league-rate steal attempt before the plate appearance.

    Returns (bases, outs made). Used only for the league check: a real game has
    the offence declare, so this stands in for a manager who steals as often as
    the league did from each state.
    """
    key = "".join(c if b else "_" for c, b in zip("123", bases))
    if rng.random() >= STEAL_RATE.get(key, 0.0):
        return bases, 0
    on1, on2, on3 = bases
    if on1 and not on2:                                    # stealing 2nd
        return ((False, True, on3), 0) if rng.random() < STEAL_OK[2] else ((False, on2, on3), 1)
    if on2 and not on3:                                    # stealing 3rd
        return ((on1, False, True), 0) if rng.random() < STEAL_OK[3] else ((on1, False, on3), 1)
    return bases, 0


def half_inning(table, rng, bases=(False, False, False), outs=0, steals=True):
    """Runs from this state to the end of the half-inning."""
    total = 0
    while outs < 3:
        bases, made, early, runs, _ = plate_appearance(table, bases, outs, rng)
        total += early                          # runs already in always count
        outs += made
        if outs >= 3:
            break                               # runs on the third out do not
        total += runs
        if steals:
            # AFTER the plate appearance, not before: a steal happens during the
            # NEXT batter's turn, and the feed files it between the two plate
            # appearances. Rolling it first would put it in the wrong transition
            # and leave the batter who singled-and-stole standing on 1st.
            bases, made = steal(bases, rng)
            outs += made
    return total


def league_table() -> Table:
    """The all-league table: the average card on both sides (spec section 9, check 1)."""
    lg = league_card(plate_appearances()).to_numpy()[None, :]
    w = line_weights()
    return Table(to_cells(lg, P_CELLS, w, True)[0], to_cells(lg, B_CELLS, w, False)[0])


def run_expectancy(table, n=40000, seed=20260921) -> pd.DataFrame:
    """Runs to the end of the half-inning from every base-out state, by playing it."""
    rng = np.random.default_rng(seed)
    rows = []
    for outs in range(3):
        for bases in BASE_ORDER:
            occ = tuple(c != "_" for c in bases)
            got = np.fromiter((half_inning(table, rng, occ, outs) for _ in range(n)),
                              float, n)
            rows.append({"bases": bases, "outs": outs, "dice": got.mean(),
                         "se": got.std(ddof=1) / np.sqrt(n)})
    return pd.DataFrame(rows)


def main() -> None:
    pd.set_option("display.width", 220)
    table = league_table()
    print("=== the printed table, league card on both sides ===")
    for label, cells, start, order in (
            ("pitcher", table.p, 0, PRINT_ORDER["P"]),
            ("batter", table.b, table.bat, PRINT_ORDER["B"])):
        at, parts = start, []
        for l, c in zip(order, cells):
            parts.append(f"{l} {at:02d}-{at + c - 1:02d}" if c > 1 else f"{l} {at:02d}")
            at += c
        print(f"  {label}: " + "  ".join(parts))
    print(f"  bands: running play {table.run:02d}-{table.roe - 1:02d}, "
          f"ROE {table.roe:02d}-{table.two - 1:02d}, "
          f"2B {table.two:02d}-{table.bat - 1:02d}")

    print("\n=== check 1: run expectancy, dice against the season ===")
    re_dice = run_expectancy(table)
    from wpbl.markov import run_expectancy as markov_re
    target = markov_re()                            # the season's own fitted table
    re_dice["season"] = [target[(b, o)] for b, o in zip(re_dice["bases"], re_dice["outs"])]
    re_dice["diff"] = re_dice["dice"] - re_dice["season"]
    # how much data the TARGET rests on: the thin states are where it, not the
    # dice, is the uncertain side, so the column belongs next to the difference
    from wpbl import tables as _t
    _p = _t.read("plays", "training")
    _pa = _p[(_p["play_kind"] == "plate_appearance") & (_p["outs_before"] < 3)]
    _st = ["".join(c if isinstance(b, str) else "_" for c, b in
                   zip("123", (r.first_base, r.second_base, r.third_base)))
           for r in _pa.itertuples()]
    _n = pd.Series(1, index=pd.MultiIndex.from_arrays(
        [_st, _pa["outs_before"]])).groupby(level=[0, 1]).size()
    re_dice["season rests on"] = [int(_n.get((b, o), 0))
                                  for b, o in zip(re_dice["bases"], re_dice["outs"])]
    print(re_dice.round(3).to_string(index=False))
    d = re_dice["diff"]
    print(f"  mean absolute difference {d.abs().mean():.3f} runs; largest "
          f"{d.abs().max():.3f} at {re_dice.loc[d.abs().idxmax(), 'bases']} "
          f"{int(re_dice.loc[d.abs().idxmax(), 'outs'])} out")
    print(f"  the dice are high in {int((d > 0).sum())} of 24 states")

    n = 200000
    print(f"\n=== check 1b: the half-inning, {n:,} played ===")
    _report(season_halves(), "season                 ")
    for steals, label in ((False, "league card, no steals "),
                          (True, "league card            ")):
        rng = np.random.default_rng(7)
        got = np.fromiter((half_inning(table, rng, steals=steals) for _ in range(n)),
                          float, n)
        _report(got, label)
    got, leads = sampled_halves()
    _report(got, "real lineups, pitchers by use")
    # Runs per team-game the honest way: whole two-sided games, ended the way the
    # rules end them. Seven times a mean half-inning counts half-innings that were
    # never played, which is why it reads high against the line score.
    tot, skipped, extras, inn, per_team = sim_games()
    s_skip, s_extra, s_inn, s_per_team = season_endings()
    ls = tables.read("line_score", "training")
    s_runs = float(ls.groupby(["game_id", "team_id"])["runs"].sum().mean())
    print(f"  whole games, real endings: {tot.mean():.2f} runs per team-game "
          f"(season {s_runs:.2f}; the figure above counts half-innings nobody played)")
    print(f"    bottom of the {INNINGS}th skipped {100 * skipped:.1f}% "
          f"(season {100 * s_skip:.1f}%), extra innings {100 * extras:.1f}% "
          f"(season {100 * s_extra:.1f}%), mean innings {inn:.2f} (season {s_inn:.2f})")
    print(f"    {per_team:.2f} half-innings batted a team (season {s_per_team:.2f}) at "
          f"{tot.mean() / per_team:.3f} runs each (season {s_runs / s_per_team:.3f}) -- "
          f"the ending rules fix the COUNT; what is left is per half-inning")
    ld = pd.Series(leads).value_counts(normalize=True).sort_index()
    print("  leadoff slot: " + ", ".join(f"{int(k)}:{100 * v:.1f}%" for k, v in ld.items()))
    print("  season      : 1:25.4%, 2:8.2%, 3:8.3%, 4:9.5%, 5:11.7%, 6:9.1%, "
          "7:8.9%, 8:9.7%, 9:8.9%")



def season_halves():
    """Runs scored in each half-inning of the real season.

    The baseline check 1b compares the dice against. It was a hardcoded string
    until 23 Sep -- "1.132 runs, 50.8% scoreless ... 7.77 runs per game" from the
    37-game scope -- which quietly became a comparison against the wrong season
    when two games were added. It is computed now so it cannot go stale again.

    One caution on the runs-per-game figure this feeds into: it is seven times the
    mean half-inning, and half-innings that were never played (a home team ahead
    after the top of the last) are not in the average, so it reads a little high.
    Actual runs per team-game, straight off the line score, is the lower number --
    7.67 against the 7.81 this gives. Both are quoted in section 9.1.
    """
    pl = tables.read("plays", "training")
    return pl.groupby(["game_id", "inning", "half"])["runs_scored"].sum().to_numpy(float)


def season_endings():
    """How the real season's games ended, for sim_games to be checked against.

    Computed, not quoted. The hardcoded-baseline mistake in check 1b was made once
    already (see season_halves) and these are the same kind of number.

    Returns (share of games whose final bottom half was never played, share going
    past INNINGS, mean innings, half-innings batted per team).
    """
    pl = tables.read("plays", "training")
    half = pl.groupby(["game_id", "inning", "half"]).size().reset_index(name="n")
    last = half.groupby("game_id")["inning"].max()
    skipped = extras = 0
    for g, li in last.items():
        rows = half[half["game_id"] == g]
        if not ((rows["inning"] == li) & (rows["half"] == "bottom")).any():
            skipped += 1
        if li > INNINGS:
            extras += 1
    n = len(last)
    teams = pl.groupby(["game_id", "pitching_team_id"]).ngroups
    return skipped / n, extras / n, float(last.mean()), len(half) / teams


def _report(got, label):
    d = pd.Series(got).value_counts(normalize=True)
    print(f"  {label}: {got.mean():.3f} runs, {100 * (got == 0).mean():.1f}% scoreless, "
          + ", ".join(f"{k}r {100 * d.get(k, 0):.1f}%" for k in (1, 2, 3))
          + f", {INNINGS * got.mean():.2f} runs per game")




def lineups():
    """Every team-game's batting order, each slot holding whoever actually batted
    there weighted by how often -- so substitutions ride along with the order."""
    from wpbl.dice import cards as _cards
    bat = tables.read("batting", "training")
    B = _cards("B")
    pa = plate_appearances()
    slot = bat.drop_duplicates(["game_id", "person_id"]).set_index(
        ["game_id", "person_id"])["lineup_spot"]
    pa = pa.assign(spot=slot.reindex(list(zip(pa["game_id"], pa["B"]))).to_numpy())
    pa = pa.dropna(subset=["spot"])
    pa = pa.assign(spot=pa["spot"].astype(int).clip(1, 9))
    out = []
    for _, grp in pa.groupby(["game_id", "B_team"]):
        order = []
        for s in range(1, 10):
            v = grp[grp["spot"] == s]["B"].value_counts()
            v = v[[i in B.index for i in v.index]]
            if not len(v):
                order = None
                break
            order.append((list(v.index), v.to_numpy(float) / v.sum()))
        if order:
            out.append(order)
    return out


def _matchups(seed):
    """Lineups, pitcher draw and expanded card lines, shared by the game sims."""
    from wpbl.dice import B_CELLS, cards as _cards
    rng = np.random.default_rng(seed)
    pa = plate_appearances()
    B, P = _cards("B"), _cards("P")
    w = line_weights()
    b_line = dict(zip(B.index, played_lines(to_cells(B.to_numpy(), B_CELLS, w, False), "B")))
    p_line = played_lines(to_cells(P.to_numpy(), P_CELLS, w, True), "P")
    p_w = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy(float)
    p_w /= p_w.sum()
    return rng, lineups(), b_line, p_line, p_w


def _half(lu, spot, b_line, p_line, p_w, rng, bases=(False, False, False)):
    """One half-inning. Returns (runs, spot after). A new pitcher each inning."""
    pi = int(rng.choice(len(p_line), p=p_w))
    outs, total = 0, 0
    while outs < 3:
        ids, pr = lu[spot % 9]
        spot += 1
        tb = Table.from_lines(p_line[pi], b_line[ids[int(rng.choice(len(ids), p=pr))]])
        bases, made, early, r, _ = plate_appearance(tb, bases, outs, rng)
        total += early
        outs += made
        if outs >= 3:
            break
        total += r
        bases, made = steal(bases, rng)
        outs += made
    return total, spot


def sim_games(n_games=30000, seed=11):
    """Whole two-sided games, ended the way the rules end them.

    Seven innings, and two rules that a string of independent half-innings cannot
    express (Two Outs, So What: Ending the Game):

      the home team does not bat in the bottom of the 7th when it is already ahead
      a tie after seven goes to extra innings, each side starting a runner on 2nd

    The first is why seven times the mean half-inning reads high against the line
    score: some of those half-innings were never played. The second pushes the
    other way. Returns per-team run totals, both sides pooled.
    """
    rng, lus, b_line, p_line, p_w = _matchups(seed)
    totals, skipped, extras, innings, halves = [], 0, 0, [], 0
    for _ in range(n_games):
        away_lu, home_lu = lus[rng.integers(len(lus))], lus[rng.integers(len(lus))]
        a_spot = h_spot = 0
        away = home = 0
        for _ in range(INNINGS - 1):
            r, a_spot = _half(away_lu, a_spot, b_line, p_line, p_w, rng)
            away += r
            r, h_spot = _half(home_lu, h_spot, b_line, p_line, p_w, rng)
            home += r
            halves += 2
        r, a_spot = _half(away_lu, a_spot, b_line, p_line, p_w, rng)   # top of the 7th
        away += r
        halves += 1
        n_inn = INNINGS
        if home > away:
            skipped += 1                       # already ahead: she does not bat
        else:
            r, h_spot = _half(home_lu, h_spot, b_line, p_line, p_w, rng)
            home += r
            halves += 1
        if away == home:
            extras += 1
        on2 = (False, True, False)             # the placed runner
        while away == home:
            n_inn += 1
            r, a_spot = _half(away_lu, a_spot, b_line, p_line, p_w, rng, on2)
            away += r
            r, h_spot = _half(home_lu, h_spot, b_line, p_line, p_w, rng, on2)
            home += r
            halves += 2
        totals += [away, home]
        innings.append(n_inn)
    return (np.array(totals, float), skipped / n_games, extras / n_games,
            float(np.mean(innings)), halves / (2 * n_games))


def sampled_halves(n_games=30000, seed=7):
    """Half-inning run totals from whole games: a real batting order against
    pitchers drawn by batters faced, one per half-inning. This is the league
    check proper -- the league-average card rounds badly (section 9.1)."""
    rng, lus, b_line, p_line, p_w = _matchups(seed)
    runs, leads = [], []
    for _ in range(n_games):
        lu, spot = lus[rng.integers(len(lus))], 0
        for _ in range(INNINGS):
            leads.append(spot % 9 + 1)
            total, spot = _half(lu, spot, b_line, p_line, p_w, rng)
            runs.append(total)
    return np.array(runs, float), np.array(leads)


if __name__ == "__main__":
    main()


# --- fatigue (spec 7.3, 7.4) ---------------------------------------------------
# The track counts MEASURED pitches, unweighted: a struggling pitcher faces more
# batters and so burns faster on her own, without a surcharge (spec 7.2).
FRESH_UNTIL = 20   # her first inning: 19.5 pitches MEASURED, rounded to 20

# Entering a game costs pitches before she faces anybody: she warmed up. Without
# it, short outings are FREE -- a 14-pitch appearance clears overnight, so the
# dominant strategy is to run eight arms through a game at 14 each, nobody ever
# fades, and the whole system idles. That is not a tuning problem: with E = 0
# there is NO recovery rate that both clears a starter's 68 pitches in her six
# days and stops a 14-pitch outing clearing in two. E > 13 is required for the
# pair of constraints to have a solution at all (spec 7.9).
ENTRY_COST = 30                       # about what a reliever throws getting loose
RESTED = -ENTRY_COST                  # a fully recovered pitcher's count, so that
# entering puts her at zero. The count is the rulebook's: it can be negative while
# an arm still has slack, and recovery floors here rather than at zero.
RECOVERY = 20                         # pitches recovered per day; USER DECISION,
# taken over 21 for playability -- a count that moves in twenties is one a player
# can update in their head between games. Both values satisfy the two binding
# constraints at E = 30 (spec 7.9); twenty is the rounder of the two.


def recover(count, days):
    """The rulebook's between-games rule, as one named operation.

    "At the end of every day, all pitchers reduce their Pitch Count by 20 to a
    minimum of -30." So recovery is per calendar day elapsed and floors at RESTED,
    not at zero -- an arm with slack keeps it, which is what lets a rested pitcher
    take the mound at 0 after paying the entry cost.

    It lives here rather than inline in the simulation so `rules_check` has
    something to compare the printed rule against.
    """
    return max(RESTED, count - RECOVERY * days)


def enter(count):
    """Taking the mound: add the warm-up. A fully rested arm arrives at zero."""
    return count + ENTRY_COST


def column_for(count, cap):
    """Which column a pitcher reads, from the pitches on her track (spec 7.4).

    Three states, and the two boundaries are not the same KIND of thing.

    fresh -> fading is MEASURED. The fatigue curve found one step, after the first
    inning, and flat after it (spec 7.2); a starter's first inning is 19.5 pitches
    mean, 19.0 median, so the window is 20.

    fading -> gassed is DESIGNED. No second step was ever found in the data, so
    there is nothing to fit. Capacity is instead placed just past what each arm
    has been shown to do, which makes gassed the price of pushing an arm further
    than a real manager pushed it. It is a deterrent, not a measurement, and the
    spec says so in those words.

    The count is the RULEBOOK's count, not a running total of work. A rested
    pitcher sits at RESTED = -30; entering adds the 30 she spends warming up, so
    she takes the mound at 0 and her first twenty game pitches are fresh. That is
    why neither boundary carries the entry cost: the measured window is one inning
    of GAME pitches, on pitchers who had all warmed up, so the warm-up buys
    availability later rather than making her worse now. Stating it this way makes
    her stamina the fading limit directly -- stamina 80 means fading through 80 --
    which is the form the printed rules use. Every number is 30 lower than the
    first version of this and the states are identical."""
    if count <= FRESH_UNTIL:
        return "fresh"
    return "fading" if count <= cap else "gassed"
