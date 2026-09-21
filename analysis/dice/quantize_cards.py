"""Rounding a card to whole d100 cells, and closing log5's sum-to-100 gap.

    pixi run python analysis/dice/quantize_cards.py

A. A card must become 100 integer cells. Four rules are compared:
     largest remainder   the classic: give the 100th cells to the biggest leftovers
     min worst absolute  minimise the largest error in cells
     min worst relative  minimise the largest error as a share of the line
     out absorbs         round the six, give OUT whatever is left
   Each is scored on worst absolute error, worst relative error, and the run
   value it costs -- the last being the project's usual standard.

B. Flat log5 multiplies then renormalises, which nobody can do at a table.
   Using B*P/L unnormalised leaves a sum that misses 100. This measures the gap
   and what it costs to hand the shortfall to OUT.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import neutral_values, plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, LINES, cards, plate_appearances

pd.set_option("display.width", 230)
pa = plate_appearances()
L = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
lvec = np.array([L["BB"] + L["HBP"] if l == "FP" else L[l] for l in CARD_LINES])

# run value of each card line, averaged over the season, free passes pooled
from wpbl import dice as _dice                                          # noqa: E402
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(_dice.TO_LINE).fillna("OUT")
lw.loc[lw["line"].isin(["BB", "HBP"]), "line"] = "FP"
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
print("run value per card line: " + ", ".join(f"{l} {v:+.3f}" for l, v in zip(CARD_LINES, W)))
OUT_I = CARD_LINES.index("OUT")


def largest_remainder(p, protect=None):
    cells = np.floor(p * 100).astype(int)
    rem = p * 100 - cells
    for i in np.argsort(-rem)[:100 - cells.sum()]:
        cells[i] += 1
    return cells


def best_by(p, cost):
    """Exhaustive over the few cell vectors reachable by moving 1-2 cells."""
    base = largest_remainder(p)
    best, score = base, cost(base, p)
    for i in range(len(p)):
        for j in range(len(p)):
            if i == j:
                continue
            for step in (1, 2):
                c = base.copy()
                if c[j] - step < 1:
                    continue
                c[i] += step
                c[j] -= step
                s = cost(c, p)
                if s < score:
                    best, score = c, s
    return best


def out_absorbs(p):
    cells = np.round(p * 100).astype(int)
    cells[OUT_I] += 100 - cells.sum()
    return cells


RULES = {
    "largest remainder": largest_remainder,
    "min worst absolute": lambda p: best_by(p, lambda c, q: np.abs(c - 100 * q).max()),
    "min worst relative": lambda p: best_by(p, lambda c, q: (np.abs(c - 100 * q) / (100 * q)).max()),
    "out absorbs": out_absorbs,
}

print("=== A. rounding a card to 100 cells ===")
for side, label in (("B", "batters"), ("P", "pitchers")):
    C, _ = cards(side)
    rows = []
    for name, rule in RULES.items():
        absd, reld, runs, outhit = [], [], [], []
        for p in C.to_numpy():
            c = rule(p)
            assert c.sum() == 100 and c.min() >= 1, (name, c)
            e = c - 100 * p
            absd.append(np.abs(e).max())
            reld.append((np.abs(e) / (100 * p)).max())
            runs.append(abs(float((c / 100 - p) @ W)))
            outhit.append(abs(e[OUT_I]) >= np.abs(e).max() - 1e-9)
        rows.append({"rule": name, "worst |cells|": round(max(absd), 2),
                     "mean worst |cells|": round(np.mean(absd), 3),
                     "worst relative": f"{max(reld):.0%}",
                     "worst runs/PA x1000": round(1000 * max(runs), 2),
                     "mean runs/PA x1000": round(1000 * np.mean(runs), 3),
                     "OUT takes the hit": f"{np.mean(outhit):.0%}"})
    print(f"\n{label} ({len(C)} cards):")
    print(pd.DataFrame(rows).to_string(index=False))

print("\n\n=== B. log5 without renormalising: how far off 100 is the sum? ===")
B, _ = cards("B")
P, _ = cards("P")
raw = B.to_numpy()[:, None, :] * P.to_numpy()[None, :, :] / lvec
S = raw.sum(axis=2)
print(f"  sum of B*P/L over the seven lines: min {100 * S.min():.1f}%, "
      f"median {100 * np.median(S):.1f}%, max {100 * S.max():.1f}%")
q = raw / S[:, :, None]                                   # proper flat log5
alt = raw.copy()
alt[:, :, OUT_I] = 1 - (raw.sum(axis=2) - raw[:, :, OUT_I])
print(f"  giving the shortfall to OUT, OUT lands between {100 * alt[:, :, OUT_I].min():.1f}% "
      f"and {100 * alt[:, :, OUT_I].max():.1f}%")
d = 100 * (alt - q)
rows = []
for j, line in enumerate(CARD_LINES):
    rows.append({"line": line, "max |cells| vs true log5": round(np.abs(d[:, :, j]).max(), 2),
                 "95th pct": round(np.percentile(np.abs(d[:, :, j]), 95), 2),
                 "median": round(np.median(np.abs(d[:, :, j])), 2)})
print(pd.DataFrame(rows).to_string(index=False))
runs = np.abs((alt - q) @ W)
print(f"  cost in run value: worst {1000 * runs.max():.1f}, "
      f"median {1000 * np.median(runs):.2f} (x1000 per PA)")
neg = (alt[:, :, OUT_I] < 0).sum()
print(f"  matchups where OUT would go negative: {neg} of {alt.shape[0] * alt.shape[1]}")
