"""The shape of the decline over the range a pitcher actually works.

    pixi run python analysis/dice/fatigue_curve.py

fatigue_from_end.py anchors the curve at one point -- the inning before a manager
acts -- and semifinal G3 anchors it past the hook. Between a pitcher's first
inning and her last, which is where the mechanic spends nearly all its time,
nothing was measured. This traces it.

Same paired design, read at every point instead of only the penultimate one: a
pitcher is compared with HERSELF earlier in the same outing, so neither her
quality nor the outing's length can masquerade as fatigue. Her final inning is
dropped throughout -- that is the collapse the removal was a reaction to, and
including it would bend the end of the curve by construction.

Two axes, because the mechanic needs one and the eye reads the other:
  pitches thrown so far   what an effective-pitch-count track would actually
                          carry
  innings completed       coarser, and immune to how pitches were counted
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
blocks = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    grp = grp.copy()
    grp["before"] = grp["pitches"].cumsum() - grp["pitches"]
    innings = list(dict.fromkeys(grp["inning"]))
    grp["inn_n"] = [innings.index(i) + 1 for i in grp["inning"]]
    grp["n_inn"] = len(innings)
    blocks.append(grp)
pa = pd.concat(blocks, ignore_index=True)
work = pa[pa["inn_n"] < pa["n_inn"]].copy()      # drop her final inning throughout
print(f"{pa.groupby(['game_id','pitcher_id']).ngroups} appearances; "
      f"{len(work)} plate appearances outside the removal inning\n")


def curve(frame, col, bins, labels, base_label):
    """Paired: each bucket minus that pitcher's own first bucket, same outing."""
    frame = frame.copy()
    frame["b"] = pd.cut(frame[col], bins, labels=labels)
    rows = []
    for (gm, pid), grp in frame.groupby(["game_id", "pitcher_id"], sort=False):
        base = grp[grp["b"] == base_label]["resid"]
        if len(base) < 2:
            continue
        for b, sub in grp.groupby("b", observed=True):
            if str(b) == base_label or len(sub) < 2:
                continue
            rows.append({"game_id": gm, "b": str(b), "d": sub["resid"].mean() - base.mean()})
    d = pd.DataFrame(rows)
    gg = pd.Categorical(d["game_id"]).codes
    nG = gg.max() + 1
    rng = np.random.default_rng(12)
    out = []
    for b, sub in d.groupby("b"):
        idx = (d["b"] == b).to_numpy()
        v = d["d"].to_numpy()
        bs = []
        for _ in range(3000):
            pick = np.concatenate([np.flatnonzero((gg == k) & idx)
                                   for k in rng.integers(0, nG, nG)])
            if len(pick) > 3:
                bs.append(v[pick].mean())
        out.append({"bucket": b, "outings": len(sub),
                    "vs her own " + base_label: round(float(sub["d"].mean()), 4),
                    "SE": round(float(np.std(bs)), 4),
                    "SE units": round(float(sub["d"].mean()) / float(np.std(bs)), 2)})
    return pd.DataFrame(out)


print("=== by pitches already thrown (her final inning excluded) ===")
print(curve(work, "before", [-1, 24, 49, 74, 999], ["0-24", "25-49", "50-74", "75+"],
            "0-24").to_string(index=False))
print("\n=== by innings completed (her final inning excluded) ===")
print(curve(work, "inn_n", [0, 1, 2, 3, 99], ["1st", "2nd", "3rd", "4th+"],
            "1st").to_string(index=False))
print("\npositive = worse than she was earlier in the same outing.")
print("The removal inning sits outside this: it is +0.19 against her first "
      "(fatigue_from_end.py),")
print("and the inning before it +0.08.")
