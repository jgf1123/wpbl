"""Performance by the i'th time a batter has faced this pitcher in this game.

    pixi run python analysis/dice/times_seen.py

The cleanest clock available. Every other cut has to control for who batted --
by card residual, which is statistical and imperfect. Here the batter is the SAME
PERSON facing the SAME PITCHER, so the matchup is held exactly fixed and the raw
run value can be differenced directly. Nothing is modelled away.

    difference = run value at her i'th meeting - run value at her first

averaged over every (game, pitcher, batter) triple that got that far.

THE SELECTION, which runs the other way from every earlier test: a second meeting
only exists if the pitcher was still in. She is pulled partly because of what
happened the first time through, so the retained first meetings are a little
better than average and the difference is biased TOWARD finding decline. Earlier
cuts were biased toward finding none, so agreement between them would mean
something. Restricting to outings of 3+ innings, where survival to a second
meeting was never in doubt, is reported alongside as the bound on it.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, TO_LINE

pd.set_option("display.width", 215)
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES)

p = tables.read("plays", "all")
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
pa["rv"] = pa["line"].map(W).astype(float)
pa = pa.sort_values(["game_id", "sequence"])

blocks = []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    grp = grp.copy()
    seen = {}
    n = []
    for b in grp["batter_id"]:
        seen[b] = seen.get(b, 0) + 1
        n.append(seen[b])
    grp["times_seen"] = n
    grp["n_inn"] = len(set(grp["inning"]))
    blocks.append(grp)
pa = pd.concat(blocks, ignore_index=True)

pairs = []
for (gm, pid, bid), grp in pa.groupby(["game_id", "pitcher_id", "batter_id"], sort=False):
    g = grp.set_index("times_seen")["rv"]
    if 1 not in g.index:
        continue
    for i in (2, 3):
        if i in g.index:
            pairs.append({"game_id": gm, "i": i, "d": float(g.loc[i]) - float(g.loc[1]),
                          "first": float(g.loc[1]), "later": float(g.loc[i]),
                          "n_inn": int(grp["n_inn"].iloc[0])})
d = pd.DataFrame(pairs)
gg = pd.Categorical(d["game_id"]).codes
nG = gg.max() + 1
rng = np.random.default_rng(20260922)


def report(sub, label):
    if len(sub) < 20:
        return {"set": label, "pairs": len(sub), "1st": np.nan, "later": np.nan,
                "difference": np.nan, "SE": np.nan, "SE units": np.nan}
    idx = sub.index.to_numpy()
    v = d["d"].to_numpy()
    mask = np.zeros(len(d), bool)
    mask[idx] = True
    bs = []
    for _ in range(3000):
        pick = np.concatenate([np.flatnonzero((gg == k) & mask)
                               for k in rng.integers(0, nG, nG)])
        if len(pick) > 5:
            bs.append(v[pick].mean())
    se = float(np.std(bs))
    m = float(sub["d"].mean())
    return {"set": label, "pairs": len(sub), "1st": round(float(sub["first"].mean()), 4),
            "later": round(float(sub["later"].mean()), 4), "difference": round(m, 4),
            "SE": round(se, 4), "SE units": round(m / se, 2) if se else np.nan}


print(f"{len(d)} (game, pitcher, batter) pairs with a repeat meeting\n")
rows = [report(d[d["i"] == 2], "2nd meeting minus 1st"),
        report(d[d["i"] == 3], "3rd meeting minus 1st")]
print(pd.DataFrame(rows).to_string(index=False))
print("\n=== restricted to outings of 3+ innings, where surviving to a 2nd "
      "meeting was never in doubt ===")
rows = [report(d[(d["i"] == 2) & (d["n_inn"] >= 3)], "2nd meeting minus 1st"),
        report(d[(d["i"] == 3) & (d["n_inn"] >= 3)], "3rd meeting minus 1st")]
print(pd.DataFrame(rows).to_string(index=False))
print("\npositive = worse the later time. No cards, no residuals: the same batter "
      "against the same pitcher.")
