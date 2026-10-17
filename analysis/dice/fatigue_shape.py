"""The fresh -> fading SHAPE from the whole season, line by line.

    pixi run python analysis/dice/fatigue_shape.py

User (12 Oct): the fatigue shape should not rest on one abnormal game (semifinal
G3, `dice.G3_RATIO`); fresh against fading is the thing to get right, and the
whole season has plenty of it.

For each card line (K, BB, HBP, HR, 1B, OUT): how much more or less often it
happens in a pitcher's later innings than in her own first inning, after taking
out the batters she faced.

  paired      only outings with a first inning and at least one later inning,
              the same outings on both sides, so who pitches cannot masquerade
              as fatigue (spec 7.2)
  batters     each plate appearance's expected chance of each line is the
              batter's and the pitcher's cards mixed as the game mixes them
              (MIX_ALPHA), so the top of the order in the first inning is
              accounted for
  ratio       (observed / expected, later innings) / (observed / expected, first)
  two ways    (A) her final inning -- the one she was removed in -- dropped,
              as fatigue_curve.py does; (B) kept. Survivorship hides fatigue,
              the removal inning exaggerates it, so the truth is likely between
              (user)
  error       1,000 resamples of whole outings: 90% intervals

Then the run value of one shift by each shape, measured as rules_check measures
the fresh -> fading step (today's G3 shift: +0.018 runs per plate appearance).
"""
import numpy as np
import pandas as pd

from wpbl import dice, tables
from wpbl.dice import MIX_ALPHA, TO_LINE, cards

LINES = ["K", "BB", "HBP", "HR", "1B", "OUT", "2B", "ROE"]   # 2B and ROE: fixed bands in the game, measured anyway
CARD = 6                                            # the first six are on the cards
rng = np.random.default_rng(20261012)

pl = tables.read("players", "training")
person = pl.set_index("player_id")["person_id"].to_dict()
p = tables.read("plays", "all")
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
B, P = cards("B"), cards("P")
league = pa["line"].value_counts(normalize=True)
lg = np.array([league.get(l, 0.0) for l in LINES])


def probs(frame, ids):
    m = frame.reindex(ids)[LINES].to_numpy(float)
    return np.where(np.isnan(m), lg, m)


exp = MIX_ALPHA * probs(P, pa["P"]) + (1 - MIX_ALPHA) * probs(B, pa["B"])
obs = np.column_stack([(pa["line"] == l).to_numpy(float) for l in LINES])
pa = pa.reset_index(drop=True)
pa = pa.sort_values(["game_id", "sequence"])
order = pa.index.to_numpy()
exp, obs = exp[order], obs[order]
pa = pa.reset_index(drop=True)

inn_n = np.zeros(len(pa), int)
n_inn = np.zeros(len(pa), int)
outing = np.zeros(len(pa), int)
for k, (_, grp) in enumerate(pa.groupby(["game_id", "pitcher_id"], sort=False)):
    innings = list(dict.fromkeys(grp["inning"]))
    inn_n[grp.index] = [innings.index(i) + 1 for i in grp["inning"]]
    n_inn[grp.index] = len(innings)
    outing[grp.index] = k


def shape(drop_final):
    later = inn_n >= 2
    if drop_final:
        later &= inn_n < n_inn
    first = inn_n == 1
    keep_out = np.intersect1d(np.unique(outing[first]), np.unique(outing[later]))
    rows = []
    for o in keep_out:
        m = outing == o
        rows.append((obs[m & first].sum(0), exp[m & first].sum(0),
                     obs[m & later].sum(0), exp[m & later].sum(0)))
    O1, E1, O2, E2 = (np.array(x) for x in zip(*rows))

    def ratio(idx):
        return (O2[idx].sum(0) / E2[idx].sum(0)) / (O1[idx].sum(0) / E1[idx].sum(0))

    point = ratio(np.arange(len(rows)))
    boots = np.array([ratio(rng.integers(0, len(rows), len(rows))) for _ in range(1000)])
    lo, hi = np.percentile(boots, [5, 95], axis=0)
    n_first, n_later = int(O1.sum()), int(O2.sum())
    shape.boots[drop_final] = boots
    shape.keep[drop_final] = keep_out
    return point, lo, hi, len(rows), n_first, n_later, O1.sum(0), O2.sum(0)


shape.boots, shape.keep = {}, {}


