"""When should the best arms pitch? Read oracle.py's *_top3.csv: for each team's best
(rank 0) and second-best (rank 1) arm, every half-inning of every sampled game,
whether the oracle had her pitch it, against the circumstances: the stakes at the
half-inning's start, how tired she came into the game, the game's weight in the
series, and the inning.

    pixi run python analysis/manager/oracle_when.py oracle_top3.csv

Fatigue is her count on taking the mound in that game (30 more than her count
that morning): 0 or less is fully rested, 1-19 has used part of her fresh window,
20+ starts fading.
"""
import sys

import numpy as np
import pandas as pd

STAKES = [0, 0.3, 0.7, 1.0, 1.2, 1.5, 2.0, 99]
S_LAB = ["<0.3", "0.3-0.7", "0.7-1.0", "1.0-1.2", "1.2-1.5", "1.5-2.0", "2.0+"]
FAT = [-99, 0.5, 19.5, 999]
F_LAB = ["rested (0)", "part-used (1-19)", "fading (20+)"]

d = pd.read_csv(sys.argv[1])
d["band"] = pd.cut(d["stakes"], STAKES, labels=S_LAB, right=False)
d["fatigue"] = pd.cut(d["entering"], FAT, labels=F_LAB)
d["stage"] = pd.cut(d["inning"], [0, 3, 5, 7], labels=["innings 1-3", "4-5", "6-7"])
d["game weight"] = pd.cut(d["weight"], [0, 0.2, 0.4, 0.6], labels=["<0.2", "0.2-0.4", "0.4-0.6"])
pd.set_option("display.width", 200)


def table(sub, by):
    t = sub.groupby(["band", by], observed=False)["pitched"].mean().unstack()
    n = sub.groupby(by, observed=False).size()
    t.columns = [f"{c} (n {n[c]})" for c in t.columns]
    return t


for r, name in ((0, "best arm"), (1, "second-best arm")):
    sub = d[d["rank"] == r]
    print(f"\n=== {name}: chance the oracle has her pitch the half-inning ===")
    print(f"overall {sub['pitched'].mean():.2f} of {len(sub)} half-innings")
    for by in ("fatigue", "game weight", "stage"):
        print(f"\nby stakes and {by}:\n" + table(sub, by).to_string(float_format=lambda x: f"{x:.2f}"))

print("\n=== where the best two pitch half the time, by fatigue ===")
top = d[d["rank"] <= 1]
for f in F_LAB:
    s = top[top["fatigue"] == f]
    if len(s) < 50:
        continue
    curve = s.groupby("band", observed=False)["pitched"].mean()
    cross = next((b for b, v in curve.items() if v >= 0.5), None)
    print(f"  {f:18s} " + "  ".join(f"{b} {v:.2f}" for b, v in curve.items()) + f"   -> half the time from {cross}")
print("\nby team, best arm: chance she pitches, stakes under 0.7 / 0.7-1.2 / 1.2+")
for t, s in d[d["rank"] == 0].groupby("team"):
    lo = s[s["stakes"] < 0.7]["pitched"].mean()
    mid = s[(s["stakes"] >= 0.7) & (s["stakes"] < 1.2)]["pitched"].mean()
    hi = s[s["stakes"] >= 1.2]["pitched"].mean()
    print(f"  {t} {s['arm'].iloc[0]:18s} {lo:.2f} / {mid:.2f} / {hi:.2f}")
