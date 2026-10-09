"""Each team's run environment in the default series: runs scored and allowed
per game, game win %, and how often each pitcher starts. The inputs for
Pythagenpat and the starter-day weights in lineup_value.py.

Same 2,400 seeded best-of-5 series as lineup_cost.py, both B0, conventions on.

    pixi run python analysis/manager/team_runs.py
"""
import zlib
from collections import Counter, defaultdict

from wpbl import manager as M, play, usage

cards, wp = play.shared()
m = M.Model(cards, wp)
m.usage = usage.Usage(cards)
TEAMS = ["BOS", "LAQ", "NYH", "SFF"]
rec = defaultdict(lambda: [0, 0, 0, 0])            # team -> [runs, allowed, games, won]
starts = defaultdict(Counter)                      # team -> starter -> games
_run = play.Game.run


def run(self):
    _run(self)
    for me, opp in ((self.away, self.home), (self.home, self.away)):
        r = rec[me.team]
        r[0] += me.runs
        r[1] += opp.runs
        r[2] += 1
        r[3] += me.runs > opp.runs
        starts[me.team][me.used[0]] += 1


play.Game.run = run

# each series once, under the (team, opponent, side) seeds lineup_cost.py uses for "me"
for me in TEAMS:
    for opp in TEAMS:
        if opp == me:
            continue
        for hi_me in (True, False):
            hi, lo = (me, opp) if hi_me else (opp, me)
            for k in range(100):
                pol = {me: M.Baseline(m, me), opp: M.Baseline(m, opp)}
                M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()))

for t in TEAMS:
    runs, allowed, games, won = rec[t]
    print(f"{t}: {games} games, runs {runs / games:.3f}, allowed {allowed / games:.3f}, won {100 * won / games:.1f}%")
    print("    starts: " + ", ".join(f"{n} {c} ({100 * c / games:.1f}%)" for n, c in starts[t].most_common()))