def step_of(ratio):
    """One shift by this shape, as rules_check measures the fresh -> fading step."""
    saved = dict(dice.G3_RATIO)
    dice.G3_RATIO.update(dict(zip(LINES[:CARD], ratio[:CARD])))
    try:
        Pc = cards("P")
        w = dice.line_weights()
        cc = {k: dice.to_cells(dice.fatigue_card(Pc.to_numpy(), lam), dice.P_CELLS, w, True)
              for k, lam in (("fresh", 0.0), ("fading", 1.0))}
        use = dice.plate_appearances().groupby("P").size().reindex(Pc.index).fillna(0).to_numpy(float)
        use /= use.sum()
        v = {k: float(((c * w).sum(axis=1) / 100.0 * use).sum()) for k, c in cc.items()}
        unrounded = {}
        for k, lam in (("fresh", 0.0), ("fading", 1.0)):
            card = dice.fatigue_card(Pc.to_numpy(), lam)
            idx = [dice.CARD_LINES.index(l) for l in dice.TREE_LINES]
            tree = card[:, idx]
            unrounded[k] = float(((tree / tree.sum(1, keepdims=True) * dice.P_CELLS * w).sum(1)
                                  / 100.0 * use).sum())
        return v["fading"] - v["fresh"], unrounded["fading"] - unrounded["fresh"]
    finally:
        dice.G3_RATIO.clear()
        dice.G3_RATIO.update(saved)


print(f"{len(pa)} plate appearances, {outing.max() + 1} outings, every 2026 game\n")
g3 = np.array([dice.G3_RATIO.get(l, np.nan) for l in LINES])
results = {}
for label, drop in (("(A) removal inning dropped", True), ("(B) removal inning kept", False)):
    point, lo, hi, n, nf, nl, o1, o2 = shape(drop)
    results[label] = point
    print(f"{label}: {n} outings, {nf} plate appearances in first innings, {nl} later")
    print(f"  {'line':4s} {'first':>6s} {'later':>6s} {'ratio':>7s}   90% interval   G3")
    for j, l in enumerate(LINES):
        print(f"  {l:4s} {int(o1[j]):6d} {int(o2[j]):6d} {point[j]:7.3f}   {lo[j]:5.2f}-{hi[j]:5.2f}   {g3[j]:.3f}")
    print()
print("one shift's run value (runs per plate appearance; rules_check's step, cells / unrounded):")
for label, r in [("G3 (today)", g3)] + list(results.items()):
    rc, ur = step_of(r)
    print(f"  {label:28s} {rc:+.4f} / {ur:+.4f}")


# --- variant (B), the user's choice: shrinkage, doubles, running plays (12 Oct) -----------
# Shrink each line's log ratio toward 0 (no change) by its own uncertainty. The
# spread of the TRUE log ratios across lines, tau, is estimated from the lines
# themselves: the observed spread minus the measurement noise (method of moments).
point = results["(B) removal inning kept"]
boots = shape.boots[False]
m = ~np.isnan(point)
logp = np.log(point[m])
se = np.log(boots[:, m]).std(axis=0)
tau2 = max(0.0, float(np.mean(logp ** 2) - np.mean(se ** 2)))
weight = tau2 / (tau2 + se ** 2)
shrunk = np.full(len(LINES), np.nan)
shrunk[m] = np.exp(weight * logp)
print(f"\nshrinkage, variant (B): tau (spread of the true log ratios) = {np.sqrt(tau2):.3f}")
print(f"  {'line':4s} {'measured':>9s} {'SE of log':>10s} {'weight':>7s} {'shrunk':>7s}")
for j, l in enumerate([l for l, ok in zip(LINES, m) if ok]):
    k = LINES.index(l)
    print(f"  {l:4s} {point[k]:9.3f} {se[j]:10.3f} {weight[j]:7.2f} {shrunk[k]:7.3f}")
rc, ur = step_of(shrunk)
print(f"  one shift by the shrunk shape: {rc:+.4f} / {ur:+.4f} runs per plate appearance")

# doubles in percentage points, the same outings
keep = np.isin(outing, shape.keep[False])
first, later = keep & (inn_n == 1), keep & (inn_n >= 2)
j2 = LINES.index("2B")
for label, mm in (("first innings", first), ("later innings", later)):
    print(f"doubles, {label}: {int(obs[mm, j2].sum())} of {int(mm.sum())} plate appearances = "
          f"{100 * obs[mm, j2].mean():.2f}%  (expected from the cards {100 * exp[mm, j2].mean():.2f}%)")
print(f"league: doubles {100 * league.get('2B', 0):.2f}% of plate appearances (the band is 4 of 100 rolls)")

# running plays: wild pitch, passed ball, balk, per plate appearance with a runner on
runs = p[((p["play_kind"] == "baserunning") & p["event_type"].isin(["wild_pitch", "passed_ball"]))
         | (p["play_kind"] == "balk")].dropna(subset=["pitcher_id"])
