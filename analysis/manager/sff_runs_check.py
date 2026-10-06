"""Why SFF's Gutierrez-for-Day-Bedard swap (+0.35 exact runs) wins no more games:
SFF's runs scored and allowed on swap days, defaults vs swap, in the same 600
seeded series as easy_gains_series.py; and whether the swap survives the game.

    pixi run python analysis/manager/sff_runs_check.py
"""
import sys
import zlib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import easy_gains_series as S                            # noqa: E402  (patches starting_nine)
from wpbl import manager as M, play                       # noqa: E402

m, TEAM, IN, OUT = S.m, "SFF", "Samantha Gutierrez", "Ela Day Bedard"
GAMES = []
_run = play.Game.run


def run(self):
    start = {s.team: [x.name for x in s.order] for s in (self.away, self.home)}
    _run(self)
    me, opp = (self.away, self.home) if self.away.team == TEAM else (self.home, self.away)
    if me.team != TEAM:
        return
    end = me.batting()
    GAMES.append(dict(runs=me.runs, allowed=opp.runs, halves=len(me.line), opp_halves=len(opp.line),
                      won=me.runs > opp.runs, legal=None,
                      kept=(IN in end) if IN in start[TEAM] else (OUT in end),
                      dh_end=any(s.pos == "DH" for s in me.order)))


play.Game.run = run

for label, active in (("defaults", None), ("swap", TEAM)):
    S.ACTIVE = active
    GAMES.clear()
    legal = []
    for opp in S.TEAMS:
        if opp == TEAM:
            continue
        for hi_me in (True, False):
            hi, lo = (TEAM, opp) if hi_me else (opp, TEAM)
            for k in range(100):
                pol = {TEAM: M.Baseline(m, TEAM), opp: M.Baseline(m, opp)}
                S.LOG.clear()
                n0 = len(GAMES)
                M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{TEAM}{opp}{hi_me}{k}".encode()))
                mine = [e for e in S.LOG if e[0] == TEAM]
                for g, e in zip(GAMES[n0:], mine):
                    g["legal"] = e[2]
    for lg in (True, False):
        G = [g for g in GAMES if g["legal"] == lg]
        a = lambda k: np.array([g[k] for g in G], float)
        print(f"{label:8s} swap {'legal' if lg else 'not legal'}: {len(G)} games, won {100 * a('won').mean():.1f}%, "
              f"runs {a('runs').mean():.3f} (+/- {a('runs').std() / np.sqrt(len(G)):.3f}) per game, "
              f"{7 * a('runs').sum() / a('halves').sum():.3f} per 7 innings batted; "
              f"allowed {a('allowed').mean():.3f}, {7 * a('allowed').sum() / a('opp_halves').sum():.3f} per 7; "
              f"{'Gutierrez' if label == 'swap' else 'Day-Bedard'} still batting at the end {100 * a('kept').mean():.0f}%; "
              f"DH at the end {100 * a('dh_end').mean():.0f}%", flush=True)
