"""The top of the 1st, through the fourth batter's plate appearance.

    pixi run python -m wpbl.lineup_start [\"NYH, Saiki SS\" ...]

Exact, not simulated: the same chain as `lineup_model.py`, pushed forward play
by play from the first pitch, with runs carried along. Two snapshots, each grouped by (outs, base of the lead runner):

  BEFORE  the state the fourth batter's card is read in: after batters 1-3 and
          after every steal / wild pitch that happens during her turn, before her
          plate appearance resolves. If the inning ended first (three outs in the
          first three PAs, or a caught stealing on the third out while she was up)
          there is no such state: "3 outs, no PA".
  AFTER   the state once her plate appearance has resolved (three outs included).
          If she never got one it is the same "3 outs, no PA" row.

The orders are the recommended ones from `wpbl.lineup` (NYH with Lahners at DH, run
once with Perez at SS and once with Saiki at SS). Arguments are LINEUPS labels.
"""
from __future__ import annotations

import os
for var in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ.setdefault(var, "1")

import sys
from collections import defaultdict

import numpy as np
import pandas as pd

from wpbl import lineup as L, lineup_model as lm, steal_ratings, tables
from wpbl.dice import cards as dice_cards, league_card, plate_appearances
from wpbl.positions import innings_by_position

# label -> (team, forced DH or None, forced fielders {pos: name}, batting order by surname)
LINEUPS = {
    "SFF": ("SFF", None, {}, ["Jorge", "Leblanc", "Kaplan", "Whitmore", "Gutierrez", "Albayati", "Gianelloni", "Leguizamon", "Park"]),
    "NYH, Perez SS": ("NYH", "Lahners", {},
                      ["Lahners", "Yonetani", "Willan", "Benites", "Sullivan", "Studer", "Perez", "Eccles", "Zettlemoyer"]),
    "NYH, Saiki SS": ("NYH", "Lahners", {"ss": "Saiki"},
                      ["Lahners", "Yonetani", "Saiki", "Benites", "Sullivan", "Studer", "Eccles", "Zettlemoyer", "Willan"]),
    "LAQ": ("LAQ", None, {}, ["Lansdell", "Edwards", "Benitez", "Mackay", "Foxx", "Eynon", "Maximiliana", "Davis", "Hondras"]),
    "BOS": ("BOS", None, {}, ["Bryant", "Geldenhuis", "Suzuka", "Hastings", "Schroder", "Greenwood", "Dumais", "Paddison", "Padgham"]),
}
FOURTH = 3


def build(label: str):
    team, forced, fixed, surnames = LINEUPS[label]
    outs = innings_by_position("training")
    names = (tables.read("batting", "training").drop_duplicates("person_id")
             .set_index("person_id")["person_name"])
    neutral = L.neutral_ratings()
    roster = L.rosters()[team]
    pos = L.assign(roster, outs)
    for slot, who in fixed.items():
        pos[slot] = next(p for p in roster if who in names[p])
    rest = sorted((p for p in roster if p not in pos.values() and p in neutral.index
                   and neutral.loc[p, "pa"] >= 20), key=lambda p: -neutral.loc[p, "neutral"])
    dh = next(p for p in rest if forced in names[p]) if forced else rest[0]
    nine = list(pos.values()) + [dh]
    order = [next(i for i, p in enumerate(nine) if key in names[p]) for key in surnames]
    card_table = dice_cards("B")
    league = league_card(plate_appearances()).to_numpy()
    cards = np.array([lm.facing_average_pitcher(
        card_table.loc[p].to_numpy() if p in card_table.index else league, league) for p in nine])
    ratings = steal_ratings.ratings()
    opps = steal_ratings.events()[0]
    lrate = {}
    for (base, o), row in steal_ratings.league_attempt_rates().iterrows():
        lrate[(0 if base == "second" else 1, o)] = row["mean"]
    for o in range(3):
        lrate[(1, o)] = float(opps[opps["base"] == "third"]["attempt"].mean())
    return nine, order, cards, lm.steal_params(nine, ratings, lrate), [names[nine[i]] for i in order]


