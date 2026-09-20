"""Figure 1 of the blog: how much prediction error each step's k costs.

    pixi run python analysis/dice/fig_k_curve.py [out.png]

Reuses the sweep in `sharpness.py`: for every step of the batter card, error on
held-out games as k moves off its best value. The two steps that divide up balls
in play rise steeply when smoothed less; the rest are nearly flat, which is
the point the figure is making.
"""
import sys
from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import pandas as pd

from wpbl.parse import DATA_DIR

CSV = Path(__file__).parent / "k_curves.csv"
if not CSV.exists():
    sys.exit(f"{CSV} is missing: run analysis/dice/sharpness.py first")
CURVES = {(r.structure, int(r.step)): (r.split, r.best, c.drop(columns=["structure", "step"]))
          for (r_, c) in pd.read_csv(CSV).groupby(["structure", "step"])
          for r in [c.iloc[0]]}

INK, MUTED, GRID = "#222222", "#666666", "#e4e4e4"
HILITE = ["#1b6ca8", "#c2410c"]          # the two in-play steps
IN_PARK = {4, 5}                          # step indexes (0-based) worth colour
YMAX = 3000

out = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_DIR / "img" / "dice_k_curve.png"
out.parent.mkdir(parents=True, exist_ok=True)

fig, ax = plt.subplots(figsize=(7.28, 4.4), dpi=200)
hi = 0
for (m, s), (nm, bk, cur) in sorted(CURVES.items(), key=lambda kv: kv[0][1] in IN_PARK):
    fin = cur[cur["k"] != "inf"]
    x = np.array([float(v) for v in fin["k"]])
    yv = fin["rise"].to_numpy()
    if s in IN_PARK:
        color = HILITE[hi]
        hi += 1
        pretty = "no limit (use the cohort)" if str(bk) == "inf" else f"k = {float(bk):g}"
        ax.plot(x, yv, color=color, linewidth=2.2, zorder=3,
                label=f"{nm.replace('OUT', 'out')}   best: {pretty}")
        kb = float(bk) if str(bk) != "inf" else x[-1]
        ax.plot([kb], [0], marker="o", ms=5, color=color, zorder=4)
    else:
        ax.plot(x, yv, color="#b9b9b9", linewidth=1.3, zorder=2)

ax.annotate("the other five steps: a wide\nrange of k does about as well",
            xy=(96, 30), xytext=(160, 1050), fontsize=8.5, color=MUTED,
            arrowprops=dict(arrowstyle="-", color=MUTED, linewidth=0.8))
ax.set_xscale("log", base=2)
ax.set_xticks([1, 4, 16, 64, 256, 1024])
ax.set_xticklabels(["1", "4", "16", "64", "256", "1024"])
ax.set_xlim(1, 2048)
ax.set_ylim(0, YMAX)
ax.set_xlabel("k, phantom plate appearances added at the cohort's rates",
              fontsize=9, color=INK, labelpad=16)
ax.text(0.0, -0.10, "← copy her own record", transform=ax.transAxes, ha="left",
        fontsize=8.5, color=MUTED)
ax.text(1.0, -0.10, "use the cohort →", transform=ax.transAxes, ha="right",
        fontsize=8.5, color=MUTED)
ax.set_ylabel("Extra error on unseen games\n(runs per PA x 1e-6, 0 = best)",
              fontsize=9, color=INK)
ax.tick_params(labelsize=8.5, colors=INK)
ax.yaxis.grid(True, color=GRID, linewidth=0.8)
ax.set_axisbelow(True)
for side in ("top", "right", "left"):
    ax.spines[side].set_visible(False)
ax.spines["bottom"].set_color(GRID)
fig.suptitle("One choice on a batter's card is sharp", x=0.02, ha="left",
             fontsize=12, color=INK, y=0.985)
fig.text(0.02, 0.935, "How the balls she puts in play divide up needs heavy smoothing: trusting "
         "her own record costs far more than\nover-smoothing does. Both coloured curves run off the "
         "top of the axis, reaching about 4,900 at k = 1.",
         ha="left", va="top", fontsize=8.5, color=MUTED)
ax.legend(loc="upper right", fontsize=8.5, frameon=False)
fig.tight_layout(rect=(0, 0.03, 1, 0.90))
fig.savefig(out)
plt.close(fig)
print(f"-> {out}")
