"""What to do about cards whose home-run line rounds to nothing.

    pixi run python analysis/dice/hr_floor_options.py

One cell is 1% of the table, but a batter smoothed toward a cohort with little
power can have a card under 0.1% -- so "at least one cell" is a fourteen-fold
increase for her, not a floor. Four options:

  none        let the line round to zero. Some matchups cannot produce a home
              run at all.
  per card    every card gets at least one cell (what inflated the league by 20%)
  per pair    only fix a matchup where BOTH sides are zero, adding the cell on
              whichever side its run error damages least
  d12 slice   a card's sub-cell lines share one cell, divided by the d12 that is
              already being rolled. A line needing 0.07% takes one twelfth of a
              cell, 0.083%, instead of a whole one.

Reported on what each costs: run error against the unrounded card, the league
home-run total, and how many matchups still cannot produce one.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, TO_LINE, cards, plate_appearances

pd.set_option("display.width", 250)
P_CELLS, B_CELLS, TW = 35, 58, 12
TREE = [l for l in CARD_LINES if l not in ("2B", "ROE")]
IXT = [CARD_LINES.index(l) for l in TREE]
HR_J = TREE.index("HR")
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()[IXT]
B, P = cards("B"), cards("P")
n_b = pa.groupby("B").size().reindex(B.index).fillna(0).to_numpy()
n_p = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy()


def exact(card, total):
    p = card[:, IXT]
    return p / p.sum(axis=1, keepdims=True) * total


exb, exp_ = exact(B.to_numpy(), B_CELLS), exact(P.to_numpy(), P_CELLS)


def round_runs(ex, total):
    """Nearest, then spend the difference where |run error| is smallest."""
    cells = np.maximum(np.rint(ex).astype(int), 0)
    for i in range(len(cells)):
        while cells[i].sum() != total:
            step = 1 if cells[i].sum() < total else -1
            cand, err = None, np.inf
            for j in range(len(TREE)):
                if step < 0 and cells[i, j] == 0:
                    continue
                c = cells[i].copy()
                c[j] += step
                e = abs(float((c - ex[i]) @ W)) / 100
                if e < err:
                    cand, err = c, e
            cells[i] = cand
    return cells


def d12_slice(ex, total):
    """Whole cells for the big lines; the small ones share one cell in twelfths."""
    small = ex < 0.5
    cells = np.zeros_like(ex)
    for i in range(len(ex)):
        if not small[i].any():
            cells[i] = round_runs(ex[i:i + 1], total)[0]
            continue
        tw = np.zeros(len(TREE))
        for j in np.flatnonzero(small[i]):
            tw[j] = max(1, round(TW * ex[i, j]))           # at least one twelfth
        if tw.sum() > TW:                                  # too many small lines: keep the biggest
            keep = np.argsort(-ex[i] * small[i])[:TW]
            tw = np.zeros(len(TREE))
            for j in keep[:TW]:
                tw[j] = 1
        big = ex[i].copy()
        big[small[i]] = 0.0
        rest = round_runs((big / max(big.sum(), 1e-9) * (total - 1))[None, :], total - 1)[0]
        cells[i] = rest + tw / TW
        cells[i, int(np.argmax(rest))] += (TW - tw.sum()) / TW   # leftover twelfths
    return cells


bc0, pc0 = round_runs(exb, B_CELLS), round_runs(exp_, P_CELLS)


def per_pair(bc, pc):
    """Only fix a matchup where both sides are zero; add the cell where it hurts least."""
    bc, pc = bc.astype(float).copy(), pc.astype(float).copy()
    fixed = 0
    for j in range(len(TREE)):
        bz, pz = np.flatnonzero(bc[:, j] == 0), np.flatnonzero(pc[:, j] == 0)
        if not len(bz) or not len(pz):
            continue
        # cheaper to fix the side with fewer zero cards, weighted by how little it distorts
        cost_b = np.mean([abs(1 - exb[i, j]) for i in bz])
        cost_p = np.mean([abs(1 - exp_[i, j]) for i in pz])
        if cost_b <= cost_p:
            for i in bz:
                k = int(np.argmax(bc[i]))
                bc[i, j] += 1
                bc[i, k] -= 1
            fixed += len(bz)
        else:
            for i in pz:
                k = int(np.argmax(pc[i]))
                pc[i, j] += 1
                pc[i, k] -= 1
            fixed += len(pz)
    return bc, pc, fixed


def report(name, bc, pc):
    holes = sum(int(((bc[i] + pc[k]) < 1e-9).any())
                for i in range(len(bc)) for k in range(len(pc)))
    hr = float(((bc[:, HR_J] + (pc[:, HR_J] * n_p).sum() / n_p.sum()) / 100 * n_b).sum())
    eb = np.abs((bc - exb) @ W).mean() / 100
    ep = np.abs((pc - exp_) @ W).mean() / 100
    return {"option": name, "batters with 0 HR cells": int((bc[:, HR_J] < 1e-9).sum()),
            "pitchers with 0": int((pc[:, HR_J] < 1e-9).sum()),
            "matchups with a missing line": holes,
            "league HR": round(hr, 1),
            "mean |run err| batters x1000": round(1000 * eb, 2),
            "pitchers": round(1000 * ep, 2)}


rows = [report("none", bc0.astype(float), pc0.astype(float))]
bcp, pcp, fixed = per_pair(bc0, pc0)
rows.append(report("per pair", bcp, pcp))
bc1 = bc0.astype(float).copy()
bc1[:, HR_J] = np.maximum(bc1[:, HR_J], 1)
for i in range(len(bc1)):
    while bc1[i].sum() > B_CELLS:
        bc1[i, int(np.argmax(bc1[i]))] -= 1
rows.append(report("per card", bc1, pc0.astype(float)))
rows.append(report("d12 slice", d12_slice(exb, B_CELLS), d12_slice(exp_, P_CELLS)))
print(f"actual home runs {int((pa['line'] == 'HR').sum())}; "
      f"unrounded cards {float((B['HR'].to_numpy() * n_b).sum()):.1f}\n")
print(pd.DataFrame(rows).to_string(index=False))

z = np.flatnonzero(bc0[:, HR_J] == 0)
zp = np.flatnonzero(pc0[:, HR_J] == 0)
print(f"\n=== if we accept the zeros ===")
print(f"  batters with no HR cell: {len(z)} of {len(bc0)}, "
      f"{100 * n_b[z].sum() / n_b.sum():.1f}% of all plate appearances")
print(f"  pitchers with no HR cell: {len(zp)} of {len(pc0)}, "
      f"{100 * n_p[zp].sum() / n_p.sum():.1f}% of all batters faced")
print(f"  share of PAs where BOTH are zero: "
      f"{100 * sum(n_b[i] * n_p[k] for i in z for k in zp) / (n_b.sum() * n_p.sum()):.2f}%")
print("  those batters' card HR rates: "
      + ", ".join(f"{100 * v:.2f}%" for v in np.sort(B['HR'].to_numpy()[z])[-5:]) + " (highest five)")
