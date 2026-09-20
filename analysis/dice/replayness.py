"""How close to the 2026 season lines are the 8-line cards vs 7-line (S2) cards split at the league BB:HBP ratio?"""
import numpy as np
import pandas as pd
_here = __file__
__file__ = _here.replace("replayness.py", "freepass_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("# ---------------- 1. best k")])
__file__ = _here
K8 = [2 ** 5.5, 2, 2 ** 2.5, 16, 64, 256, 16]
K7 = [2 ** 5.5, 8, 2 ** 3.5, 2 ** 5.5, 2 ** 7.5, 32]
c8 = full_card("B", "8", C8, K8)
c7 = full_card("B", "7", S2, K7)
use("8")
X = counts(pa, "B")
n = X.sum(axis=1)
raw = X / np.maximum(n[:, None], 1)
hbp_share = X[:, 2].sum() / (X[:, 1].sum() + X[:, 2].sum())
fp = c7[:, 1]
c7s = np.column_stack([c7[:, 0], fp * (1 - hbp_share), fp * hbp_share, c7[:, 2:]])   # back to 8 lines
REG = ["Denae Benites", "Ashton Lansdell", "Kelsie Whitmore", "Alexia Jorge", "Andreanne Leblanc", "Skylar Kaplan",
       "Natsuki Yonetani", "Kylee Lahners", "Caitlin Eynon", "Jua Park", "Jamie Mackay", "Ticara Geldenhuis",
       "Sarah Edwards", "Maggie Foxx", "Samaria Benitez", "Amanda Gianelloni", "Diana Ibarra", "Amira Hondras",
       "Joely Leguizamon", "Mo'ne Davis"]
nm = [name.get(i, i) for i in people["B"]]
idx = [nm.index(r) for r in REG]
print(f"league HBP share of free passes: {hbp_share:.1%}")
for label, cd in (("8-line cards", c8), ("7-line S2, league split", c7s)):
    gap = np.abs(cd[idx] - raw[idx]) * 100
    print(f"\n{label}: average |card - season| over the 20 regulars, percentage points")
    print("  BB {:.2f}  HBP {:.2f}  all 8 lines {:.2f}".format(gap[:, 1].mean(), gap[:, 2].mean(), gap.mean()))
    reg = n >= 25
    L = X.sum(axis=0) / X.sum()
    val = (cd - L) @ (W8 - L @ W8)
    print(f"  spread of card value among batters with 25+ PA: {1000 * val[reg].std(ddof=1):.0f} (season lines {1000 * ((raw - L) @ (W8 - L @ W8))[reg].std(ddof=1):.0f})")
print("\nBB / HBP % for players with distinctive mixes: season | 8-line card | 7-line league split")
for r in ("Alexia Jorge", "Kylee Lahners", "Kelsie Whitmore", "Maggie Foxx", "Diana Ibarra", "Andreanne Leblanc"):
    i = nm.index(r)
    print(f"  {r:17s} {100 * raw[i, 1]:4.1f} / {100 * raw[i, 2]:4.1f} | {100 * c8[i, 1]:4.1f} / {100 * c8[i, 2]:4.1f} | {100 * c7s[i, 1]:4.1f} / {100 * c7s[i, 2]:4.1f}")
