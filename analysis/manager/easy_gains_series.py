"""Confirm the easiest lineup gains (easy_gains.py) in series and in games.

Same 600 seeded best-of-5 series per team as lineup_cost.py, both sides B0,
conventions on. Pass "defaults": everyone plays the conventions nine. Pass
"swap": one team at a time makes its one-in change on every day it is legal
under 2+ starts (the best legal option if it has two); the opponents play the
defaults. Games are split by whether the swap applies that day -- in the
defaults pass too, so the same days are compared.

    pixi run python analysis/manager/easy_gains_series.py [series per pairing, default 100]
"""
import sys
import time
import zlib
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import easy_gains as E                                   # noqa: E402
from wpbl import manager as M                             # noqa: E402

m = E.m
TEAMS = ["BOS", "LAQ", "NYH", "SFF"]
SWAPS = {"BOS": [("Hyeonah Kim", "Gabrielle Haas")],
         "LAQ": [("Samaria Benitez", "Amira Hondras")],
         "NYH": [("Keira Izumi", "Val Perez"), ("Keira Izumi", "Madison Willan")],
         "SFF": [("Samantha Gutierrez", "Ela Day Bedard")]}

_swapped = {}


def swapped(team, starter, nine):
    """The nine with the team's best legal swap, or None if none is legal or gains."""
    key = (team, starter)
    if key in _swapped:
        return _swapped[key]
    home = {n: p for n, p in nine if p != "P"}
    two_way = len(home) < len(nine)
    base = E.runs([n for n, _ in nine])
    best = None
    for b, out in SWAPS[team]:
        if b == starter or b in dict(nine) or out not in home:
            continue
        players = [n for n in home if n != out] + [b]
        res = E.assign(players, list(home.values()), {n: p for n, p in home.items() if n != out}, "2+")
        if res is None:
            continue
        new = [(n, pos) for pos, n in res[1].items()] + ([(starter, "P")] if two_way else [])
        r = E.runs([n for n, _ in new])
        if r > base and (best is None or r > best[0]):
            best = (r, new)
    _swapped[key] = None if best is None else M._order(m, best[1])
    return _swapped[key]


ACTIVE = None
LOG = []                                                  # (team, starter, swap legal, swap used)
_orig = M.starting_nine


def starting_nine(model, team, starter):
    nine = _orig(model, team, starter)
    alt = swapped(team, starter, nine)
    use = team == ACTIVE and alt is not None
    LOG.append((team, starter, alt is not None, use))
    return alt if use else nine


M.starting_nine = starting_nine


def run(n_series):
    global ACTIVE
    out = {}
    for label in ["defaults"] + TEAMS:
        t0 = time.time()
        ACTIVE = None if label == "defaults" else label
        mes = TEAMS if label == "defaults" else [label]
        won, n = defaultdict(int), defaultdict(int)
        games = defaultdict(lambda: [0, 0])                    # (team, legal) -> [won, played]
        by_starter = defaultdict(lambda: [0, 0])               # (team, starter) -> [won, played]
        for me in mes:
            for opp in TEAMS:
                if opp == me:
                    continue
                for hi_me in (True, False):
                    hi, lo = (me, opp) if hi_me else (opp, me)
                    for k in range(n_series):
                        pol = {me: M.Baseline(m, me), opp: M.Baseline(m, opp)}
                        LOG.clear()
                        trace = []
                        w, played = M.series(m, hi, lo, pol, M.FINAL,
                                             zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()), trace=trace)
                        after = trace[1:] + [None]
                        for gi in range(played):
                            g_win = w if after[gi] is None else max(after[gi], key=lambda t: after[gi][t] - trace[gi][t])
                            for team, st, legal, _ in LOG[2 * gi: 2 * gi + 2]:
                                if team != me:
                                    continue
                                games[(me, legal)][0] += g_win == me
                                games[(me, legal)][1] += 1
                                by_starter[(me, st)][0] += g_win == me
                                by_starter[(me, st)][1] += 1
                        won[me] += w == me
                        n[me] += 1
        for me in mes:
            p = won[me] / n[me]
            g = {lg: games[(me, lg)] for lg in (True, False)}
            out[(label, me)] = (p, g)
            print(f"{label:8s} {me}: series {100 * p:5.1f}% +/- {100 * np.sqrt(p * (1 - p) / n[me]):.1f} of {n[me]}"
                  + "".join(f"   games, swap {'legal' if lg else 'not legal'}: "
                            f"{100 * a / max(b, 1):5.1f}% of {b}" for lg, (a, b) in g.items()), flush=True)
            print("           by starter: " + ", ".join(
                f"{st.split()[-1]} {100 * a / b:.1f}% of {b}" for (t, st), (a, b) in sorted(by_starter.items())
                if t == me), flush=True)
        print(f"    ({time.time() - t0:.0f}s)", flush=True)
    return out


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
