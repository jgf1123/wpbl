"""Which reservation wins more series? B0 in-game for everyone; the opponent uses the blanket ban."""
import zlib, time, numpy as np
from wpbl import manager as M, play, usage
cards, wp = play.shared(); m = M.Model(cards, wp); m.usage = usage.Usage(cards)
teams = ["BOS", "LAQ", "NYH", "SFF"]
for mode in ("ban", "guaranteed", "next"):
    t0 = time.time(); won = n = 0; brink = brink_won = 0
    for me in teams:
        for opp in teams:
            if me == opp: continue
            for hi_me in (True, False):
                hi, lo = (me, opp) if hi_me else (opp, me)
                for k in range(100):
                    mine = M.Baseline(m, me); mine.reserve = mode
                    pol = {me: mine, opp: M.Baseline(m, opp)}
                    tr = []
                    w, _ = M.series(m, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()), trace=tr)
                    won += w == me; n += 1
                    # on the brink with a next game possible: trailing 0-2 or 1-2 before a game
                    if any(r[opp] == 2 and r[me] < 2 for r in tr):
                        brink += 1; brink_won += w == me
    p, q = won / n, brink_won / max(brink, 1)
    print(f"{mode:11s} series won {100*p:5.1f}% +/- {100*np.sqrt(p*(1-p)/n):.1f} of {n};  "
          f"after facing elimination with a next game possible: {100*q:5.1f}% +/- "
          f"{100*np.sqrt(q*(1-q)/max(brink,1)):.1f} of {brink}  ({time.time()-t0:.0f}s)", flush=True)