def propagate(order, cards, steals, pairs=None):
    """Returns (before, after). With `pairs` (a defaultdict), also records the joint
    (state before her PA, state after) weight for every PA she actually takes."""
    g = lm.graph()
    L_ = np.asarray(order)
    card = cards[L_]                                             # by batting slot
    line_of = {"K": ["K"], "FP": ["BB", "HBP"], "HR": ["HR"], "1B": ["1B"], "2B": ["2B"],
               "ROE": ["ROE"], "OUT": ["OUT"]}
    from wpbl.dice import CARD_LINES

    def p_line(b, op_line):
        return sum(card[b, CARD_LINES.index(l)] for l in line_of[op_line]) if op_line != "FP" \
            else card[b, CARD_LINES.index("BB")] + card[b, CARD_LINES.index("HBP")]

    def a_s(b, r):
        lag = g.st_lag[r]
        if lag < 0:
            return 0.0, 0.0, -1
        who = L_[(b - lag) % 9]
        return steals.attempt[who, g.st_kind[r]], steals.safe[who], who

    def key(r, runs):
        outs, cfg = g.states[r]
        return (outs, lm.bases_of(cfg), runs)

    before, after = defaultdict(float), defaultdict(float)
    live = {(0, g.index[(0, lm.CFG0)], 0): 1.0}
    while live:
        nxt = defaultdict(float)
        for (b, r, runs), p in live.items():
            a, s, _ = a_s(b, r)
            rs = g.run_share[r]
            if a > 0:                                            # a steal attempt
                nxt_safe = (b, g.st_safe[r], runs)
                nxt[nxt_safe] += p * a * s
                cd = g.st_caught[r]
                if cd < 0:
                    before[("over", runs)] += p * a * (1 - s)
                    after[("over", runs)] += p * a * (1 - s)
                else:
                    nxt[(b, cd, runs)] += p * a * (1 - s)
            for dst, rr, q in g.run_detail.get(r, []):           # wild pitch, passed ball, balk
                w = p * (1 - a) * rs * q
                if dst < 0:
                    before[("over", runs + rr)] += w
                    after[("over", runs + rr)] += w
                else:
                    nxt[(b, dst, runs + rr)] += w
            pa_w = p * (1 - a) * (1 - rs)
            if b == FOURTH:
                before[key(r, runs)] += pa_w
            for line, dst, rr, q in g.pa_detail.get(r, []):
                w = pa_w * p_line(b, line) * q
                if b == FOURTH:
                    done = ("over", runs + rr) if dst < 0 else key(dst, runs + rr)
                    after[done] += w
                    if pairs is not None:
                        pairs[(key(r, runs), done)] += w
                elif dst < 0:                                    # inning over before her turn
                    before[("over", runs + rr)] += w
                    after[("over", runs + rr)] += w
                else:
                    nxt[(b + 1, dst, runs + rr)] += w
        live = {k: v for k, v in nxt.items() if v > 1e-13}
    return before, after


LEAD = ["none", "1st", "2nd", "3rd"]


def lead(bases: str) -> str:
    """The base of the lead runner: the furthest-advanced runner on base."""
    return "3rd" if bases[2] != "_" else "2nd" if bases[1] != "_" else "1st" if bases[0] != "_" else "none"


def table(dist: dict, with_outs: bool = True) -> pd.DataFrame:
    rows = defaultdict(lambda: defaultdict(float))
    for k, p in dist.items():
        cap = lambda n: min(n, 4)
        if k[0] == "over":
            rows["3 outs"][cap(k[1])] += p
        else:
            outs, bases, runs = k
            label = (f"{outs} out, lead runner {lead(bases)}" if with_outs
                     else f"lead runner {lead(bases)}")
            rows[label][cap(runs)] += p
    frame = pd.DataFrame(rows).T.reindex(columns=range(5)).fillna(0.0)
    frame.columns = ["0 runs", "1", "2", "3", "4+"]
    frame["total"] = frame.sum(axis=1)
    order = sorted(frame.index, key=lambda s: (s == "3 outs", s[0], LEAD.index(s.split()[-1]) if s != "3 outs" else 0))
    return frame.loc[order]


def main() -> None:
    pd.set_option("display.width", 200)
    for team in sys.argv[1:] or list(LINEUPS):
        nine, order, cards, steals, names = build(team)
        before, after = propagate(order, cards, steals)
        for name, dist in (("BEFORE the 4th batter's PA resolves", before), ("AFTER the 4th batter's PA", after)):
            total = sum(dist.values())
            no_pa = sum(v for k, v in before.items() if k[0] == "over")
            mean = sum(v * (k[1] if k[0] == "over" else k[2]) for k, v in dist.items())
            print(f"\n===== {team}: {name}   (mass {total:.6f}; mean runs {mean:.3f}; "
                  f"P(no 4th PA) = {no_pa:.3f}); order {', '.join(n.split()[-1] for n in names)}")
            fmt = lambda x: f"{x:5.1f}" if x else "    ."
            print((100 * table(dist)).round(1).to_string(float_format=fmt))
            print("  -- compact: lead runner only --")
            print((100 * table(dist, with_outs=False)).round(1).to_string(float_format=fmt))
        print("(percent of first innings, by outs and the base of the lead runner)")


if __name__ == "__main__":
    main()
