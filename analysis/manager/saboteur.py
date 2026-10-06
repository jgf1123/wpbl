"""Range of bullpen management: a saboteur that minimises its own WP each PA, vs B0."""
import zlib, numpy as np
from wpbl import manager, play
cards, wp = play.shared(); m = manager.Model(cards, wp)

class Saboteur(manager.Shadow):
    def decide(self, g, side):
        worst = self.value(g, side, side.pitcher, g.fatigue[side.pitcher], False, None); choice = "keep"
        for name, lineup, after in manager.options(g, side, m):
            v = self.value(g, side, name, g.fatigue[name], True, after)
            if v < worst - 1e-9:
                worst, choice = v, (name if lineup is None else (name, manager.lineup_text(lineup)))
        return choice

teams = ["BOS", "LAQ", "NYH", "SFF"]; won = n = 0
for me in teams:
    for opp in teams:
        if me == opp: continue
        for hi_me in (True, False):
            hi, lo = (me, opp) if hi_me else (opp, me)
            for k in range(50):
                pol = {me: Saboteur(m, me, 0.0), opp: manager.Baseline(m, opp)}
                w, _ = manager.series(m, hi, lo, pol, manager.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()))
                won += w == me; n += 1
p = won / n
print(f"saboteur series won {100*p:.1f}% +/- {100*np.sqrt(p*(1-p)/n):.1f} of {n}")
