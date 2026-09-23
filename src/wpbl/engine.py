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
from wpbl.dice import (BAND_CELLS, B_CELLS, CARD_LINES, PA_CELLS, P_CELLS,
                       RUN_CELLS, TREE_LINES, cards, league_card, line_weights,
                       plate_appearances, to_cells)

BASE_ORDER = ["___", "1__", "_2_", "__3", "12_", "1_3", "_23", "123"]
INNINGS = 7                        # WPBL plays seven (32 of 37 training games)

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
D12_NO_FORCE = ["B"] * 5 + ["B+"] * 7
D12_FORCE = ["B"] * 6 + ["B+"] * 2 + ["F+"] * 2 + ["FB+"] * 2


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
        self.p = np.asarray(pitcher_cells, int)
        self.b = np.asarray(batter_cells, int)
        assert self.p.sum() == P_CELLS and self.b.sum() == B_CELLS
        self.p_line = np.repeat(TREE_LINES, self.p)
        self.b_line = np.repeat(TREE_LINES, self.b)
        self.two = P_CELLS
        self.roe = self.two + BAND_CELLS["2B"]
        self.run = self.roe + BAND_CELLS["ROE"]
        self.bat = self.run + RUN_CELLS

    @classmethod
    def from_lines(cls, p_line, b_line):
        """Build from already-expanded cell labels, so a sampled matchup costs nothing."""
        self = cls.__new__(cls)
        self.p_line, self.b_line = p_line, b_line
        self.two = P_CELLS
        self.roe = self.two + BAND_CELLS["2B"]
        self.run = self.roe + BAND_CELLS["ROE"]
        self.bat = self.run + RUN_CELLS
        return self

    def read(self, roll):
        if roll < self.two:
            return self.p_line[roll]
        if roll < self.roe:
            return "2B"
        if roll < self.run:
            return "ROE"
        if roll < self.bat:
            return "RUN"
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
    for label, cells, start in (("pitcher", table.p, 0), ("batter", table.b, table.bat)):
        at, parts = start, []
        for l, c in zip(TREE_LINES, cells):
            parts.append(f"{l} {at:02d}-{at + c - 1:02d}" if c > 1 else f"{l} {at:02d}")
            at += c
        print(f"  {label}: " + "  ".join(parts))
    print(f"  bands: 2B {table.two:02d}-{table.roe - 1:02d}, ROE {table.roe:02d}-"
          f"{table.run - 1:02d}, running play {table.run:02d}-{table.bat - 1:02d}")

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
    print("  season: 1.132 runs, 50.8% scoreless, 1r 19.6%, 2r 13.4%, 7.77 runs per game")
    for steals, label in ((False, "league card, no steals "),
                          (True, "league card            ")):
        rng = np.random.default_rng(7)
        got = np.fromiter((half_inning(table, rng, steals=steals) for _ in range(n)),
                          float, n)
        _report(got, label)
    got, leads = sampled_halves()
    _report(got, "real lineups, pitchers by use")
    ld = pd.Series(leads).value_counts(normalize=True).sort_index()
    print("  leadoff slot: " + ", ".join(f"{int(k)}:{100 * v:.1f}%" for k, v in ld.items()))
    print("  season      : 1:25.4%, 2:8.2%, 3:8.3%, 4:9.5%, 5:11.7%, 6:9.1%, "
          "7:8.9%, 8:9.7%, 9:8.9%")



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


def sampled_halves(n_games=30000, seed=7):
    """Half-inning run totals from whole games: a real batting order against
    pitchers drawn by batters faced, one per half-inning. This is the league
    check proper -- the league-average card rounds badly (section 9.1)."""
    from wpbl.dice import B_CELLS, cards as _cards
    rng = np.random.default_rng(seed)
    pa = plate_appearances()
    B, P = _cards("B"), _cards("P")
    w = line_weights()
    b_line = {pid: np.repeat(TREE_LINES, r) for pid, r in
              zip(B.index, to_cells(B.to_numpy(), B_CELLS, w, False))}
    p_line = [np.repeat(TREE_LINES, r) for r in to_cells(P.to_numpy(), P_CELLS, w, True)]
    p_w = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy(float)
    p_w /= p_w.sum()
    lus, runs, leads = lineups(), [], []
    for _ in range(n_games):
        lu, spot = lus[rng.integers(len(lus))], 0
        for _ in range(INNINGS):
            pi = int(rng.choice(len(p_line), p=p_w))
            bases, outs, total = (False, False, False), 0, 0
            leads.append(spot % 9 + 1)
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
            runs.append(total)
    return np.array(runs, float), np.array(leads)