on = (pa["first_base"].notna() | pa["second_base"].notna() | pa["third_base"].notna()).to_numpy()
key = pd.Series(np.arange(len(pa)))
grp = pa.assign(o=outing, i=inn_n)
inn_of = grp.drop_duplicates(["game_id", "pitcher_id", "inning"]).set_index(
    ["game_id", "pitcher_id", "inning"])[["o", "i"]]
ev = runs.join(inn_of, on=["game_id", "pitcher_id", "inning"], how="inner")
ev = ev[ev["o"].isin(shape.keep[False])]
print(f"\nrunning plays (wild pitch, passed ball, balk) in these outings: {len(ev)} "
      f"of {len(runs)} in the season")
for label, mm, sel in (("first innings", first, ev["i"] == 1), ("later innings", later, ev["i"] >= 2)):
    opp = int((mm & on).sum())
    print(f"  {label}: {int(sel.sum())} running plays in {opp} plate appearances with a runner on = "
          f"{100 * sel.sum() / opp:.2f}%  ({100 * sel.sum() / int(mm.sum()):.2f}% of all plate appearances)")


# --- flat against hierarchical, two steps (user, 12 Oct) ----------------------------------
# Flat: one multiplier per outcome (K, BB, HBP, OUT, 1B, 2B, HR), renormalised.
# Hierarchical: (a) K / BB / HBP / ball in play, renormalised; (b) within balls in
# play, OUT / 1B / 2B / HR shares, renormalised within play. Each level measured
# as observed / expected, later innings against first (variant B, same outings),
# and shrunk toward 1 by its own uncertainty with its own tau.
from wpbl.batters import plate_appearances as bat_pa

ALL = ["K", "BB", "HBP", "OUT", "1B", "2B", "HR"]
BIP = ["OUT", "1B", "2B", "HR"]
ix = {l: LINES.index(l) for l in ALL}
keep_o = shape.keep[False]
grp_rows = []
for o in keep_o:
    mm = outing == o
    f, la = mm & (inn_n == 1), mm & (inn_n >= 2)
    grp_rows.append((obs[f].sum(0), exp[f].sum(0), obs[la].sum(0), exp[la].sum(0)))
O1, E1, O2, E2 = (np.array(x) for x in zip(*grp_rows))


def level_ratios(idx):
    o1, e1, o2, e2 = O1[idx].sum(0), E1[idx].sum(0), O2[idx].sum(0), E2[idx].sum(0)
    flat = np.array([(o2[ix[l]] / e2[ix[l]]) / (o1[ix[l]] / e1[ix[l]]) for l in ALL])
    def tot(v, ls):
        return sum(v[ix[l]] for l in ls)
    top = ["K", "BB", "HBP"]
    a = np.array([(o2[ix[l]] / e2[ix[l]]) / (o1[ix[l]] / e1[ix[l]]) for l in top]
                 + [(tot(o2, BIP) / tot(e2, BIP)) / (tot(o1, BIP) / tot(e1, BIP))])
    b = np.array([((o2[ix[l]] / tot(o2, BIP)) / (e2[ix[l]] / tot(e2, BIP)))
                  / ((o1[ix[l]] / tot(o1, BIP)) / (e1[ix[l]] / tot(e1, BIP))) for l in BIP])
    return flat, a, b


n_o = len(grp_rows)
pt = level_ratios(np.arange(n_o))
bs = [level_ratios(rng.integers(0, n_o, n_o)) for _ in range(1000)]


def shrink(point, boots):
    lp = np.log(point)
    se = np.log(np.array(boots)).std(axis=0)
    t2 = max(0.0, float(np.mean(lp ** 2) - np.mean(se ** 2)))
    return np.exp(lp * t2 / (t2 + se ** 2)), np.sqrt(t2)


flat_s, tf = shrink(pt[0], [b[0] for b in bs])
a_s, ta = shrink(pt[1], [b[1] for b in bs])
b_s, tb = shrink(pt[2], [b[2] for b in bs])
print("\nFLAT vs HIERARCHICAL (variant B, shrunk)")
print(f"  flat tau {tf:.3f}: " + "  ".join(f"{l} {r:.3f}" for l, r in zip(ALL, flat_s)))
print(f"  (a) tau {ta:.3f}: " + "  ".join(f"{l} {r:.3f}" for l, r in zip(["K", "BB", "HBP", "BIP"], a_s))
      + "      measured: " + "  ".join(f"{r:.3f}" for r in pt[1]))
print(f"  (b) tau {tb:.3f}: " + "  ".join(f"{l} {r:.3f}" for l, r in zip(BIP, b_s))
      + "      measured: " + "  ".join(f"{r:.3f}" for r in pt[2]))

lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean()
w = np.array([W[l] for l in ALL])
p0 = np.array([league.get(l, 0.0) for l in ALL])
p0 = p0 / p0.sum()


def flat_steps(k):
    q = p0 * flat_s ** k
    return q / q.sum()


def hier_steps(k):
    top = np.array([p0[0], p0[1], p0[2], p0[3:].sum()]) * a_s ** k
    top = top / top.sum()
    inner = p0[3:] / p0[3:].sum() * b_s ** k
    inner = inner / inner.sum()
    return np.concatenate([top[:3], top[3] * inner])


print(f"\n  league plate appearance, 0 / 1 / 2 steps (rates in %; run value per PA vs fresh)")
print(f"  {'model':6s} {'steps':>5s}  " + "  ".join(f"{l:>5s}" for l in ALL) + "     run value")
v0 = float(p0 @ w)
for name, fn in (("flat", flat_steps), ("hier", hier_steps)):
    for k in (0, 1, 2):
        q = fn(k)
        print(f"  {name:6s} {k:5d}  " + "  ".join(f"{100 * x:5.1f}" for x in q) + f"     {float(q @ w) - v0:+.4f}")


# --- the v0.8.0 shape: hierarchical, doubles out of it (user, 12 Oct) --------------------
# Doubles and running plays become fixed cells on the pitcher card (doubles 4/5/6,
# running plays 5/6/7 for fresh/fading/gassed), so the shape is refit WITHOUT
# doubles: (a) K / BB / HBP / other balls in play, (b) OUT / 1B / HR within them.
BIP3 = ["OUT", "1B", "HR"]


def level_ratios3(idx):
    o1, e1, o2, e2 = O1[idx].sum(0), E1[idx].sum(0), O2[idx].sum(0), E2[idx].sum(0)
    def tot(v, ls):
        return sum(v[ix[l]] for l in ls)
    a = np.array([(o2[ix[l]] / e2[ix[l]]) / (o1[ix[l]] / e1[ix[l]]) for l in ["K", "BB", "HBP"]]
                 + [(tot(o2, BIP3) / tot(e2, BIP3)) / (tot(o1, BIP3) / tot(e1, BIP3))])
    b = np.array([((o2[ix[l]] / tot(o2, BIP3)) / (e2[ix[l]] / tot(e2, BIP3)))
                  / ((o1[ix[l]] / tot(o1, BIP3)) / (e1[ix[l]] / tot(e1, BIP3))) for l in BIP3])
    return a, b


pt3 = level_ratios3(np.arange(n_o))
bs3 = [level_ratios3(rng.integers(0, n_o, n_o)) for _ in range(1000)]
a3, ta3 = shrink(pt3[0], [b[0] for b in bs3])
b3, tb3 = shrink(pt3[1], [b[1] for b in bs3])
print("\nv0.8.0 SHAPE: hierarchical, doubles fixed in cells (variant B, shrunk)")
print(f"  (a) tau {ta3:.3f}: " + "  ".join(f"{l} {r:.3f}" for l, r in zip(["K", "BB", "HBP", "BIP"], a3))
      + "      measured: " + "  ".join(f"{r:.3f}" for r in pt3[0]))
print(f"  (b) tau {tb3:.3f}: " + "  ".join(f"{l} {r:.3f}" for l, r in zip(BIP3, b3))
      + "      measured: " + "  ".join(f"{r:.3f}" for r in pt3[1]))

# preview: the league pitcher's own six lines on 34 / 32 / 30 cells, 0 / 1 / 2 steps
OWN = ["K", "BB", "HBP", "OUT", "1B", "HR"]
own0 = np.array([league.get(l, 0.0) for l in OWN])
own0 = own0 / own0.sum()


def own_steps(k):
    top = np.array([own0[0], own0[1], own0[2], own0[3:].sum()]) * a3 ** k
    top = top / top.sum()
    inner = own0[3:] / own0[3:].sum() * b3 ** k
    inner = inner / inner.sum()
    return np.concatenate([top[:3], top[3] * inner])


print("\n  league pitcher card, uncentred preview (cells of the 43-cell pitcher block)")
print(f"  {'column':7s} " + "  ".join(f"{l:>5s}" for l in OWN) + "     2B   RUN   own cells")
for k, (name, cells, d2, rp) in enumerate((("fresh", 34, 4, 5), ("fading", 32, 5, 6), ("gassed", 30, 6, 7))):
    q = own_steps(k) * cells
    print(f"  {name:7s} " + "  ".join(f"{x:5.1f}" for x in q) + f"   {d2:4d}  {rp:4d}   {cells}")
