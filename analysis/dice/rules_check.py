"""Play `Two_Outs_So_What_rules.md` as written, and check it matches the engine.

    pixi run python analysis/dice/rules_check.py

The rulebook is a SEPARATE statement of the same mechanics, written for a player
rather than derived from the code, so the two can drift apart silently: a d12 band
or a d100 block edited in one and not the other changes the game without failing
anything. On 23 Sep the rulebook's Matchup Table and its own quick reference
disagreed about which rolls were doubles, and nothing caught it.

Three tables are checked, each re-implemented from the printed text:

    the Matchup Table   every roll 00-99 -> pitcher card / running play / error /
                        double / batter card
    the Outs and        every line x base state x out count x d12 face
    Singles Tables
    the fatigue columns every pitch count around each boundary, at each stamina
                        on the ladder

Change either side and this is what catches it.
"""
import itertools

import numpy as np

from wpbl import engine


class FixedDie:
    """Stands in for rng, returning a chosen d12 face."""

    def __init__(self, face):
        self.face = face

    def integers(self, lo, hi=None):
        if hi is None:
            lo, hi = 0, lo
        if (lo, hi) == (1, 13):        # SINGLE_D12 draws 1..12
            return self.face
        if (lo, hi) == (0, 12):        # out flavour draws 0..11
            return self.face - 1
        raise AssertionError((lo, hi))


# ---------------------------------------------------------------------------
# 1. the Matchup Table
# ---------------------------------------------------------------------------
def matchup(roll):
    """00-32 pitcher, 33-38 running play, 39-40 error, 41-44 double, 45-99 batter."""
    if roll <= 32:
        return "pitcher"
    if roll <= 38:
        return "RUN"
    if roll <= 40:
        return "ROE"
    if roll <= 44:
        return "2B"
    return "batter"


def check_matchup():
    table = engine.Table.from_lines(np.array(["K"] * 33), np.array(["HR"] * 55))
    bad = 0
    for roll in range(100):
        want = matchup(roll)
        got = table.read(roll)
        got = "pitcher" if got == "K" else "batter" if got == "HR" else got
        if got != want:
            bad += 1
            if bad <= 8:
                print(f"  MISMATCH roll {roll:02d}: rulebook {want}, engine {got}")
    print(f"Matchup Table: 100 rolls checked, {bad} mismatches")
    return bad


# ---------------------------------------------------------------------------
# 2. the Outs and Singles Tables
# ---------------------------------------------------------------------------
def rulebook(line, bases, outs, d12):
    """The results exactly as the rulebook states them."""
    on1, on2, on3 = bases

    if line == "K":
        return bases, 1, 0

    if line in ("BB", "HBP"):
        # batter to 1st, runners advance only if forced
        if on1 and on2 and on3:
            return (True, True, True), 0, 1
        if on1 and on2:
            return (True, True, True), 0, 0
        if on1:
            return (True, True, on3), 0, 0
        return (True, on2, on3), 0, 0

    if line == "HR":
        return (False, False, False), 0, 1 + sum(bases)

    if line == "2B":
        # batter to 2nd, all runners advance 2 bases
        return (False, True, on1), 0, int(on2) + int(on3)

    if line == "ROE":
        # batter to 1st, every runner advances 1 base
        return (True, on1, on2), 0, int(on3)

    if line == "1B":
        scores_from_2nd, to_3rd_from_1st = ((8, 11) if outs < 2 else (5, 10))
        scored = d12 >= scores_from_2nd
        plus = d12 >= to_3rd_from_1st
        runs = int(on3) + int(on2 and scored)           # 3rd always scores
        third = (on2 and not scored) or (on1 and plus)  # otherwise advance one
        second = on1 and not plus
        return (True, bool(second), bool(third)), 0, runs

    if line == "OUT":
        # Outs Table: flavour-first, as printed
        if on1:
            flavour = ("FB+" if d12 <= 2 else "F+" if d12 <= 4
                       else "B" if d12 <= 10 else "B+")
        else:
            flavour = "B" if d12 <= 5 else "B+"
        if flavour == "B":
            return bases, 1, 0                          # runners hold
        if flavour == "B+":                             # all runners advance one
            return (False, on1, on2), 1, int(on3)
        if flavour == "F+":
            # runner from 1st out, batter to 1st, all others advance one
            return (True, False, on2), 1, int(on3)
        if flavour == "FB+":
            # batter and runner from 1st both out, others advance one
            return (False, False, on2), 2, int(on3)
    raise ValueError(line)


