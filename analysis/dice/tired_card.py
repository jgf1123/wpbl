"""What a tired pitcher's card looks like: the size and the shape.

    pixi run python analysis/dice/tired_card.py

SIZE comes from the measured step -- about +0.09 runs per batter faced once she is
past her first inning (spec 7.2). One cell of her block is 1/94 of the plate
appearances that resolve, not 1/33: her block is only 35% of them, the rest being
the batter's block and the bands. So a cell is worth about 0.013 runs and the step
needs six or seven of them.

SHAPE comes from semifinal G3, the only game played with genuinely spent bullpens.
Restricted to the lines a pitcher's card actually carries -- 2B and ROE are fixed
bands and cannot move -- strikeouts fall and home runs and free passes rise.

The tired column is the fresh one shifted toward the G3 mix and scaled to hit the
target, then rounded to whole cells with the same rule the cards use.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (CARD_LINES, PA_CELLS, P_CELLS, TO_LINE, TREE_LINES,
                       league_card, line_weights, plate_appearances, to_cells)

pd.set_option("display.width", 215)
TARGET = 0.09
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES)
Wt = W.reindex(TREE_LINES).to_numpy()

pa = plate_appearances()
lg = league_card(pa)
fresh_p = lg.reindex(TREE_LINES).to_numpy()
fresh_p = fresh_p / fresh_p.sum()

# G3's mix, over the same six lines
allp = tables.read("plays", "all")
trn = tables.read("plays", "training")
excl = set(allp["game_id"].unique()) - set(trn["game_id"].unique())
g3 = allp[allp["game_id"].isin(excl)]
g3 = g3[(g3["play_kind"] == "plate_appearance") & (g3["outs_before"] < 3)]
g3_line = pd.Series([TO_LINE.get(e, "OUT") for e in g3["event_type"]])
g3_p = g3_line.value_counts(normalize=True).reindex(TREE_LINES).fillna(0).to_numpy()
g3_p = g3_p / g3_p.sum()

print("league pitcher card against the spent-bullpen game, over her six printed lines:\n")
print(pd.DataFrame({"line": TREE_LINES, "league %": (100 * fresh_p).round(1),
                    "G3 %": (100 * g3_p).round(1),
                    "shift": (100 * (g3_p - fresh_p)).round(1)}).to_string(index=False))

share = P_CELLS / PA_CELLS                      # her block's share of resolving cells
full = share * float((g3_p - fresh_p) @ Wt)
print(f"\nher block is {100*share:.1f}% of the cells that resolve a plate appearance")
print(f"shifting her all the way to the G3 mix would cost {full:+.4f} runs per batter faced")
print(f"the measured step is {TARGET:+.3f}, so the shift is scaled by "
      f"{TARGET/full:.2f}")

w = line_weights()
fresh_cells = to_cells(lg.to_numpy()[None, :], P_CELLS, w, True)[0]


def column(lam):
    p_ = np.clip(fresh_p + lam * (g3_p - fresh_p), 1e-6, None)
    p_ = p_ / p_.sum()
    card = np.zeros(len(CARD_LINES))
    for i_, l in enumerate(CARD_LINES):
        card[i_] = (p_[TREE_LINES.index(l)] * (1 - lg["2B"] - lg["ROE"])
                    if l in TREE_LINES else lg[l])
    cells = to_cells(card[None, :], P_CELLS, w, True)[0]
    cost = share * float(((cells - fresh_cells) / P_CELLS) @ Wt)
    moved = int(np.abs(cells - fresh_cells).sum() // 2)
    return cells, cost, moved


rows = [{"column": "fresh", "G3 shift": "0", "runs/BF": 0.0, "cells moved": 0,
         **{l: int(c) for l, c in zip(TREE_LINES, fresh_cells)}}]
for name, lam in (("tired", 0.5), ("gassed", 1.0),
                  ("what +0.09 would need", TARGET / full)):
    cells, cost, moved = column(lam)
    rows.append({"column": name, "G3 shift": f"{lam:.2f}x", "runs/BF": round(cost, 4),
                 "cells moved": moved, **{l: int(c) for l, c in zip(TREE_LINES, cells)}})
print("\n=== candidate columns, in cells out of 33 ===")
print(pd.DataFrame(rows).to_string(index=False))
print("\n  The last row is shown to be rejected: hit-by-pitches at 4 cells of 33 is")
print("  12% of her card. Her block is only 35% of the cells that resolve a plate")
print("  appearance, so moving the MATCHUP by 0.09 needs her card to move by")
print(f"  {TARGET/share:.2f} runs a read, against a league card worth "
      f"{float(fresh_p @ Wt):+.3f}. A card-only mechanic cannot do it.")
print("\n  The two estimates that do NOT include the manager reacting to luck --")
print("  G3's own shape (+0.032) and the times-seen design (+0.048, SE 0.057) --")
print("  both sit where 'gassed' lands. That is the defensible size.")
