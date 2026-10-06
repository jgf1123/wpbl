"""Runs per inning a league lineup scores off each team's arms, fresh / fading / gassed.

    pixi run python analysis/manager/card_spread.py
"""
from wpbl import manager as M, play
cards, wp = play.shared(); m = M.Model(cards, wp)
lg = m.runs_per_inning  # noqa
print("runs per inning off each arm, league lineup: fresh / fading / gassed")
for t in ["BOS", "LAQ", "NYH", "SFF"]:
    rows = [(n, *[m.runs_per_inning(n, c) for c in ("fresh", "fading", "gassed")]) for n in M.arms(m, t)]
    rows.sort(key=lambda r: r[2])
    best, worst = rows[0], rows[-1]
    g = [r[3] - r[1] for r in rows]
    print(f"{t}: best {best[0].split()[-1]} {best[1]:.2f}/{best[2]:.2f}/{best[3]:.2f}   worst {worst[0].split()[-1]} "
          f"{worst[1]:.2f}/{worst[2]:.2f}/{worst[3]:.2f}   fading spread {worst[2]-best[2]:.2f}   "
          f"fresh->gassed per arm {min(g):.2f}-{max(g):.2f}")