def check_results():
    bad = checked = 0
    for line in ("K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"):
        for bits in itertools.product((False, True), repeat=3):
            for outs in (0, 1, 2):
                faces = range(1, 13) if line in ("1B", "OUT") else (1,)
                for d in faces:
                    got = rulebook(line, bits, outs, d)
                    want = engine.apply_line(line, bits, outs, FixedDie(d))
                    checked += 1
                    if got != want:
                        bad += 1
                        if bad <= 8:
                            print(f"  MISMATCH {line} bases={bits} outs={outs} d12={d}")
                            print(f"     rulebook {got}")
                            print(f"     engine   {want}")
    print(f"Outs and Singles Tables: {checked} combinations checked, {bad} mismatches")
    return bad


# ---------------------------------------------------------------------------
# 3. the fatigue columns
# ---------------------------------------------------------------------------
def column(count, stamina):
    """Fresh up to 20, fading up to her stamina, gassed past that."""
    if count <= 20:
        return "fresh"
    return "fading" if count <= stamina else "gassed"


def check_columns():
    bad = checked = 0
    for stamina in (50, 60, 70, 80, 90, 100, 110):
        for count in range(-30, int(stamina) + 25):
            want = column(count, stamina)
            got = engine.column_for(count, float(stamina))
            checked += 1
            if got != want:
                bad += 1
                if bad <= 8:
                    print(f"  MISMATCH count {count} stamina {stamina}: "
                          f"rulebook {want}, engine {got}")
    print(f"Fatigue columns: {checked} counts checked, {bad} mismatches")
    return bad



# ---------------------------------------------------------------------------
# 4. the pitch count: what a batter costs
# ---------------------------------------------------------------------------
def rulebook_cost(line):
    """Walk 5, Strikeout 5, anything else 3 -- the printed table."""
    return 5 if line in ("BB", "K") else 3


def check_costs():
    """The rulebook's costs against the engine's.

    These are the units the whole track is denominated in, so a disagreement
    rescales every threshold: the fresh window, each stamina, the entry cost and
    the recovery rate all mean something different in each currency.
    """
    from wpbl.dice import PITCH_COST
    bad = 0
    print("Pitch costs, per plate appearance:")
    for line in ("BB", "K", "HBP", "HR", "1B", "2B", "ROE", "OUT"):
        want, got = rulebook_cost(line), PITCH_COST[line]
        differs = abs(want - got) > 1e-9
        bad += int(differs)
        print("    {:4s} rulebook {}   engine {:.2f}{}".format(
            line, want, got, "   <-- DIFFERS" if differs else ""))
    return bad


# ---------------------------------------------------------------------------
# 5. the pitch count: entering, and recovering between games
# ---------------------------------------------------------------------------
def rulebook_track(count, days_rested=0, entering=False, outcomes=()):
    """The printed rules, applied in the printed order.

    "At the end of every day, all pitchers reduce their Pitch Count by 20 to a
    minimum of -30." Then, on entering, "add 30 to her Pitch Count before she
    faces anybody."
    """
    for _ in range(days_rested):
        count = max(-30, count - 20)
    if entering:
        count += 30
    for line in outcomes:
        count += rulebook_cost(line)
    return count


