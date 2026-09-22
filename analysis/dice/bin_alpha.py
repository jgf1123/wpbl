"""Fit the ten bin weights, given the cards.

    pixi run python analysis/dice/bin_alpha.py

Layout: each player's lines are laid end to end in one fixed order, lowest
mixing weight first, and the 100 cells are cut into ten bins of ten. A line may
straddle a boundary; bin j on her card is whatever lines cover cells 10j..10j+9.

Given the cards, fitting the weights is a least-squares problem, not a search.
With s_X(j, L) the share of bin j that line L covers on card X, and v_X(j) that
bin's run value, the expected runs of a plate appearance are

    sum_j 0.1 * [ v_B(j) + a_j * ( v_P(j) - v_B(j) ) ]

linear in the ten a_j, so squared error is quadratic in them and solves in
closed form. (The hard direction is the other one: k moves the cards, which
moves every bin's contents.)

Weights should come out increasing, because the lines were sorted that way. If
they do not, the sort or the fit is wrong.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, TO_LINE, band_2b, build,
                       plate_appearances, usage)

pd.set_option("display.width", 240)
NBIN, SPLITS = 10, 10
# lowest mixing weight first; ties (1B/K both 0.30) broken by run value, and 2B
# parked at the Out -> BB jump because it is identical on both cards.
ORDER = ["HR", "HBP", "1B", "K", "OUT", "2B", "BB", "ROE"]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares, two_b = usage(pa), band_2b(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES).to_numpy()
y = pa["line"].map(IX).to_numpy()
ORD_I = [IX[l] for l in ORDER]


def bin_shares(card):
    """Share of each bin taken by each line, per player: cards x NBIN x lines."""
    p = card[:, ORD_I]                                   # lines in layout order
    edges = np.cumsum(p, axis=1)
    lo = np.concatenate([np.zeros((len(p), 1)), edges[:, :-1]], axis=1)
    out = np.zeros((len(p), NBIN, len(ORD_I)))
    for j in range(NBIN):
        a, b = j / NBIN, (j + 1) / NBIN
        out[:, j, :] = np.clip(np.minimum(edges, b) - np.maximum(lo, a), 0, None) * NBIN
    return out


def bin_value(card):
    return (bin_shares(card) * W[ORD_I]).sum(axis=2)


def make(frame, side, steps, ks):
    X = pd.crosstab(frame[side], frame["line"]).reindex(columns=LINES, fill_value=0)
    ids = X.index.to_numpy()
    nms = [players["person_name"].get(i, i) for i in ids]
    c = build(X.to_numpy().astype(float), nms,
              shares[side].reindex(ids).fillna(0).to_numpy(), steps, ks,
              SLUGGERS if side == "B" else (), two_b)
    return pd.DataFrame(c, index=ids, columns=CARD_LINES)


rng = np.random.default_rng(20260921)
A, rhs, SB, SP, YY = [], [], [], [], []
for _ in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        cb, cp = make(tr, "B", BATTER_STEPS, BATTER_K), make(tr, "P", PITCHER_STEPS, PITCHER_K)
        ok = [i for i in te if pa["B"].iloc[i] in cb.index and pa["P"].iloc[i] in cp.index]
        if not ok:
            continue
        sb = bin_shares(cb.loc[pa["B"].iloc[ok]].to_numpy())
        sp = bin_shares(cp.loc[pa["P"].iloc[ok]].to_numpy())
        vb, vp = (sb * W[ORD_I]).sum(axis=2) / NBIN, (sp * W[ORD_I]).sum(axis=2) / NBIN
        A.append(vp - vb)                    # coefficient on each a_j
        rhs.append(W[y[ok]] - vb.sum(axis=1))
        SB.append(sb.astype(np.float32))
        SP.append(sp.astype(np.float32))
        YY.append(np.array([ORDER.index(CARD_LINES[y[i]]) for i in ok]))
A = np.vstack(A)
rhs = np.concatenate(rhs)
alpha_raw, *_ = np.linalg.lstsq(A, rhs, rcond=None)
# How much can a bin's weight move anything? If both cards say the same thing in
# bin j -- and bins 5-8 are pure Out for nearly everyone -- then v_P(j) = v_B(j),
# the column is ~zero, a_j is unidentified, and plain least squares answers with
# whatever shrinks the residual by accident: 22.3, -256.0.
lev = np.abs(A).mean(axis=0)
print(f"{len(rhs)} held-out plate appearances over {SPLITS} splits x 2 folds")
print("\nhow much each bin's weight can move expected runs (mean |v_P - v_B| / 10):")
print(pd.DataFrame({"bin": range(1, NBIN + 1), "leverage x1000": (1000 * lev).round(2),
                    "unconstrained a": np.round(alpha_raw, 2)}).to_string(index=False))

GR = np.round(np.arange(0, 1.0001, 0.05), 2)
alpha = np.full(NBIN, 0.4)


def sse(v):
    return float(((A @ v - rhs) ** 2).sum())


for _ in range(6):                       # 0 <= a1 <= ... <= a10 <= 1
    for j in range(NBIN):
        lo_b = alpha[j - 1] if j else 0.0
        hi_b = alpha[j + 1] if j < NBIN - 1 else 1.0
        cand = [g for g in GR if lo_b - 1e-9 <= g <= hi_b + 1e-9] or [alpha[j]]
        alpha[j] = min(cand, key=lambda g: sse(np.r_[alpha[:j], g, alpha[j + 1:]]))
print("\nconstrained fit (0 <= a1 <= ... <= a10 <= 1):")
print(pd.DataFrame({"bin": range(1, NBIN + 1), "a": alpha,
                    "identified?": ["yes" if l > 1e-4 else "NO - both cards agree"
                                    for l in lev]}).to_string(index=False))
print(f"\nSSE: unconstrained {sse(alpha_raw):.1f}, constrained {sse(alpha):.1f}, "
      f"flat 0.4 {sse(np.full(NBIN, 0.4)):.1f}, no mixing {sse(np.zeros(NBIN)):.1f}")

print("\nwhat sits in each bin, league-average player (% of the bin):")
lg = pa["line"].value_counts(normalize=True).reindex(CARD_LINES).to_numpy()[None, :]
p = lg[:, ORD_I][0]
edges, lo = np.cumsum(p), np.concatenate([[0], np.cumsum(p)[:-1]])
rows = []
for j in range(NBIN):
    a, b = j / NBIN, (j + 1) / NBIN
    ov = np.clip(np.minimum(edges, b) - np.maximum(lo, a), 0, None) * NBIN
    rows.append({"bin": j + 1, **{ORDER[i]: (f"{100 * ov[i]:.0f}%" if ov[i] > 0.005 else "")
                                  for i in range(len(ORDER))}})
print(pd.DataFrame(rows).to_string(index=False))


# ---------------- the same fit on log loss, and on a finer grid ----------------
# Run value cannot tell a walk from an error (both "reaches first", +0.45 and
# +0.50), and bin 10 is exactly those two -- so the bin that should most want the
# pitcher has almost nothing for a runs fit to grip. Log loss can see it.
SB = np.concatenate(SB)
SP = np.concatenate(SP)
YY = np.concatenate(YY)
rows_pa = np.arange(len(YY))


def logloss(v):
    p = (SB * (1 - v)[None, :, None] + SP * v[None, :, None]).sum(axis=1) / NBIN
    return float(-np.log(np.clip(p[rows_pa, YY], 1e-9, None)).mean())


def fit(objective, grid, starts):
    best, best_s = None, np.inf
    for s0 in starts:
        v = np.full(NBIN, s0)
        for _ in range(8):
            for j in range(NBIN):
                lo_b = v[j - 1] if j else 0.0
                hi_b = v[j + 1] if j < NBIN - 1 else 1.0
                cand = [g for g in grid if lo_b - 1e-9 <= g <= hi_b + 1e-9] or [v[j]]
                v[j] = min(cand, key=lambda g: objective(np.r_[v[:j], g, v[j + 1:]]))
        sc = objective(v)
        if sc < best_s:
            best, best_s = v.copy(), sc
    return best, best_s


FINE = np.round(np.arange(0, 1.0001, 0.025), 3)
STARTS = [0.0, 0.2, 0.4, 0.6, 0.8]
a_runs, s_runs = fit(sse, FINE, STARTS)
a_ll, s_ll = fit(logloss, FINE, STARTS)
print("\n=== finer grid (0.025) and five starting points ===")
print(pd.DataFrame({"bin": range(1, NBIN + 1),
                    "a by runs": a_runs, "a by log loss": a_ll,
                    "identified?": ["yes" if l > 1e-4 else "no" for l in lev]}).to_string(index=False))
print(f"\nlog loss: fitted {1000 * s_ll:.2f}, flat 0.4 {1000 * logloss(np.full(NBIN, 0.4)):.2f}, "
      f"no mixing {1000 * logloss(np.zeros(NBIN)):.2f}, all pitcher {1000 * logloss(np.ones(NBIN)):.2f}")
print(f"runs SSE: fitted {s_runs:.1f} (earlier coarse fit {sse(alpha):.1f})")
