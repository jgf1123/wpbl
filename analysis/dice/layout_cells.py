"""Lay the real cards into 35 pitcher cells and 58 batter cells. Does anything break?

    pixi run python analysis/dice/layout_cells.py

The table: 00-34 the pitcher's card, 35-39 double, 40-41 error, 42-99 the
batter's. Each card spreads its own block over the six tree lines by largest
remainder, so the blocks are whole cells.

Two things can go wrong and both matter at the table:

  a line disappears   a line rounding to zero cells on BOTH cards has
                      probability zero for that matchup -- it cannot happen at
                      all, which no amount of smoothing intended. The 1% floor
                      used to prevent this; in cells the equivalent is that the
                      two blocks together must give every line at least one.
  the mix drifts      35/93 is 0.3763 in the aggregate, but each card is rounded
                      separately, so the realised weight per matchup is not
                      exactly that.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import CARD_LINES, bands, cards, plate_appearances

pd.set_option("display.width", 240)
P_CELLS, B_CELLS = 35, 58
TREE = [l for l in CARD_LINES if l not in ("2B", "ROE")]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
bd = bands(pa)
B, P = cards("B"), cards("P")
IXT = [CARD_LINES.index(l) for l in TREE]


def to_cells(card, total):
    """Largest remainder: whole cells summing to `total`, over the six tree lines."""
    p = card[:, IXT]
    p = p / p.sum(axis=1, keepdims=True)
    exact = p * total
    cells = np.floor(exact).astype(int)
    rem = exact - cells
    for i in range(len(cells)):
        short = total - cells[i].sum()
        if short:
            for j in np.argsort(-rem[i])[:short]:
                cells[i, j] += 1
    return cells


pc = to_cells(P.to_numpy(), P_CELLS)
bc = to_cells(B.to_numpy(), B_CELLS)
print(f"pitcher block {P_CELLS} cells, batter block {B_CELLS}, "
      f"2B {round(100 * bd['2B'])} cells, ROE {round(100 * bd['ROE'])} cells\n")

print("=== lines that round to zero cells ===")
for who, cel, ids in (("pitchers", pc, P.index), ("batters", bc, B.index)):
    z = (cel == 0)
    print(f"  {who}: {int(z.sum())} zero entries across {len(cel)} cards")
    for j, l in enumerate(TREE):
        if z[:, j].any():
            print(f"    {l}: zero on {int(z[:, j].sum())} cards, e.g. "
                  + ", ".join(str(nm.get(ids[i], ids[i])) for i in np.flatnonzero(z[:, j])[:3]))

print("\n=== can a line vanish from a whole matchup? ===")
worst = []
for i in range(len(bc)):
    tot = bc[i][None, :] + pc                      # every pitcher against this batter
    gone = (tot == 0)
    if gone.any():
        for j in np.flatnonzero(gone.any(axis=0)):
            for k in np.flatnonzero(gone[:, j]):
                worst.append((nm.get(B.index[i], B.index[i]),
                              nm.get(P.index[k], P.index[k]), TREE[j]))
print(f"  matchups where some line has zero cells on both cards: {len(worst)}"
      f" of {len(bc) * len(pc)}")
for w in worst[:8]:
    print(f"    {w[0]} vs {w[1]}: no {w[2]}")

print("\n=== how far the cell table drifts from the intended mixture ===")
alpha = P_CELLS / (P_CELLS + B_CELLS)
lvl = {l: bd[l] for l in ("2B", "ROE")}
rows = []
for j, l in enumerate(TREE):
    exact, celled = [], []
    for i in range(len(bc)):
        pt = (1 - sum(lvl.values()))
        ex = pt * (alpha * (P.to_numpy()[:, IXT][:, j] / P.to_numpy()[:, IXT].sum(axis=1))
                   + (1 - alpha) * (B.to_numpy()[i, IXT][j] / B.to_numpy()[i, IXT].sum()))
        ce = (pc[:, j] + bc[i, j]) / 100.0
        exact.append(ex)
        celled.append(ce)
    e, c = np.concatenate(exact), np.concatenate(celled)
    rows.append({"line": l, "exact mean %": round(100 * e.mean(), 2),
                 "celled mean %": round(100 * c.mean(), 2),
                 "mean |drift| pts": round(100 * np.abs(c - e).mean(), 3),
                 "worst |drift| pts": round(100 * np.abs(c - e).max(), 2)})
print(pd.DataFrame(rows).to_string(index=False))
print(f"\nrealised weight on the pitcher: {100 * alpha:.2f}% of the tree, "
      f"{P_CELLS}/{P_CELLS + B_CELLS} cells")
