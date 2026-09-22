"""Do relievers pitch at a higher ceiling and burn through it faster?

    pixi run python analysis/dice/roles.py

The hypothesis, and Jaida Lee's own account of moving from starting to relief: a
reliever throws nearer her maximum, which is better while it lasts and lasts less
long. Other games price that at about three times the burn rate.

Two halves, measured separately:
  ceiling    is a reliever better per batter faced than a starter, once the
             pitcher herself is accounted for? The sharpest version compares
             pitchers who did BOTH, against themselves.
  burn       does the decline with pitches thrown differ by role?

Scored as a residual against the matchup (both cards), so a reliever is not
credited for facing weaker batters. One caveat throughout: a pitcher's card pools
her starts and her relief, so if she is genuinely better in relief the card sits
between the two and both residuals are pulled toward zero. The WITHIN-pitcher
comparison is immune to that; the across-pitcher one is not.
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
nm = pl.drop_duplicates("person_id").set_index("person_id")["person_name"]
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
starters = pa.groupby(["game_id", "pitcher_id"])["sequence"].min()
first_of_game = pa.groupby(["game_id", "pitching_team_id"])["sequence"].min()
pa["is_starter"] = [starters.get((g, q)) == first_of_game.get((g, tm))
                    for g, q, tm in zip(pa["game_id"], pa["pitcher_id"], pa["pitching_team_id"])]
blocks = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    grp = grp.copy()
    grp["before"] = grp["pitches"].cumsum() - grp["pitches"]
    blocks.append(grp)
pa = pd.concat(blocks, ignore_index=True)

g = pd.Categorical(pa["game_id"]).codes
nG = g.max() + 1
rng = np.random.default_rng(20260922)
DRAWS = [np.concatenate([np.flatnonzero(g == k) for k in rng.integers(0, nG, nG)])
         for _ in range(1500)]


def stat(mask, label):
    m = np.asarray(mask)
    v = pa["resid"].to_numpy()
    if m.sum() < 15:
        return {"group": label, "BF": int(m.sum()), "resid": np.nan, "SE": np.nan}
    bs = [v[d][m[d]].mean() for d in DRAWS if m[d].sum() > 5]
    return {"group": label, "BF": int(m.sum()), "resid": round(float(v[m].mean()), 4),
            "SE": round(float(np.std(bs)), 4)}


st = pa["is_starter"].to_numpy()
app = pa.groupby(["game_id", "pitcher_id"]).agg(
    P=("P", "first"), starter=("is_starter", "first"), BF=("rv", "size"),
    pitches=("pitches", "sum"))
roles = app.groupby("P")["starter"].agg(["mean", "size"])
both = roles[(roles["mean"] > 0) & (roles["mean"] < 1)]
print(f"{len(roles)} pitchers; {len(both)} both started and relieved\n")
print("=== usage by role ===")
print(app.groupby("starter").agg(appearances=("BF", "size"), BF_median=("BF", "median"),
                                 pitches_median=("pitches", "median"),
                                 pitches_max=("pitches", "max")).to_string())

print("\n=== ceiling: across all pitchers (card pools both roles, so muted) ===")
print(pd.DataFrame([stat(~st, "relief"), stat(st, "start")]).to_string(index=False))
print("\n  ... restricted to the first 25 pitches of the outing, before fatigue can bite")
print(pd.DataFrame([stat(~st & (pa["before"] <= 25).to_numpy(), "relief, first 25 pitches"),
                    stat(st & (pa["before"] <= 25).to_numpy(), "start, first 25 pitches")]
                   ).to_string(index=False))

print("\n=== ceiling: the pitchers who did BOTH, against themselves ===")
rows = []
for pid in both.index:
    sub = pa[pa["P"] == pid]
    r = sub[~sub["is_starter"]]["resid"]
    s = sub[sub["is_starter"]]["resid"]
    if len(r) >= 10 and len(s) >= 10:
        rows.append({"pitcher": nm.get(pid, pid), "relief BF": len(r), "start BF": len(s),
                     "relief": round(r.mean(), 4), "start": round(s.mean(), 4),
                     "relief - start": round(r.mean() - s.mean(), 4)})
d = pd.DataFrame(rows)
if len(d):
    print(d.to_string(index=False))
    print(f"\n  mean of the within-pitcher differences: {d['relief - start'].mean():+.4f} "
          f"over {len(d)} pitchers (negative = better in relief)")

print("\n=== burn: decline with pitches thrown, by role ===")
rows = []
for role, m in (("relief", ~st), ("start", st)):
    for lo, hi, lbl in ((0, 24, "0-24"), (25, 49, "25-49"), (50, 999, "50+")):
        mm = m & (pa["before"] >= lo).to_numpy() & (pa["before"] <= hi).to_numpy()
        s_ = stat(mm, f"{role}, {lbl} pitches in")
        rows.append(s_)
print(pd.DataFrame(rows).to_string(index=False))