def check_track():
    bad = checked = 0
    for start in range(-30, 200):
        for days in range(0, 10):
            want, got = rulebook_track(start, days_rested=days), engine.recover(start, days)
            checked += 1
            if want != got:
                bad += 1
                if bad <= 8:
                    print("  MISMATCH recover({}, {}): rulebook {}, engine {}".format(
                        start, days, want, got))
    for start in range(-30, 200):
        want, got = rulebook_track(start, entering=True), engine.enter(start)
        checked += 1
        if want != got:
            bad += 1

    # The rulebook's own worked example, verbatim from the printed text:
    #   "A pitcher with Stamina 80 finishes a game at 83 Pitch Count. She recovers
    #    40 over that night and the following day, leaving 43. If she then pitches
    #    a game 2 days after her last outing, warming up puts her at 73: deep into
    #    Fading and only 7 pitches from Gassed."
    after = engine.recover(83, 2)
    entered = engine.enter(after)
    for label, want, got in (("recovers to", 43, after),
                             ("enters at", 73, entered),
                             ("column", "fading", engine.column_for(entered, 80)),
                             ("from gassed", 7, 80 - entered)):
        checked += 1
        if want != got:
            bad += 1
            print("  MISMATCH rulebook example, {}: printed {}, engine {}".format(
                label, want, got))
    print("Pitch count track: {} cases checked, {} mismatches".format(checked, bad))
    return bad


# ---------------------------------------------------------------------------
# 6. the season's shape, anchored to PLAY-BY-PLAY
# ---------------------------------------------------------------------------
# Anchored to plays on purpose. The `games` table carries one fixture under
# several game_ids -- 71 rows for 40 played games, the rest "Not Started"
# placeholders -- so a count taken from it can be inflated without looking wrong
# (spec Data notes), and that is exactly how the season simulator came to play
# 140 team-games instead of 80. Play-by-play cannot be fooled that way: a game
# either has plays or it does not.
def check_season_shape():
    from wpbl import tables
    from wpbl.season_fatigue import schedules, staffs

    played = tables.read("plays", "all")["game_id"].nunique()
    pitching = tables.read("pitching", "all")
    outings = int((pitching["bf"] > 0).sum())
    arms = outings / (2 * played)

    team_games = sum(len(v) for v in schedules().values())
    bad = 0
    print("Season shape, anchored to play-by-play:")
    for label, want, got in (("team-games in the calendar", 2 * played, team_games),
                             ("teams with a staff", 4, len(staffs()))):
        differs = want != got
        bad += int(differs)
        print("    {:30s} plays {:5}   sim {:5}{}".format(
            label, want, got, "   <-- DIFFERS" if differs else ""))
    print("    {:30s} plays {:5.2f}   (the manager's target)".format(
        "arms per team-game", arms))
    return bad


