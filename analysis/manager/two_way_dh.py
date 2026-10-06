"""Lineup questions 2 and 3, one team at a time against the defaults (B0, conventions on)."""
import zlib, time, numpy as np
from wpbl import manager as M, play, usage
cards, wp = play.shared(); m = M.Model(cards, wp); m.usage = usage.Usage(cards)
teams = ["BOS", "LAQ", "NYH", "SFF"]
fat = {n: -30 for n in cards.pitcher}
for t in teams:   # what the switch changes, for each role starter
    for st in sorted(m.usage.starters[t]):
        a, b = M.usage_nine(m, t, st, True), M.usage_nine(m, t, st, False)
        if a != b:
            print(f"{t} starter {st}: bats at P; if she sits, DH is "
                  f"{[n.split()[-1] for n, p in b if p == 'DH']}", flush=True)
for label in ("starter doesn't bat", "DH-aware relief"):
    t0 = time.time(); won = {t: 0 for t in teams}; n = {t: 0 for t in teams}; use_all = []
    for me in teams:
        m.starter_sits = {me} if label.startswith("starter") else set()
        for opp in teams:
            if me == opp: continue
            for hi_me in (True, False):
                hi, lo = (me, opp) if hi_me else (opp, me)
                for k in range(100):
                    mine = M.Baseline(m, me)
                    mine.dh_aware = label.startswith("DH")
                    pol = {me: mine, opp: M.Baseline(m, opp)}
                    use = []
                    w, _ = M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()), use)
                    use_all += [u for u in use if u[0] == me]
                    won[me] += w == me; n[me] += 1
    m.starter_sits = set()
    tot = sum(won.values()) / sum(n.values())
    u = np.array([u[4:] for u in use_all], float); dh = u[:, 0] == 1
    print(f"{label:20s} all {100*tot:5.1f}% +/- {100*np.sqrt(tot*(1-tot)/sum(n.values())):.1f}   "
          + "  ".join(f"{t} {100*won[t]/n[t]:5.1f}%" for t in teams) + f"   ({time.time()-t0:.0f}s)", flush=True)
    print(f"    games with a DH at the start {100*dh.mean():.0f}%; of those, DH lost {100*(1-u[dh,1]).mean():.0f}%;"
          f" relievers from the lineup per game {u[:,2].mean():.2f}", flush=True)