if __name__ == "__main__":
    main()


# --- fatigue (spec 7.3, 7.4) ---------------------------------------------------
# The track counts MEASURED pitches, unweighted: a struggling pitcher faces more
# batters and so burns faster on her own, without a surcharge (spec 7.2).
PITCH_COST = {"K": 4.92, "BB": 5.40, "HBP": 3.05, "HR": 3.26, "1B": 3.08,
              "2B": 3.18, "ROE": 3.10, "OUT": 3.23}
FRESH_UNTIL = 17                      # her first inning, at 17.5 pitches an inning
CAPACITY = {"start": 68, "relief": 31}    # median outing by role
RECOVERY = 14                         # pitches recovered per day (user, 22 Sep)


def column_for(track, role):
    """Which column a pitcher reads, from the pitches on her track (spec 7.4).

    Two columns, not three. At 33 cells one cell is worth about 0.013 runs a
    batter, and centred, a third column would sit under a cell away from the
    second -- a distinction no rounding can print (spec 7.6)."""
    return "fresh" if track <= FRESH_UNTIL else "tired"


# The share of PLATE APPEARANCES resolved against a pitcher in each column,
# counted over a simulated season under the pull rule: 43% are pitched by someone
# still inside her fresh window, 57% by someone past it. The columns are CENTRED
# on these (see pitcher_columns), which is circular -- a tired pitcher allows more
# baserunners, faces more batters, and so spends more plate appearances tired --
# so it was iterated. Centring on 0.433 returns 0.432, which returns 0.4319, and
# it sits there. One pass is enough.
COLUMN_SHARE = {"fresh": 0.433, "tired": 0.567}


def pitcher_columns(centred=True):
    """Every pitcher's three columns, as expanded cell labels ready for Table.

    CENTRED, and this matters. A pitcher's card is built from all her plate
    appearances, the tired ones included, so it already carries the average
    fatigue she pitched with. Hanging a penalty on top of it counts that twice and
    inflates the league's scoring. Centring shifts all three columns so their
    usage-weighted average returns her card exactly: a FRESH pitcher is better
    than her season line, a gassed one worse, and the average is unchanged.
    """
    from wpbl.dice import FATIGUE, cards as _cards, fatigue_card
    P = _cards("P")
    w = line_weights()
    mean_lam = sum(COLUMN_SHARE[k] * v for k, v in FATIGUE.items()) if centred else 0.0
    out = {}
    for name, lam in FATIGUE.items():
        cells = to_cells(fatigue_card(P.to_numpy(), lam - mean_lam), P_CELLS, w, True)
        out[name] = [np.repeat(TREE_LINES, r) for r in cells]
    return P.index, out


