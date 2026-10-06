"""What one arm is worth: series win% with her unable to pitch, both sides B0."""
import zlib, time, numpy as np
from wpbl import manager as M, play
cards, wp = play.shared(); m = M.Model(cards, wp)
teams = ["BOS", "LAQ", "NYH", "SFF"]

def best(team, deep):
    pool = [n for n in M.arms(m, team) if (cards.stamina(n) >= 70) == deep]
    return min(pool, key=lambda n: m.runs_per_inning(n, "fading"))

reliever = {t: best(t, False) for t in teams}
ace = {t: best(t, True) for t in teams}
for t in teams:
    print(f"{t}: best reliever {reliever[t]} (stamina {cards.stamina(reliever[t])}, "
          f"{m.runs_per_inning(reliever[t], 'fading'):.3f} R/inn)   ace {ace[t]} "
          f"(stamina {cards.stamina(ace[t])}, {m.runs_per_inning(ace[t], 'fading'):.3f})", flush=True)

def run(removed, label):
    t0 = time.time(); won = {t: 0 for t in teams}; n = {t: 0 for t in teams}
    for me in teams:
        saved = set(M.DISFAVORED)
        if removed: M.DISFAVORED.add(removed[me])
        M.best_nine.cache_clear()
        for opp in teams:
            if opp == me: continue
            for hi_me in (True, False):
                hi, lo = (me, opp) if hi_me else (opp, me)
                for k in range(100):
                    pol = {me: M.Baseline(m, me), opp: M.Baseline(m, opp)}
                    w, _ = M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()))
                    won[me] += w == me; n[me] += 1
        M.DISFAVORED.clear(); M.DISFAVORED.update(saved)
    tot = sum(won.values()) / sum(n.values())
    print(f"{label:22s} all {100*tot:5.1f}% +/- {100*np.sqrt(tot*(1-tot)/sum(n.values())):.1f}   " +
          "  ".join(f"{t} {100*won[t]/n[t]:5.1f}%" for t in teams) + f"   ({time.time()-t0:.0f}s)", flush=True)

run(None, "full staff")
run(reliever, "without best reliever")
run(ace, "without ace")
