"""Where does the saboteur lose? Two bad-but-legal managers vs B0, conventions off."""
import zlib, time, numpy as np
from wpbl import manager as M, play, engine
cards, wp = play.shared(); m = M.Model(cards, wp)

class WorstArm(M.Policy):
    def decide(self, g, side):
        if g.column(side.pitcher) != "gassed":
            return "keep"
        opts = M.options(g, side, self.model)
        if not opts:
            return "keep"
        def entering(o):
            return engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0]))
        pool = [o for o in opts if entering(o) != "gassed"] or opts
        o = max(pool, key=lambda o: self.model.runs_per_inning(o[0], entering(o)))
        return o[0] if o[1] is None else (o[0], M.lineup_text(o[1]))

class NeverRelieve(M.Policy):
    def decide(self, g, side):
        return "keep"

teams = ["BOS", "LAQ", "NYH", "SFF"]
for label, cls in (("worst arm, never gassed", WorstArm), ("never relieve", NeverRelieve)):
    t0 = time.time(); won = n = 0; used = []
    for me in teams:
        for opp in teams:
            if me == opp: continue
            for hi_me in (True, False):
                hi, lo = (me, opp) if hi_me else (opp, me)
                for k in range(100):
                    pol = {me: cls(m, me), opp: M.Baseline(m, opp)}
                    use = []
                    w, _ = M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()), use)
                    used += [u[2] for u in use if u[0] == me]
                    won += w == me; n += 1
    p = won / n
    print(f"{label:24s} series won {100*p:5.1f}% +/- {100*np.sqrt(p*(1-p)/n):.1f} of {n}; "
          f"pitchers per game {np.mean(used):.2f}  ({time.time()-t0:.0f}s)", flush=True)
