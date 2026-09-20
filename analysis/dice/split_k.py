"""k for the per-player walk | HBP split of a free pass, chosen two ways, plus S2 k stability.

Held-out free passes only (usual 20 game splits). A player's HBP share of her free passes
is smoothed toward her usage cohort's: (HBP + k * cohort share) / (FP + k). Scored by
 1. pitches: squared error of predicted pitches (share-weighted walk / HBP means from the
    build half) against the PA's actual pitch count;
 2. log-likelihood of walk vs HBP.
Then nested (20 x 5) tuning of the S2 batter structure, for the medians of each tuned k."""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("split_k.py", "freepass_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("# ---------------- 1. best k")])
__file__ = _here
use("8")
pitches = pa["n_pitches_est"].to_numpy().astype(float)
fp_mask = pa["line8"].isin(["BB", "HBP"]).to_numpy()
is_hbp = (pa["line8"] == "HBP").to_numpy()
std = halves(gids, REPEATS, np.random.default_rng(SEED))

for side in ("B", "P"):
    S_p = {k: np.zeros(len(pa)) for k in range(len(KGRID))}
    S_l = {k: np.zeros(len(pa)) for k in range(len(KGRID))}
    for build_idx, test in std:
        b = pa.loc[build_idx]
        X = counts(b, side)                              # 8-line counts, BB = col 1, HBP = col 2
        base, _, _ = all_cohorts(side, X)
        fp = X[:, 1] + X[:, 2]
        hb = X[:, 2]
        cf = np.array([fp[c].sum() for c in base])
        ch = np.array([hb[c].sum() for c in base])
        t = np.where(cf > 0, ch / np.maximum(cf, 1), hb.sum() / fp.sum())
        bfp = b[b["line8"].isin(["BB", "HBP"])]
        c_bb = bfp.loc[bfp["line8"] == "BB", "n_pitches_est"].mean()
        c_hbp = bfp.loc[bfp["line8"] == "HBP", "n_pitches_est"].mean()
        tt = test[fp_mask[test]]
        pos = pos_of[side][pa.loc[tt, side]].to_numpy()
        for j, k in enumerate(KGRID):
            hshare = t if np.isinf(k) else (hb + k * t) / (fp + k)
            s = np.clip(hshare[pos], 1e-6, 1 - 1e-6)
            S_p[j][tt] += (pitches[tt] - (s * c_hbp + (1 - s) * c_bb)) ** 2
            S_l[j][tt] += np.where(is_hbp[tt], np.log(s), np.log(1 - s))
    label = "batters" if side == "B" else "pitchers"
    print(f"\n=== {label}: walk | HBP split, {int(fp_mask.sum())} free passes ===")
    for obj, S, better in (("pitches (squared error)", S_p, "min"), ("log-likelihood", S_l, "max")):
        M = np.stack([S[j] / REPEATS for j in range(len(KGRID))], axis=1)[fp_mask]
        gg = g[fp_mask]
        G = np.stack([np.bincount(gg, weights=M[:, j], minlength=nG) for j in range(M.shape[1])], axis=1)
        cn = np.bincount(gg, minlength=nG).astype(float)
        pt, bt = M.mean(axis=0), (Wb @ G) / (Wb @ cn)[:, None]
        b_ = int(np.argmin(pt) if better == "min" else np.argmax(pt))
        near = [KGRID[j] for j in range(len(KGRID)) if abs(pt[j] - pt[b_]) <= (bt[:, j] - bt[:, b_]).std()]
        worse_inf = (pt[-1] - pt[b_]) if better == "min" else (pt[b_] - pt[-1])
        print(f"  {obj:24s} best k {f(KGRID[b_]):>5s}; within 1 SE {f(min(near))}-{f(max(near))}; "
              f"cohort-only (inf) worse by {worse_inf:.4f} (SE {(bt[:, -1] - bt[:, b_]).std():.4f})")

# ---- nested tuning of S2 (batters), for the stability column ----
print("\n=== S2 batter structure, k tuned inside each build half (20 x 5) ===", flush=True)
orng = np.random.default_rng(SEED + 37)
chosen = []
for r in range(OUTER):
    half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
    for fold in (0, 1):
        inner = halves([gg for gg in gids if half_of[gg] != fold], INNER, orng)
        chosen.append(tune(S2, "7", records(None, "B", "7", inner)))
a = np.log2(np.clip(np.array(chosen), 1, 4096))
for (_, parts), md, lo, hi in zip(S2, np.median(a, axis=0), np.percentile(a, 25, axis=0), np.percentile(a, 75, axis=0)):
    print(f"  {' | '.join('+'.join(c) for c in parts):28s} median {f(2 ** md)} (middle half {f(2 ** lo)}-{f(2 ** hi)})")
