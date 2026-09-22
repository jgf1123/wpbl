"""Align appearances by when the pitcher was REMOVED, not when she started.

    pixi run python analysis/dice/fatigue_from_end.py

fatigue.py aligns on the first batter, so its late buckets hold only pitchers who
were allowed to stay -- survivorship, biased toward finding no decline. Aligning
on the LAST batter inverts the problem: every appearance is measured against the
moment the manager decided, so "two innings before she came out" means the same
thing in a 40-pitch outing and a 90-pitch one.

The last inning, full or partial, is DROPPED. That is where the collapse that
triggered the removal lives, and including it would guarantee a decline for the
trivial reason that managers pull pitchers who have just been hit. What is left
is the stretch before the manager acted: if fatigue is what he was reacting to,
it should already be visible there.

This measures a different clock from pitch count -- time until removal, which is
partly the manager's perception. An appearance ended for a pinch hitter or a
blowout adds noise but not bias.

Scored as a residual against the matchup (both cards), so neither who batted nor
who pitched can be credited.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, MIX_ALPHA, TO_LINE, cards

pd.set_option("display.width", 215)
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES)

p = tables.read("plays", "all")
pl = tables.read("players", "training")
person = pl.set_index("player_id")["person_id"].to_dict()
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
pa["rv"] = pa["line"].map(W).astype(float)
pa["pitches"] = pd.to_numeric(pa["n_pitches"], errors="coerce").fillna(3.7)
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
B, P = cards("B"), cards("P")
lgm = float(pa["rv"].mean())
ev = (B @ W).reindex(pa["B"]).to_numpy()
pv = (P @ W).reindex(pa["P"]).to_numpy()
pa["resid"] = pa["rv"] - (MIX_ALPHA * np.where(np.isnan(pv), lgm, pv)
                          + (1 - MIX_ALPHA) * np.where(np.isnan(ev), lgm, ev))

pa = pa.sort_values(["game_id", "sequence"])
out = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    grp = grp.copy()
    innings = list(dict.fromkeys(grp["inning"]))          # her innings, in order
    n_inn = len(innings)
    pos = {inn: n_inn - i for i, inn in enumerate(innings)}   # 1 = her LAST inning
    grp["from_end_inn"] = [pos[i] for i in grp["inning"]]
    tot = grp["pitches"].sum()
    grp["pitches_left"] = tot - grp["pitches"].cumsum()   # pitches thrown AFTER this PA
    grp["n_inn"] = n_inn
    out.append(grp)
pa = pd.concat(out, ignore_index=True)

g = pd.Categorical(pa["game_id"]).codes
nG = g.max() + 1
rng = np.random.default_rng(20260922)
DRAWS = [np.concatenate([np.flatnonzero(g == k) for k in rng.integers(0, nG, nG)])
         for _ in range(1500)]


def show(masks, title):
    print(f"\n=== {title} ===")
    v = pa["resid"].to_numpy()
    rows = []
    for label, m in masks.items():
        m = np.asarray(m)
        if m.sum() < 15:
            rows.append({"group": label, "BF": int(m.sum()), "resid": np.nan, "SE": np.nan})
            continue
        bs = [v[d][m[d]].mean() for d in DRAWS if m[d].sum() > 5]
        rows.append({"group": label, "BF": int(m.sum()), "resid": round(float(v[m].mean()), 4),
                     "SE": round(float(np.std(bs)), 4)})
    print(pd.DataFrame(rows).to_string(index=False))


fe = pa["from_end_inn"].to_numpy()
deep = (pa["n_inn"] >= 3).to_numpy()
print(f"{pa.groupby(['game_id','pitcher_id']).ngroups} appearances; "
      f"{int(pa.groupby(['game_id','pitcher_id'])['n_inn'].first().ge(3).sum())} span 3+ innings")
show({"her LAST inning (dropped from the tests)": deep & (fe == 1),
      "2nd from last": deep & (fe == 2),
      "3rd from last": deep & (fe == 3),
      "4th from last or earlier": deep & (fe >= 4)},
     "POOLED, and therefore confounded: innings counted back from removal")
print("  Do not read this as a decline. The buckets hold DIFFERENT appearances:")
print("  '4th from last or earlier' exists only inside outings of 4+ innings, which")
print("  are the long good ones. That is survivorship inverted. The paired test below")
print("  compares a pitcher with herself inside one appearance, which is the fix.")

# ---- the paired test: within one appearance, her first inning against the one
# before she was pulled. Appearance length is held fixed by construction, and the
# pitcher cancels, so neither can masquerade as fatigue.
rows = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    n = int(grp["n_inn"].iloc[0])
    if n < 3:
        continue
    first = grp[grp["from_end_inn"] == n]["resid"]
    penult = grp[grp["from_end_inn"] == 2]["resid"]
    last = grp[grp["from_end_inn"] == 1]["resid"]
    if len(first) < 2 or len(penult) < 2:
        continue
    rows.append({"game_id": gm, "innings": n, "first": first.mean(),
                 "penultimate": penult.mean(),
                 "last": last.mean() if len(last) else np.nan,
                 "d_penult": penult.mean() - first.mean(),
                 "d_last": (last.mean() - first.mean()) if len(last) else np.nan})
paired = pd.DataFrame(rows)
gg = pd.Categorical(paired["game_id"]).codes
nGG = gg.max() + 1
rng2 = np.random.default_rng(5)
print(f"\n=== PAIRED, within one appearance: {len(paired)} outings of 3+ innings ===")
out = []
for col, lbl in (("d_penult", "the inning BEFORE she was pulled, minus her first"),
                 ("d_last", "the inning she was pulled in, minus her first")):
    v = paired[col].dropna().to_numpy()
    idx = paired[col].notna().to_numpy()
    bs = []
    for _ in range(3000):
        pick = np.concatenate([np.flatnonzero(gg[idx] == k)
                               for k in rng2.integers(0, nGG, nGG)])
        if len(pick):
            bs.append(v[pick].mean())
    out.append({"comparison": lbl, "outings": len(v), "mean difference": round(float(v.mean()), 4),
                "SE": round(float(np.std(bs)), 4),
                "SE units": round(float(v.mean()) / float(np.std(bs)), 2)})
print(pd.DataFrame(out).to_string(index=False))
print("\n  positive = worse. The first row excludes the inning the removal happened in,")
print("  so it cannot be the collapse that triggered the decision.")


# ---- fatigue, or a manager reacting to bad luck? -------------------------------
# The inning before removal is selected on having just pitched badly, since that is
# what makes a manager act. Bad luck plus a quick hook produces the same paired
# decline with no fatigue at all. The two separate on one prediction: fatigue
# should bite harder when more pitches have been thrown, selection should not care.
tot_p = pa.groupby(["game_id", "pitcher_id"])["pitches"].sum()
paired["total pitches"] = [tot_p.get((g, None), np.nan) for g in paired["game_id"]]
tp = {k: v for k, v in tot_p.items()}
key = list(pa.groupby(["game_id", "pitcher_id"]).groups.keys())
lookup = {}
for (g, q) in key:
    lookup.setdefault(g, []).append((q, tp[(g, q)]))
rows2 = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    n = int(grp["n_inn"].iloc[0])
    if n < 3:
        continue
    first = grp[grp["from_end_inn"] == n]["resid"]
    penult = grp[grp["from_end_inn"] == 2]["resid"]
    if len(first) < 2 or len(penult) < 2:
        continue
    rows2.append({"game_id": gm, "pitches": float(grp["pitches"].sum()),
                  "d": penult.mean() - first.mean()})
q = pd.DataFrame(rows2)
q["bucket"] = pd.cut(q["pitches"], [0, 45, 70, 9999],
                     labels=["short (<=45 pitches)", "medium (46-70)", "long (71+)"])
gg2 = pd.Categorical(q["game_id"]).codes
nG2 = gg2.max() + 1
rng3 = np.random.default_rng(9)
print("\n=== does the decline grow with the pitches thrown? ===")
rows3 = []
for b, sub in q.groupby("bucket", observed=True):
    idx = (q["bucket"] == b).to_numpy()
    v = q["d"].to_numpy()
    bs = []
    for _ in range(3000):
        pick = np.concatenate([np.flatnonzero((gg2 == k) & idx)
                               for k in rng3.integers(0, nG2, nG2)])
        if len(pick) > 3:
            bs.append(v[pick].mean())
    rows3.append({"appearance length": str(b), "outings": len(sub),
                  "median pitches": round(sub["pitches"].median()),
                  "decline before removal": round(float(sub["d"].mean()), 4),
                  "SE": round(float(np.std(bs)), 4)})
print(pd.DataFrame(rows3).to_string(index=False))
print("  fatigue predicts this grows with length; a quick hook on bad luck does not.")
