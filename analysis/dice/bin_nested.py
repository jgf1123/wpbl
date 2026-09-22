"""Do ten fitted bin weights beat one, when the weights are also held out?

    pixi run python analysis/dice/bin_nested.py

bin_alpha.py fitted the ten weights on the same plate appearances it then scored
them on. The cards were held out; the weights were not. Ten free parameters
fitted in sample will look good whether or not they are real, so this nests them
the way spec 9.0 requires:

    outer: split the games in half. One half is never touched until scoring.
    inner: split the build half again; cards from one part, weights fitted on
           the other, both directions averaged.
    then:  rebuild the cards on the whole build half, apply the fitted weights,
           and score the outer half that played no part in either.

Three rules are compared on that footing: ten bin weights, one weight for the
whole card, and no mixing at all.

A bin whose two cards hold the same thing for every player -- bins of pure Out,
for most of the league -- has nothing to fit. Its weight is not fitted; the roll
there needs no card choice at all.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, bands, build,
                       plate_appearances, usage)

pd.set_option("display.width", 240)
NBIN, OUTER = 10, 10
GRID = np.round(np.arange(0, 1.0001, 0.025), 3)
STARTS = [0.0, 0.3, 0.6]
UNIFORM = 1e-3                      # a bin this close on both cards has nothing to fit
# Sorted batter-end to pitcher-end by the PITCHER'S SHARE OF REAL SPREAD, which is
# what the mixing weight is supposed to track (line_owner.py):
#   HR, 1B, OUT  0.00   HBP 0.10   K 0.49   BB 0.82
#
# The fixed bands are NOT in here. Putting them in a bin destroys the thing that
# makes them fixed: the lines before them differ between the two cards, so a band
# lands on different cells on each, and once the bins carry different weights its
# total stops being the league rate and starts depending on the matchup. So the
# bands are set aside as their own cells and the bins divide what is left.
ORDER = ["HR", "1B", "OUT", "HBP", "K", "BB"]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, band = usage(pa), bands(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
ORD_I = [IX[l] for l in ORDER]
BAND_TOT = sum(band.values())
TREE_P = 1.0 - BAND_TOT
y_ord = pa["line"].map(lambda l: ORDER.index(l) if l in ORDER else -1).to_numpy()
band_p = pa["line"].map(lambda l: band.get(l, 0.0)).to_numpy()
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1


def bin_shares(card):
    p = card[:, ORD_I]
    p = p / p.sum(axis=1, keepdims=True)       # the bins divide the non-band part
    edges = np.cumsum(p, axis=1)
    lo = np.concatenate([np.zeros((len(p), 1)), edges[:, :-1]], axis=1)
    out = np.zeros((len(p), NBIN, len(ORD_I)))
    for j in range(NBIN):
        a, b = j / NBIN, (j + 1) / NBIN
        out[:, j, :] = np.clip(np.minimum(edges, b) - np.maximum(lo, a), 0, None) * NBIN
    return out


def make(frame, side, steps, ks):
    X = pd.crosstab(frame[side], frame["line"]).reindex(columns=LINES, fill_value=0)
    ids = X.index.to_numpy()
    nms = [players["person_name"].get(i, i) for i in ids]
    c = build(X.to_numpy().astype(float), nms,
              shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
              SLUGGERS if side == "B" else (), band)
    return pd.DataFrame(c, index=ids, columns=CARD_LINES)


def tensors(train, idx):
    """Share tensors and outcomes for plate appearances `idx`, cards built on `train`."""
    cb = make(train, "B", BATTER_STEPS, BATTER_K)
    cp = make(train, "P", PITCHER_STEPS, PITCHER_K)
    ok = [i for i in idx if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
    if not ok:
        return None
    return (bin_shares(cb.loc[pa["B"].iloc[ok]].to_numpy()),
            bin_shares(cp.loc[pa["P"].iloc[ok]].to_numpy()),
            y_ord[ok], gcode[ok], band_p[ok])


def loss_vec(SB, SP, YY, v, BP=None):
    """A band line's probability is its band, untouched by any weight."""
    p = (SB * (1 - v)[None, :, None] + SP * v[None, :, None]).sum(axis=1) / NBIN * TREE_P
    got = np.where(YY >= 0, p[np.arange(len(YY)), np.maximum(YY, 0)],
                   BP if BP is not None else 0.0)
    return -np.log(np.clip(got, 1e-9, None))


