"""How to round a card into whole cells: four rules, judged on runs.

    pixi run python analysis/dice/layout_round.py

The batter's card gets 58 cells, the pitcher's 35. Turning a distribution into
whole cells needs a rule, and the obvious ones are wrong in a familiar way:
giving the leftover cells to the biggest line lets Out absorb every rounding
error, which is the same mistake as letting Out give back the mixing offset.

The rule under test instead spends the leftover cells wherever they bring the
card's RUN VALUE closest to the unrounded card -- which is what the cards are
scored on:

    a  scale the distribution to the block size
    b  round each line to the nearest whole cell
    c  raise home runs to at least one cell
    d  if the cells do not sum to the block, then
    e  add or remove cells wherever |run error| ends up smallest

Compared against largest remainder (the classic), and against the same rule
without the home-run floor, to price that floor separately.
"""
from itertools import combinations

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, TO_LINE, bands, cards, plate_appearances

pd.set_option("display.width", 240)
P_CELLS, B_CELLS = 35, 58
TREE = [l for l in CARD_LINES if l not in ("2B", "ROE")]
IXT = [CARD_LINES.index(l) for l in TREE]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()[IXT]
HR_J = TREE.index("HR")
B, P = cards("B"), cards("P")


def exact_cells(card, total):
    p = card[:, IXT]
    return p / p.sum(axis=1, keepdims=True) * total


def largest_remainder(ex, total):
    cells = np.floor(ex).astype(int)
    rem = ex - cells
    for i in range(len(cells)):
        for j in np.argsort(-rem[i])[:total - cells[i].sum()]:
            cells[i, j] += 1
    return cells


def by_run_error(ex, total, hr_floor):
    """Nearest, then the home-run floor, then spend the difference on run value."""
    cells = np.rint(ex).astype(int)
    cells = np.maximum(cells, 0)
    if hr_floor:
        cells[:, HR_J] = np.maximum(cells[:, HR_J], 1)
    out = cells.copy()
    for i in range(len(cells)):
        short = total - cells[i].sum()
        if short == 0:
            continue
        best, best_err = None, np.inf
        step = 1 if short > 0 else -1
        picks = range(len(TREE))
        for combo in combinations(picks, min(abs(short), len(TREE))):
            c = cells[i].copy()
            for j in combo:
                c[j] += step
            if c.sum() != total or (c < 0).any():
                continue
            if hr_floor and c[HR_J] < 1:
                continue
            err = abs(float((c / 100 - ex[i] / 100) @ W))
            if err < best_err:
                best, best_err = c, err
        if best is None:                       # fall back if nothing legal was found
            best = largest_remainder(ex[i:i + 1], total)[0]
        out[i] = best
    return out


RULES = {
    "largest remainder": lambda ex, t: largest_remainder(ex, t),
    "nearest + run error": lambda ex, t: by_run_error(ex, t, False),
    "nearest + run error + HR floor": lambda ex, t: by_run_error(ex, t, True),
}
exb, exp_ = exact_cells(B.to_numpy(), B_CELLS), exact_cells(P.to_numpy(), P_CELLS)
n_b = pa.groupby("B").size().reindex(B.index).fillna(0).to_numpy()
rows = []
for name, fn in RULES.items():
    bc, pc = fn(exb, B_CELLS), fn(exp_, P_CELLS)
    assert (bc.sum(axis=1) == B_CELLS).all() and (pc.sum(axis=1) == P_CELLS).all()
    run_b = np.abs((bc / 100 - exb / 100) @ W)
    run_p = np.abs((pc / 100 - exp_ / 100) @ W)
    holes = sum(int(((bc[i] + pc[k]) == 0).any())
                for i in range(len(bc)) for k in range(len(pc)))
    hr_total = float(((bc[:, HR_J] + pc[:, HR_J].mean()) / 100 * n_b).sum())
    rows.append({"rule": name,
                 "mean |run error| x1000, batters": round(1000 * run_b.mean(), 2),
                 "worst, batters": round(1000 * run_b.max(), 2),
                 "mean, pitchers": round(1000 * run_p.mean(), 2),
                 "matchups with a missing line": holes,
                 "league HR the table gives": round(hr_total, 1)})
print(f"actual home runs {int((pa['line'] == 'HR').sum())}; "
      f"unrounded cards give {float((B['HR'].to_numpy() * n_b).sum()):.1f}\n")
print(pd.DataFrame(rows).to_string(index=False))

bc = RULES["nearest + run error + HR floor"](exb, B_CELLS)
pc = RULES["nearest + run error + HR floor"](exp_, P_CELLS)
print("\n=== what the HR floor costs the batters it binds on ===")
raw = exb[:, HR_J]
bind = np.flatnonzero((np.rint(exb).astype(int)[:, HR_J] == 0))
print(f"  binds on {len(bind)} of {len(exb)} batters")
show = pd.DataFrame({"batter": [nm.get(B.index[i], B.index[i]) for i in bind[:8]],
                     "PA": n_b[bind[:8]].astype(int),
                     "card HR %": (100 * B["HR"].to_numpy()[bind[:8]]).round(2),
                     "exact cells": raw[bind[:8]].round(2),
                     "printed cells": bc[bind[:8], HR_J]})
print(show.to_string(index=False))
