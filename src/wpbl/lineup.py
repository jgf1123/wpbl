"""The best batting order for each team.

    pixi run python -m wpbl.lineup [BOS LAQ NYH SFF]

THE NINE
  * Roster: everyone who has appeared for the team this season.
  * The eight fielders (C 1B 2B 3B SS LF CF RF): players are assigned to
    positions to maximise the total outs fielded at those positions over the
    season (`positions.innings_by_position`, all games and teams, so traded
    players keep their old positions). When one player leads two positions this
    is where the conflict is settled.
  * DH: of the rest of the roster, the batter with the best context-neutral
    runs per PA over the training games, at least 20 PA (--min-pa=N to change).

THE ORDER
  Exact expected runs over seven innings (`lineup_model.py`) against a
  league-average pitcher, smoothed cards not printed cells, steals green-lit for
  any runner whose smoothed success rate beats the break-even of the base-out
  state. Search is local: from several starts, take the best swap or move until
  none helps. One process, one thread, by design.
"""
from __future__ import annotations

import os
for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import itertools
import sys
import time

import numpy as np
import pandas as pd

from wpbl import batters, lineup_model as lm, steal_ratings, tables
from wpbl.dice import cards as dice_cards, league_card, plate_appearances
from wpbl.positions import CARD_POS, innings_by_position
from wpbl.usage_chart import CODES

FIELD = [p for p in CARD_POS if p != "p"]


def rosters() -> dict:
    """Everyone who appeared for the team at any point (batting or pitching)."""
    bat, pit = tables.read("batting", "training"), tables.read("pitching", "training")
    both = pd.concat([bat[["person_id", "team_name"]], pit[["person_id", "team_name"]]])
    return {CODES[t]: set(g["person_id"]) for t, g in both.groupby("team_name")}


def assign(roster: set, outs: pd.DataFrame) -> dict:
    """position -> person_id, maximising total outs; exact by brute force over the
    few players with real time at each position."""
    table = outs[outs["person_id"].isin(roster)].set_index("person_id")
    cands = {pos: list(table[table[pos] > 0].sort_values(pos, ascending=False).index[:4])
             for pos in FIELD}
    best, best_score = None, -1
    for combo in itertools.product(*(cands[p] for p in FIELD)):
        if len(set(combo)) < len(combo):
            continue
        score = sum(table.loc[pid, pos] for pid, pos in zip(combo, FIELD))
        if score > best_score:
            best, best_score = combo, score
    return dict(zip(FIELD, best))


def neutral_ratings() -> pd.DataFrame:
    """Context-neutral runs per PA on every training plate appearance, for anyone with
    at least one (batters.py's own table stops at 37 PA in the regular season, which
    leaves nobody for the DH spot on a 15-player roster). Columns: neutral, pa."""
    fit = batters.plate_appearances("training")
    kept, _ = batters.neutral_values(fit, "credit", "pool", fit)
    grouped = kept.groupby("person_id")["neutral"]
    return pd.DataFrame({"neutral": grouped.mean(), "pa": fit.groupby("person_id").size()})


def local_search(ev: lm.Evaluator, start, cache) -> tuple:
    def val(order):
        key = tuple(order)
        if key not in cache:
            cache[key] = ev.value(list(order))
        return cache[key]
    cur, cv = list(start), val(start)
    while True:
        best, bv = None, cv + 1e-9
        for i, j in itertools.combinations(range(9), 2):
            o = cur.copy(); o[i], o[j] = o[j], o[i]
            if val(o) > bv:
                best, bv = o, val(o)
        for i in range(9):
            for j in range(9):
                if i != j:
                    o = cur.copy(); o.insert(j, o.pop(i))
                    if val(o) > bv:
                        best, bv = o, val(o)
        if best is None:
            return cur, cv
        cur, cv = best, bv


def optimise(ev, starts=6, seed=0):
    rng = np.random.default_rng(seed)
    cache, found = {}, []
    for _ in range(starts):
        found.append(local_search(ev, list(rng.permutation(9)), cache))
    found.sort(key=lambda t: -t[1])
    return found, cache