# ---------------------------------------------------------------------------
# 7. COLUMN_SHARE, replayed from the real outings
# ---------------------------------------------------------------------------
def replay_shares(cost):
    """Share of real PLATE APPEARANCES read off each column, in order, with carry.

    `cost` maps a line to pitches, so the replay can run in either currency. It
    walks the real per-PA sequence rather than an average, so each boundary falls
    where it really fell.
    """
    import pandas as pd
    from wpbl.dice import CAPACITY_DEFAULT, capacity, plate_appearances

    pa = plate_appearances().sort_values(["date", "game_id", "sequence"])
    caps = capacity()
    seen = {"fresh": 0, "fading": 0, "gassed": 0}
    state = {}
    for (gid, team, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        day = pd.to_datetime(grp["date"].iloc[0])
        track, prev = state.get(pid, (-30.0, None))
        if prev is not None:
            track = engine.recover(track, (day - prev).days)
        track = engine.enter(track)
        cap = caps.get(pid, CAPACITY_DEFAULT)
        for line in grp["line"]:
            seen[engine.column_for(track, cap)] += 1          # read BEFORE the batter
            track += cost(line)
        state[pid] = (track, day)
    n = sum(seen.values())
    return {k: v / n for k, v in seen.items()}


def check_column_share():
    """The constant that centres every card, against what the real season gives.

    COLUMN_SHARE is the weighting centring uses, so if it drifts from the usage it
    claims to describe, every printed card is centred on the wrong average.
    """
    from wpbl.dice import COLUMN_SHARE, PITCH_COST
    got = replay_shares(lambda l: PITCH_COST[l])
    rule = replay_shares(rulebook_cost)
    bad = 0
    print("COLUMN_SHARE, replayed from the real outings:")
    print("    {:10s}{:>10s}{:>13s}{:>15s}".format(
        "", "constant", "engine cost", "rulebook cost"))
    for k in ("fresh", "fading", "gassed"):
        off = abs(got[k] - COLUMN_SHARE[k])
        bad += int(off > 0.03)
        print("    {:10s}{:10.3f}{:13.3f}{:15.3f}{}".format(
            k, COLUMN_SHARE[k], got[k], rule[k], "   <-- DRIFTED" if off > 0.03 else ""))
    return bad



# ---------------------------------------------------------------------------
# 8. numbers the SPEC quotes, against the numbers the code computes
# ---------------------------------------------------------------------------
# Every drift found while building section 7 was a figure the spec stated and the
# code also computed: the boundaries, the column shares, the pitch costs, the
# capacity fit, the recovery examples. Prose cannot be made to update itself, so
# the load-bearing ones are pinned here. A data refresh SHOULD fail this check --
# that is the signal to update the spec, which is exactly what went missing before.
SPEC = {
    # section 7.4, the capacity fit
    "capacity intercept":        (35.0,  0.5),
    "capacity slope":            (0.73,  0.02),
    "capacity R2":               (0.54,  0.02),
    "capacity residual SD":      (12.6,  0.5),
    "ladder min":                (44,    0),
    "ladder max":                (100,   0),
    "ladder median":             (69.5,  0),
    # section 7.6, the spacing of the columns
    "step fresh->fading":        (0.018, 0.002),
    "step fading->gassed":       (0.032, 0.002),
    # section 7.9, the currency
    "pitches per plate appearance": (3.482, 0.005),
}


def spec_numbers():
    """Recompute everything in SPEC from the data, in the game's own currency."""
    import numpy as np
    import pandas as pd
    from wpbl.dice import (COLUMN_SHARE, PITCH_COST, capacity, cards,
                           column_cells, line_weights, plate_appearances)

    pa = plate_appearances()
    pa = pa.assign(p=[PITCH_COST.get(l, 3.3) for l in pa["line"]])
    o = pa.groupby(["game_id", "P_team", "P"], sort=False)["p"].sum().reset_index()
    per = o.groupby("P")["p"].agg(["size", "median", "max"])
    fit = per[per["size"] >= 3]
    slope, intercept = np.polyfit(fit["median"], fit["max"], 1)
    resid = fit["max"] - (intercept + slope * fit["median"])
    caps = pd.Series(capacity())

    P = cards("P")
    w = line_weights()
    cc = column_cells(P.to_numpy(), centred=True)
    use = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy(float)
    use /= use.sum()
    v = {k: float(((cc[k] * w).sum(axis=1) / 100.0 * use).sum()) for k in cc}

    return {
        "capacity intercept": float(intercept),
        "capacity slope": float(slope),
        "capacity R2": float(1 - resid.var() / fit["max"].var()),
        "capacity residual SD": float(resid.std()),
        "ladder min": float(caps.min()),
        "ladder max": float(caps.max()),
        "ladder median": float(caps.median()),
        "step fresh->fading": v["fading"] - v["fresh"],
        "step fading->gassed": v["gassed"] - v["fading"],
        "pitches per plate appearance": float(pa["p"].mean()),
    }


def check_spec_numbers():
    got = spec_numbers()
    bad = 0
    print("Numbers the spec quotes:")
    print("    {:32s}{:>10s}{:>10s}".format("", "spec", "computed"))
    for name, (want, tol) in SPEC.items():
        now = got[name]
        off = abs(now - want) > tol
        bad += int(off)
        print("    {:32s}{:10.3f}{:10.3f}{}".format(
            name, want, now, "   <-- DRIFTED" if off else ""))
    return bad


def main():
    bad = check_matchup() + check_results() + check_columns()
    print()
    bad += check_costs()
    bad += check_track()
    print()
    bad += check_season_shape()
    print()
    bad += check_column_share()
    print()
    bad += check_spec_numbers()
    print()
    print("EVERYTHING AGREES" if bad == 0 else f"{bad} MISMATCHES -- fix before playing")


if __name__ == "__main__":
    main()
