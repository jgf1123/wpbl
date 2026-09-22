"""How does a plate appearance change as the outing goes on?

    pixi run python analysis/dice/pitch_tempo.py

Two questions the fatigue mechanic depends on.

1. HOW VARIABLE IS AN INNING as a unit of work? The decline is measured in
   innings, because pitches are endogenous -- a struggling inning is a long one,
   so a pitch-defined window selects on bad performance. But the TRACK counts
   pitches, so the measurement has to be converted, and the conversion is only as
   good as its spread.

2. DOES A TIRING PITCHER THROW LONGER OR SHORTER PLATE APPEARANCES? This decides
   whether a pitch-count track accelerates or decelerates as she gets worse. If
   she walks more, it accelerates and the mechanic compounds on its own. If she
   gives up more contact, plate appearances shorten and the track SLOWS DOWN
   exactly when she is pitching worst -- which would be a mechanic that rewards
   getting hit.

Everything is paired within the outing: inning n against that pitcher's own first
inning, same appearance, so neither her quality nor the outing's length can
masquerade as a trend. Her final inning is excluded throughout.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import TO_LINE

pd.set_option("display.width", 215)
p = tables.read("plays", "all")
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
pa["pitches"] = pd.to_numeric(pa["n_pitches"], errors="coerce")
pa = pa.sort_values(["game_id", "sequence"])
blocks = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    grp = grp.copy()
    innings = list(dict.fromkeys(grp["inning"]))
    grp["inn_n"] = [innings.index(i) + 1 for i in grp["inning"]]
    grp["n_inn"] = len(innings)
    blocks.append(grp)
pa = pd.concat(blocks, ignore_index=True)

print("=== 1. how variable is an inning as a unit of work? ===")
per_inn = pa.groupby(["game_id", "pitcher_id", "inning"]).agg(
    BF=("pitches", "size"), pitches=("pitches", "sum"))
print(f"  {len(per_inn)} pitcher-innings")
print(f"  batters faced: mean {per_inn['BF'].mean():.2f}, SD {per_inn['BF'].std():.2f}, "
      f"max {int(per_inn['BF'].max())}")
print(f"  pitches:       mean {per_inn['pitches'].mean():.1f}, SD {per_inn['pitches'].std():.1f}, "
      f"max {int(per_inn['pitches'].max())}")
print(f"  coefficient of variation on pitches per inning: "
      f"{per_inn['pitches'].std() / per_inn['pitches'].mean():.2f}")
print(f"  innings facing 10+ batters (batting around): "
      f"{int((per_inn['BF'] >= 10).sum())} of {len(per_inn)} "
      f"({100 * (per_inn['BF'] >= 10).mean():.1f}%)")
print(f"  innings facing 4 or fewer:  {100 * (per_inn['BF'] <= 4).mean():.1f}%")
dup = pa.groupby(["game_id", "pitcher_id", "inning"])["batter_id"].apply(
    lambda s: s.duplicated().any())
print(f"  innings where a batter came up TWICE: {int(dup.sum())} of {len(dup)} "
      f"({100 * dup.mean():.1f}%)")

print("\n=== 2. does a plate appearance get longer or shorter? ===")
work = pa[pa["inn_n"] < pa["n_inn"]].copy()
rows = []
for (gm, pid), grp in work.groupby(["game_id", "pitcher_id"], sort=False):
    base = grp[grp["inn_n"] == 1]
    if len(base) < 2:
        continue
    for n, sub in grp.groupby("inn_n"):
        if n == 1 or len(sub) < 2:
            continue
        rows.append({"game_id": gm, "inn": min(int(n), 4),
                     "d_pitch": sub["pitches"].mean() - base["pitches"].mean(),
                     "d_bb": (sub["line"].isin(["BB", "HBP"]).mean()
                              - base["line"].isin(["BB", "HBP"]).mean()),
                     "d_k": (sub["line"].eq("K").mean() - base["line"].eq("K").mean()),
                     "d_contact": (sub["line"].isin(["1B", "2B", "HR", "ROE", "OUT"]).mean()
                                   - base["line"].isin(["1B", "2B", "HR", "ROE", "OUT"]).mean())})
d = pd.DataFrame(rows)
gg = pd.Categorical(d["game_id"]).codes
nG = gg.max() + 1
rng = np.random.default_rng(20260922)
out = []
for n, sub in d.groupby("inn"):
    idx = (d["inn"] == n).to_numpy()
    row = {"her inning": f"{n}{'+' if n == 4 else ''}", "outings": len(sub)}
    for col, lbl in (("d_pitch", "pitches/PA"), ("d_bb", "BB+HBP rate"),
                     ("d_k", "K rate"), ("d_contact", "contact rate")):
        v = d[col].to_numpy()
        bs = []
        for _ in range(2000):
            pick = np.concatenate([np.flatnonzero((gg == k) & idx)
                                   for k in rng.integers(0, nG, nG)])
            if len(pick) > 3:
                bs.append(v[pick].mean())
        row[lbl] = round(float(sub[col].mean()), 4)
        row[lbl + " SE"] = round(float(np.std(bs)), 4)
    out.append(row)
print("  each against that pitcher's own first inning, same outing\n")
print(pd.DataFrame(out).to_string(index=False))
print("\n  positive pitches/PA = longer plate appearances as the outing goes on.")
