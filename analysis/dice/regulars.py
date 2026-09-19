"""The 20 players with 17+ games: where their batting lines differ most from league,
by z-score and by run effect, and what the four-step card does to them."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("regulars.py", "trees_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
pd.set_option("display.width", 250)

REGULARS = ["Ashton Lansdell", "Jamie Mackay", "Amanda Gianelloni", "Andreanne Leblanc", "Joely Leguizamon",
            "Kelsie Whitmore", "Denae Benites", "Jua Park", "Maggie Foxx", "Mo'ne Davis", "Natsuki Yonetani",
            "Sarah Edwards", "Skylar Kaplan", "Alexia Jorge", "Amira Hondras", "Caitlin Eynon", "Diana Ibarra",
            "Kylee Lahners", "Samaria Benitez", "Ticara Geldenhuis"]
LABEL = {"K": "K", "BB": "BB", "HBP": "HBP", "HR": "HR", "1B": "1B", "2B": "2B", "ROE": "ROE", "OUT": "out in play"}

X = counts(pa, "B")
n = X.sum(axis=1)
L = X.sum(axis=0) / X.sum()                      # league rate per line (all training PAs)
w_avg = float(L @ w)                             # run value of an average PA
coh = all_cohorts("B", X)
C = child_counts(X, SETUPS["4-step"])
T = targets(C, coh, HR_STEP["4-step"])
cd = card(C, T, [32, 64, 45, 11], SETUPS["4-step"])
names = [name.get(i, i) for i in people["B"]]

rows, zt, rt = [], {}, {}
for nm in REGULARS:
    i = names.index(nm)
    p = X[i] / n[i]
    z = (p - L) / np.sqrt(L * (1 - L) / n[i])
    runs = (p - L) * (w - w_avg)                  # sums to her total runs above average per PA
    cruns = (cd[i] - L) * (w - w_avg)
    jz, jr, jc = int(np.argmax(np.abs(z))), int(np.argmax(np.abs(runs))), int(np.argmax(np.abs(cruns - runs)))
    zt[nm] = z
    rt[nm] = 1000 * runs
    rows.append({"player": nm, "PA": int(n[i]),
                 "most extreme (z)": f"{LABEL[ALL[jz]]} {100 * p[jz]:.1f}% vs {100 * L[jz]:.1f} (z {z[jz]:+.1f})",
                 "biggest run effect": f"{LABEL[ALL[jr]]} {1000 * runs[jr]:+.0f}",
                 "raw total": round(1000 * runs.sum()), "card total": round(1000 * cruns.sum()),
                 "card changes most": f"{LABEL[ALL[jc]]} {100 * p[jc]:.1f}->{100 * cd[i, jc]:.1f}% ({1000 * (cruns[jc] - runs[jc]):+.0f})"})
out = pd.DataFrame(rows).sort_values("raw total", ascending=False)
print(f"league rates %: " + ", ".join(f"{LABEL[l]} {100 * L[j]:.1f}" for j, l in enumerate(ALL)))
print(f"run value above an average PA: " + ", ".join(f"{LABEL[l]} {w[j] - w_avg:+.2f}" for j, l in enumerate(ALL)))
print("\n=== 20 regulars (runs above average per PA x1000; training games, G3 excluded) ===")
print(out.to_string(index=False))

print("\n=== z-score by line ===")
print(pd.DataFrame(zt, index=[LABEL[l] for l in ALL]).T.loc[out["player"]].round(1).to_string())
print("\n=== run effect by line (x1000 per PA) ===")
print(pd.DataFrame(rt, index=[LABEL[l] for l in ALL]).T.loc[out["player"]].round(0).to_string())
zz = pd.DataFrame(zt, index=ALL).T
print("\nhow often each line is a player's most extreme:", zz.abs().idxmax(axis=1).map(LABEL).value_counts().to_dict())
print("lines with |z| >= 2 across the 20:", {LABEL[l]: int((zz[l].abs() >= 2).sum()) for l in ALL},
      f"(by chance alone expect about {0.046 * 20:.1f} per line)")