def stint_targets():
    """The observed distribution of pitches in an outing, by role.

    The pull rule is DESCRIPTIVE on purpose: a manager is sampled to come out
    where real managers came out, which is all that is needed to make a fatigue
    setting identifiable (spec 7.2). It is not the AI manager check 3 wants.
    """
    pa = plate_appearances()
    pa = pa.assign(pitches=[PITCH_COST.get(l, 3.3) for l in pa["line"]])
    pa = pa.sort_values(["game_id", "P_team", "date"])
    first = pa.groupby(["game_id", "P_team"])["P"].first()
    out = {"start": [], "relief": []}
    for (gm, tm, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        role = "start" if first.get((gm, tm)) == pid else "relief"
        out[role].append(float(grp["pitches"].sum()))
    return {k: np.array(v) for k, v in out.items()}


def sim_fatigue(n_games=20000, fatigue=True, seed=20260922, centred=True):
    """Play whole games with pitching changes, and optionally with the track on.

    One team's seven half-innings at a time, against a staff that changes when the
    current pitcher passes a stint length sampled from the real distribution. The
    track carries her measured pitches; the column she reads follows from it. Every
    outing starts at zero, which matches the league: four in five really do (spec
    7.4), so the cross-day carry is a season-level concern, not a game-level one.
    """
    rng = np.random.default_rng(seed)
    from wpbl.dice import B_CELLS, cards as _cards
    ids, cols = pitcher_columns(centred=centred)
    B = _cards("B")
    w = line_weights()
    b_line = {pid: np.repeat(TREE_LINES, r) for pid, r in
              zip(B.index, to_cells(B.to_numpy(), B_CELLS, w, False))}
    pa = plate_appearances()
    p_w = pa.groupby("P").size().reindex(ids).fillna(0).to_numpy(float)
    p_w /= p_w.sum()
    st = stint_targets()
    lus = lineups()
    runs, stints, seen = [], [], {"fresh": 0, "tired": 0}
    for _ in range(n_games):
        lu, spot = lus[rng.integers(len(lus))], 0
        total = 0
        pi = int(rng.choice(len(ids), p=p_w))
        role = "start"
        track, target = 0.0, float(rng.choice(st["start"]))
        for _ in range(INNINGS):
            bases, outs = (False, False, False), 0
            while outs < 3:
                if fatigue and track >= target:              # the hook
                    stints.append((role, track))
                    pi = int(rng.choice(len(ids), p=p_w))
                    role = "relief"
                    track, target = 0.0, float(rng.choice(st["relief"]))
                col = column_for(track, role) if fatigue else "fresh"
                seen[col] += 1
                ids_b, pr = lu[spot % 9]
                spot += 1
                tb = Table.from_lines(cols[col][pi],
                                      b_line[ids_b[int(rng.choice(len(ids_b), p=pr))]])
                bases, made, early, r, line = plate_appearance(tb, bases, outs, rng)
                track += PITCH_COST.get(line, 3.3)
                total += early
                outs += made
                if outs >= 3:
                    break
                total += r
                bases, made = steal(bases, rng)
                outs += made
        stints.append((role, track))
        runs.append(total)
    n = sum(seen.values())
    return (np.array(runs, float), pd.DataFrame(stints, columns=["role", "pitches"]),
            {k: v / n for k, v in seen.items()})


def stamina():
    """Each pitcher's fresh window, in pitches, shrunk toward the role default.

    Stamina is a real trait but a small one: per-pitcher median start lengths run
    from 58 to 92 pitches, SD 8.9, of which 5.5 is the noise in a median of about
    five starts -- so 7.0 is real. Her own median therefore gets weight
    49 / (49 + 30) = 0.62 against the role median, the same shrinkage idea the
    cards use.

    The fresh window scales with it. The measured step comes after her first
    inning for pitchers pooled together (spec 7.2), and nothing in the data says
    when a strong arm's step comes; scaling is the assumption that a pitcher who
    lasts a fifth longer stays fresh a fifth longer. ASSUMPTION.
    """
    from wpbl.dice import cards as _cards
    W_OWN = 0.62
    pa = plate_appearances()
    pa = pa.assign(pitches=[PITCH_COST.get(l, 3.3) for l in pa["line"]])
    first = pa.sort_values(["game_id", "P_team", "date"]).groupby(
        ["game_id", "P_team"])["P"].first()
    rows = []
    for (gm, tm, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        rows.append({"P": pid, "role": "start" if first.get((gm, tm)) == pid else "relief",
                     "pitches": float(grp["pitches"].sum())})
    a = pd.DataFrame(rows)
    out = {}
    for pid in _cards("P").index:
        sub = a[a["P"] == pid]
        role = "start" if (sub["role"] == "start").mean() >= 0.5 else "relief"
        base = CAPACITY[role]
        own = sub[sub["role"] == role]["pitches"].median()
        cap = base if not np.isfinite(own) else base + W_OWN * (own - base)
        out[pid] = (role, float(cap), FRESH_UNTIL * float(cap) / CAPACITY["start"])
    return out


def manager_pull(cur_cost, bench_cost):
    """Pull when the batter in front of her is cheaper against someone else.

    No free parameter and no fitting to observed hooks. Every batter is worth the
    same in runs, so the run-minimising allocation gives each one to the best arm
    still able to take him: keep her while her CURRENT column beats the best
    available arm's FRESH column, and change when it does not. A strong starter
    stays in because her tired card is still better than the bullpen; a weak one
    goes early. Check 3 then asks whether that lands where real managers landed,
    which it cannot do if the rule were fitted to them.
    """
    return cur_cost > bench_cost
