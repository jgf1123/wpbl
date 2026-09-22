"""Does a platoon adjustment predict held-out games better than none?

    pixi run python analysis/dice/handedness.py

Spec section 5 carries a platoon table as an ASSUMPTION -- never tested the way
every card choice is tested. The gaps it quotes have since moved a long way, so
the question is not "how big is the gap" but the one the project asks of
everything else: does knowing the handedness matchup help predict games the
adjustment was not fitted on?

The baseline already knows a great deal. Each player's card carries her own
rates, so a left-handed batter who hits well is already a good card; the platoon
adjustment has to earn its keep ON TOP of that, by predicting the part that
depends on the MATCHUP rather than on either player.

    baseline   p = a * pitcher's card + (1 - a) * batter's card
    platoon    p + d(side), d fitted on the build half only, summing to zero
               across lines so the card still sums to 100%

Scored on runs first and log loss second, per spec 9.0, with standard errors
from resampling whole games. A shrunk version is included because an adjustment
fitted on half a season is itself noisy: shrinking it toward zero is what a
smaller, safer platoon table would do.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, MIX_ALPHA,
                       PITCHER_K, PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 210)
SPLITS = 20
SHRINK = [0.0, 0.25, 0.5, 0.75, 1.0]       # 0 = no adjustment, 1 = the raw fitted gap

pa = plate_appearances()
pl = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
bats, throws = pl["bats"].to_dict(), pl["throws"].to_dict()


def side(b, t):
    if not isinstance(b, str) or not isinstance(t, str):
        return None
    if b.upper().startswith("S"):
        return 1                                  # switch hitters take the platoon side
    return 0 if b.upper()[0] == t.upper()[0] else 1


pa["side"] = [side(bats.get(b), throws.get(p)) for b, p in zip(pa["B"], pa["P"])]
pa = pa.dropna(subset=["side"]).copy()
pa["side"] = pa["side"].astype(int)

IX = {l: i for i, l in enumerate(CARD_LINES)}
y = pa["line"].map(IX).to_numpy()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, band = usage(pa), bands(pa)


def fold_cards(train):
    """Cards built on the build half only, so the baseline sees no more than the
    adjustment does. Leaving them fitted on all 37 games would hand the baseline
    the test half and stack the comparison against the platoon table."""
    out = {}
    for s, steps, ks, slug in (("B", BATTER_STEPS, BATTER_K, SLUGGERS),
                               ("P", PITCHER_STEPS, PITCHER_K, ())):
        X = pd.crosstab(train[s], train["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        nms = [players["person_name"].get(i, i) for i in ids]
        c = build(X.to_numpy().astype(float), nms,
                  shares[s].reindex(ids).fillna(0).to_numpy(), steps, ks, slug, band)
        out[s] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
    return out
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
actual_rv = W[y]
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
sd = pa["side"].to_numpy()

rng = np.random.default_rng(20260922)
runs = np.zeros((len(SHRINK), nG))
loss = np.zeros((len(SHRINK), nG))
cnt = np.zeros(nG)
for rep in range(SPLITS):
    half = rng.permutation(np.arange(nG) % 2)
    m = half[gcode]
    for fold in (0, 1):
        tr, te = m != fold, m == fold
        cd = fold_cards(pa[tr])
        ok = te & pa["B"].isin(cd["B"].index).to_numpy() & pa["P"].isin(cd["P"].index).to_numpy()
        te = ok
        base_te = (MIX_ALPHA * cd["P"].loc[pa["P"][te]].to_numpy()
                   + (1 - MIX_ALPHA) * cd["B"].loc[pa["B"][te]].to_numpy())
        # the adjustment: how each side's line rates differ from the pooled rate,
        # measured on the build half only
        d = np.zeros((2, len(CARD_LINES)))
        pooled = np.bincount(y[tr], minlength=len(CARD_LINES)) / tr.sum()
        for s in (0, 1):
            k = tr & (sd == s)
            if k.sum() > 0:
                d[s] = np.bincount(y[k], minlength=len(CARD_LINES)) / k.sum() - pooled
        np.add.at(cnt, gcode[te], 1.0)
        for j, sh in enumerate(SHRINK):
            p = np.clip(base_te + sh * d[sd[te]], 1e-6, None)
            p = p / p.sum(axis=1, keepdims=True)
            err = (p @ W - actual_rv[te]) ** 2
            np.add.at(runs[j], gcode[te], err)
            np.add.at(loss[j], gcode[te], -np.log(p[np.arange(len(p)), y[te]]))

tot_r, tot_l = runs.sum(axis=1) / cnt.sum(), loss.sum(axis=1) / cnt.sum()
draws = np.random.default_rng(3).integers(0, nG, size=(3000, nG))
rows = []
for j, sh in enumerate(SHRINK):
    dr = runs[j] - runs[0]
    dl = loss[j] - loss[0]
    se_r = (1e6 * dr[draws].sum(axis=1) / cnt[draws].sum(axis=1)).std()
    se_l = (1000 * dl[draws].sum(axis=1) / cnt[draws].sum(axis=1)).std()
    rows.append({"platoon strength": sh,
                 "runs err x1e6": round(1e6 * tot_r[j], 1),
                 "vs none": round(1e6 * (tot_r[j] - tot_r[0]), 1), "SE": round(se_r, 1),
                 "log loss x1000": round(1000 * tot_l[j], 3),
                 "vs none ": round(1000 * (tot_l[j] - tot_l[0]), 3), "SE ": round(se_l, 3)})
print(f"{len(pa)} plate appearances, {nG} games, {SPLITS} splits")
print("negative = better than no platoon adjustment\n")
print(pd.DataFrame(rows).to_string(index=False))
