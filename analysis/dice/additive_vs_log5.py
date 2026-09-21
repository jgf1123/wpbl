"""How far is the additive shortcut from log5, per card line?

    pixi run python analysis/dice/additive_vs_log5.py

At the table you cannot multiply and renormalise, so the candidate shortcut is

    p = batter rate + pitcher rate - league rate

which already sums to 100% across the seven lines (1 + 1 - 1). The question is
how far it drifts from flat log5 (p proportional to B*P/L, renormalised), which
is the rule the spec evaluates matchups with.

Reported in percentage points, i.e. cells of a d100 roll, because that is the
unit the error has to be judged in: an error under half a cell cannot change a
roll's outcome, and one over a cell will.
"""
import numpy as np
import pandas as pd

from wpbl.dice import CARD_LINES, LINES, cards, plate_appearances
from wpbl import tables

pd.set_option("display.width", 230)
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
L = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
lvec = np.array([L["BB"] + L["HBP"] if l == "FP" else L[l] for l in CARD_LINES])

B, _ = cards("B")
P, _ = cards("P")
bm, pm = B.to_numpy(), P.to_numpy()
bn = pa.groupby("B").size().reindex(B.index).fillna(0).to_numpy()
pn = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy()

log5 = bm[:, None, :] * pm[None, :, :] / lvec                 # batters x pitchers x lines
log5 /= log5.sum(axis=2, keepdims=True)
add = bm[:, None, :] + pm[None, :, :] - lvec
diff = 100 * (add - log5)                                     # percentage points

print(f"{len(B)} batters x {len(P)} pitchers = {len(B) * len(P)} matchups, "
      f"{pa['game_id'].nunique()} games")
real = (bn[:, None] >= 25) & (pn[None, :] >= 25)
print(f"of which {int(real.sum())} pair a 25+ PA batter with a 25+ BF pitcher\n")

rows = []
for j, line in enumerate(CARD_LINES):
    d, dr = diff[:, :, j], diff[:, :, j][real]
    i = np.unravel_index(np.abs(d).argmax(), d.shape)
    rows.append({"line": line, "league %": round(100 * lvec[j], 1),
                 "max |error| all pairs": round(np.abs(d).max(), 2),
                 "worst pair": f"{nm.get(B.index[i[0]], '?')} vs {nm.get(P.index[i[1]], '?')}",
                 "max |error| 25+ only": round(np.abs(dr).max(), 2),
                 "95th pct": round(np.percentile(np.abs(dr), 95), 2),
                 "median": round(np.median(np.abs(dr)), 2)})
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== where the additive rule goes negative or over 100% ===")
for j, line in enumerate(CARD_LINES):
    bad = (add[:, :, j] < 0).sum()
    if bad:
        print(f"  {line}: negative in {bad} of {add.shape[0] * add.shape[1]} matchups "
              f"(most negative {100 * add[:, :, j].min():.2f}%)")

print("\n=== K and FP: what drives the error? ===")
for line in ("K", "FP", "HR"):
    j = CARD_LINES.index(line)
    d = diff[:, :, j]
    bq = np.argsort(bm[:, j])
    pq = np.argsort(pm[:, j])
    lo_b, hi_b = bq[:len(bq) // 4], bq[-len(bq) // 4:]
    lo_p, hi_p = pq[:len(pq) // 4], pq[-len(pq) // 4:]
    print(f"\n  {line}: additive minus log5, percentage points")
    grid = pd.DataFrame(
        [[round(d[np.ix_(rb, rp)].mean(), 2) for rp in (lo_p, hi_p)] for rb in (lo_b, hi_b)],
        index=["batter low quartile", "batter high quartile"],
        columns=["pitcher low quartile", "pitcher high quartile"])
    print(grid.to_string())

print("\n=== a correction table: additive error by pitcher rate, for extreme batters ===")
for line, who in (("HR", ["Denae Benites", "Kelsie Whitmore"]),
                  ("K", ["Joely Leguizamon", "Andreanne Leblanc"]),
                  ("FP", ["Ashton Lansdell", "Maggie Foxx"])):
    j = CARD_LINES.index(line)
    print(f"\n  {line} (league {100 * lvec[j]:.1f}%)")
    band = np.floor(100 * pm[:, j]).astype(int)
    for w in who:
        i = list(B.index).index(next(k for k, v in nm.items() if v == w))
        cells = []
        for b in sorted(set(band[pn >= 25])):
            sel = (band == b) & (pn >= 25)
            if sel.sum():
                cells.append(f"P={b}%: {diff[i, sel, j].mean():+.1f}")
        print(f"    {w:20s} card {100 * bm[i, j]:4.1f}%  " + "  ".join(cells))