def fit_alpha(SB, SP, YY, live, monotone=True, BP=None):
    best, best_s = None, np.inf
    for s0 in STARTS:
        v = np.full(NBIN, s0)
        for _ in range(6):
            for j in range(NBIN):
                if not live[j]:
                    continue
                lo_b = v[j - 1] if (monotone and j) else 0.0
                hi_b = v[j + 1] if (monotone and j < NBIN - 1) else 1.0
                cand = [g for g in GRID if lo_b - 1e-9 <= g <= hi_b + 1e-9] or [v[j]]
                v[j] = min(cand, key=lambda g: loss_vec(SB, SP, YY,
                                                        np.r_[v[:j], g, v[j + 1:]], BP).mean())
        sc = loss_vec(SB, SP, YY, v, BP).mean()
        if sc < best_s:
            best, best_s = v.copy(), sc
    return best


rng = np.random.default_rng(20260921)
acc = {r: np.zeros(nG) for r in ("ten bins", "one weight", "no mixing")}
seen = np.zeros(nG)
alphas, flats, live_count = [], [], np.zeros(NBIN)

for rep in range(OUTER):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        build_g = [g for g in gids if half[g] != fold]
        test = np.flatnonzero(side_of == fold)
        # --- inner: cards from one part, weights from the other, both ways
        inner = dict(zip(build_g, rng.permutation(np.arange(len(build_g)) % 2)))
        got = []
        for ip in (0, 1):
            tr = pa[pa["game_id"].map(lambda g: inner.get(g, -1)) == 1 - ip]
            idx = np.flatnonzero(pa["game_id"].map(lambda g: inner.get(g, -1)).to_numpy() == ip)
            t = tensors(tr, idx)
            if t is None:
                continue
            SB, SP, YY, _, BP = t
            live = (np.abs(SB - SP).max(axis=(0, 2)) > UNIFORM)
            live_count += live
            got.append((fit_alpha(SB, SP, YY, live, BP=BP),
                        fit_alpha(SB, SP, YY, np.ones(NBIN, bool) & live, monotone=False, BP=BP)))
            # one global weight: fit a single value shared by every bin
            flat = min(GRID, key=lambda g: loss_vec(SB, SP, YY, np.full(NBIN, g), BP).mean())
            got[-1] = (got[-1][0], flat)
        if not got:
            continue
        a_bins = np.mean([g[0] for g in got], axis=0)
        a_flat = float(np.mean([g[1] for g in got]))
        alphas.append(a_bins)
        flats.append(a_flat)
        # --- outer: rebuild on the whole build half, score the untouched half
        t = tensors(pa[side_of != fold], test)
        if t is None:
            continue
        SB, SP, YY, gg, BP = t
        for name, v in (("ten bins", a_bins), ("one weight", np.full(NBIN, a_flat)),
                        ("no mixing", np.zeros(NBIN))):
            np.add.at(acc[name], gg, loss_vec(SB, SP, YY, v, BP))
        np.add.at(seen, gg, 1.0)
    print(f"  outer {rep + 1}/{OUTER}", flush=True)

draws = np.random.default_rng(7).integers(0, nG, size=(2000, nG))
base = acc["one weight"]
rows = []
for name in ("no mixing", "one weight", "ten bins"):
    d = acc[name] - base
    bs = 1000 * d[draws].sum(axis=1) / seen[draws].sum(axis=1)
    rows.append({"rule": name,
                 "log loss x1000": round(1000 * acc[name].sum() / seen.sum(), 2),
                 "vs one weight": f"{1000 * d.sum() / seen.sum():+.2f} (SE {bs.std():.2f})"})
print(f"\nnested: weights fitted inside the build half only, {OUTER} outer x 2 folds\n")
print(pd.DataFrame(rows).to_string(index=False))
A = np.array(alphas)
print("\nfitted bin weights across the outer folds (median, and the middle half):")
print(pd.DataFrame({"bin": range(1, NBIN + 1),
                    "median a": np.median(A, axis=0).round(3),
                    "25th-75th": [f"{lo:.2f}-{hi:.2f}" for lo, hi in
                                  zip(np.percentile(A, 25, axis=0), np.percentile(A, 75, axis=0))],
                    "folds where the bin had anything to fit":
                        (live_count / (2 * OUTER * 2)).round(2)}).to_string(index=False))
print(f"\none global weight, median across folds: {np.median(flats):.3f}")

print("\nwhat sits in each bin, league-average player (% of the bin):")
lgv = pa["line"].value_counts(normalize=True).reindex(CARD_LINES).to_numpy()[ORD_I]
lgv = lgv / lgv.sum()
edges, lo = np.cumsum(lgv), np.concatenate([[0], np.cumsum(lgv)[:-1]])
rows2 = []
for j in range(NBIN):
    a_, b_ = j / NBIN, (j + 1) / NBIN
    ov = np.clip(np.minimum(edges, b_) - np.maximum(lo, a_), 0, None) * NBIN
    rows2.append({"bin": j + 1, **{ORDER[i]: (f"{100 * ov[i]:.0f}%" if ov[i] > 0.005 else "")
                                   for i in range(len(ORDER))}})
print(pd.DataFrame(rows2).to_string(index=False))