def main() -> None:
    pd.set_option("display.width", 200)
    floor = next((int(a.split("=")[1]) for a in sys.argv[1:] if a.startswith("--min-pa=")), 20)
    forced = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--dh=")), None)
    want = [a for a in sys.argv[1:] if not a.startswith("--")] or ["BOS", "LAQ", "NYH", "SFF"]
    outs = innings_by_position("training")
    names = (tables.read("batting", "training").drop_duplicates("person_id")
             .set_index("person_id")["person_name"])
    neutral = neutral_ratings()
    card_table = dice_cards("B")
    league = league_card(plate_appearances()).to_numpy()
    ratings = steal_ratings.ratings()
    opps = steal_ratings.events()[0]
    lrate = {}
    for (base, o), row in steal_ratings.league_attempt_rates().iterrows():
        lrate[(0 if base == "second" else 1, o)] = row["mean"]
    for o in range(3):                    # third-base steals are rare: pool the outs
        lrate[(1, o)] = float(opps[opps["base"] == "third"]["attempt"].mean())
    rost = rosters()
    for team in want:
        t0 = time.time()
        roster = rost[team]
        pos = assign(roster, outs)
        for a in sys.argv[1:]:                      # --pos=SS:Saiki forces a fielder
            if a.startswith("--pos="):
                slot, who = a[6:].split(":")
                pos[slot.lower()] = next(p for p in roster if who.lower() in names[p].lower())
        assert len(set(pos.values())) == 8, "a player was forced into two positions"
        rest = sorted((p for p in roster if p not in pos.values() and p in neutral.index
                             and neutral.loc[p, "pa"] >= floor),
                      key=lambda p: -neutral.loc[p, "neutral"])
        dh = next((p for p in rest if forced.lower() in names[p].lower()), None) if forced else rest[0]
        assert dh is not None, f"no DH candidate matches {forced}"
        nine = list(pos.values()) + [dh]
        labels = FIELD + ["dh"]
        cards = np.array([lm.facing_average_pitcher(
            card_table.loc[p].to_numpy() if p in card_table.index else league, league)
            for p in nine])
        steals = lm.steal_params(nine, ratings, lrate)
        ev = lm.Evaluator(cards, steals)
        n_starts = next((int(a[9:]) for a in sys.argv[1:] if a.startswith("--starts=")), 6)
        found, cache = optimise(ev, starts=n_starts)
        order, value = found[0]
        print(f"\n===== {team}: DH {names[dh]} (neutral {neutral.loc[dh, 'neutral']:+.3f} "
              f"in {int(neutral.loc[dh, 'pa'])} PA); next: "
              + ", ".join(f"{names[p]} {neutral.loc[p, 'neutral']:+.3f} ({int(neutral.loc[p, 'pa'])} PA)"
                          for p in rest[1:3]))
        print(f"starts agree on {sum(abs(v - value) < 1e-6 for _, v in found)} of {len(found)}; "
              f"best {value:.4f} runs per 7 innings ({len(cache)} orders evaluated)")
        seen = {}
        for o, v in found:
            seen.setdefault(round(v, 4), o)
        for v, o in list(seen.items())[:4]:
            print(f"  local optimum {v:.4f}: " + " ".join(names[nine[i]].split()[-1] for i in o))
        rows = []
        for slot, i in enumerate(order, 1):
            p = nine[i]
            rows.append({"slot": slot, "player": names[p], "pos": labels[i].upper(),
                         "neutral": neutral["neutral"].get(p, np.nan), "steal_ok": steals.safe[i],
                         "attempt_scale": ratings["attempt_scale"].get(p, 1.0),
                         "green_kinds": int((steals.attempt[i] > 0).sum())})
        print(pd.DataFrame(rows).round(3).to_string(index=False))
        nosteal = lm.Evaluator(cards, lm.Steals(nine, np.zeros_like(steals.attempt), steals.safe))
        print(f"same order, no running game: {nosteal.value(order):.4f}; "
              f"worst order searched: {min(cache.values()):.4f}  ({time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
