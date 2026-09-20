"""Walks and HBP merged into one free-pass line (FP): 7-line cards vs the 8-line model.

Batters: true outcomes (K, FP, HR) | in park, with FP placed three ways (S1-S3); in-park
branch unchanged. Pitchers: 4-step tree with FP / in play at step 2. Every version is
scored against the same actual run values (BB and HBP valued separately), so merging
gets no credit for ignoring their difference.
 1. best k per structure on the usual 20 game splits, and key cards
 2. nested comparison (20 outer x 5 inner) against the 8-line structures
 3. log5 matchup on held-out games: best 7-line cards vs the 8-line cards"""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("freepass_cv.py", "chain_cv.py")
SRC = open(__file__, encoding="utf-8").read()
exec(SRC[:SRC.index("\ngids = sorted(")])
__file__ = _here
OUTER, INNER = 20, 5

LINES8 = list(ALL)
LINES7 = ["K", "FP", "HR", "1B", "2B", "ROE", "OUT"]
pa["line8"] = pa["line"]
pa["line7"] = pa["line"].replace({"BB": "FP", "HBP": "FP"})
W8 = np.array(w, dtype=float)
bb, hbp = int((pa["line8"] == "BB").sum()), int((pa["line8"] == "HBP").sum())
W7 = np.array([W8[0], (W8[1] * bb + W8[2] * hbp) / (bb + hbp)] + list(W8[3:]))
V_FINE = W8[y]                                       # actual run value, BB and HBP apart
WORLD = {"8": (LINES8, W8), "7": (LINES7, W7)}


def use(world):
    """Point the shared card machinery at the 8-line or 7-line world."""
    global ALL, IX, PA_, w
    ALL, w = list(WORLD[world][0]), WORLD[world][1]
    IX = {l: i for i, l in enumerate(ALL)}
    PA_ = tuple(ALL)
    pa["line"] = pa["line" + world]


P8, P7 = tuple(LINES8), tuple(LINES7)
CON = ("HR", "1B", "2B", "ROE", "OUT")
INP = ("1B", "2B", "ROE", "OUT")
IN_PARK = [(INP, [("1B",), ("2B", "ROE", "OUT")]), (("2B", "ROE", "OUT"), [("OUT",), ("2B", "ROE")]),
           (("2B", "ROE"), [("ROE",), ("2B",)])]
T8 = ("K", "BB", "HBP", "HR")
C8 = [(P8, [T8, INP]), (T8, [("HBP",), ("K", "BB", "HR")]), (("K", "BB", "HR"), [("HR",), ("K", "BB")]),
      (("K", "BB"), [("K",), ("BB",)])] + IN_PARK
T7 = ("K", "FP", "HR")
S1 = [(P7, [T7, INP]), (T7, [("FP",), ("K", "HR")]), (("K", "HR"), [("HR",), ("K",)])] + IN_PARK
S2 = [(P7, [T7, INP]), (T7, [("HR",), ("K", "FP")]), (("K", "FP"), [("K",), ("FP",)])] + IN_PARK
S3 = [(P7, [T7, INP]), (T7, [("K",), ("FP", "HR")]), (("FP", "HR"), [("FP",), ("HR",)])] + IN_PARK
HIT = ("HR", "1B", "2B")
TREE8 = [(P8, [("K",), ("BB", "HBP") + CON]), (("BB", "HBP") + CON, [("BB",), ("HBP",), CON]),
         (CON, [("OUT",), ("ROE",), HIT]), (HIT, [("HR",), ("1B",), ("2B",)])]
TREE7 = [(P7, [("K",), ("FP",) + CON]), (("FP",) + CON, [("FP",), CON]),
         (CON, [("OUT",), ("ROE",), HIT]), (HIT, [("HR",), ("1B",), ("2B",)])]
PLAN = {"B": {"8-line C": ("8", C8), "S1 FP|K+HR": ("7", S1), "S2 HR|K+FP": ("7", S2), "S3 K|FP+HR": ("7", S3)},
        "P": {"8-line tree": ("8", TREE8), "7-line tree": ("7", TREE7)}}
sname = lambda steps: " ; ".join(" | ".join("+".join(c) for c in parts) for _, parts in steps)


def hr_step(steps):
    return next(i for i, (_, parts) in enumerate(steps) if ("HR",) in parts)


def records(frame_idx, side, world, splits):
    """For each (build, test) pair: counts, cohorts, test PAs and card positions, in `world`."""
    use(world)
    out = []
    for build_idx, test in splits:
        X = counts(pa.loc[build_idx], side)
        out.append(((X, all_cohorts(side, X)), test, pos_of[side][pa.loc[test, side]].to_numpy()))
    return out


def halves(game_ids, n, rng):
    gl = sorted(game_ids)
    sub = pa[pa["game_id"].isin(gl)]
    res = []
    for _ in range(n):
        half = sub["game_id"].map(dict(zip(gl, rng.permutation(np.arange(len(gl)) % 2)))).to_numpy()
        for fold in (0, 1):
            res.append((sub.index[half != fold], sub.index[half == fold].to_numpy()))
    return res


def tune(steps, world, recs):
    use(world)
    prep = []
    for (X, coh), test, pos in recs:
        C = child_counts(X, steps)
        prep.append((C, targets(C, coh, hr_step(steps)), test, pos))

    def err(ks):
        tot, n = 0.0, 0
        for C, T, test, pos in prep:
            tot += float(((V_FINE[test] - (card(C, T, ks, steps) @ w)[pos]) ** 2).sum()); n += len(test)
        return tot / n
    ks = [64.0] * len(steps)
    for _ in range(2):
        for s in range(len(ks)):
            ks[s] = KGRID[int(np.argmin([err(ks[:s] + [k] + ks[s + 1:]) for k in KGRID]))]
    return ks


def full_card(side, world, steps, ks):
    use(world)
    X = counts(pa, side)
    coh = all_cohorts(side, X)
    C = child_counts(X, steps)
    return card(C, targets(C, coh, hr_step(steps)), ks, steps)


gids = sorted(pa["game_id"].unique())
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)


def boot_diff(d):
    bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
    return 1e6 * d.mean(), 1e6 * bt.std()


# ---------------- 1. best k on the usual 20 splits ----------------
std = halves(gids, REPEATS, np.random.default_rng(SEED))
best = {}
print("==================== 1. best k (usual 20 splits) ====================", flush=True)
for side, plan in PLAN.items():
    for label_, (world, steps) in plan.items():
        best[(side, label_)] = tune(steps, world, records(None, side, world, std))
        print(f"  {label_:12s} " + "; ".join(f"{' | '.join('+'.join(c) for c in parts)} {f(k)}"
                                       for (_, parts), k in zip(steps, best[(side, label_)])), flush=True)
names_b = [name.get(i, i) for i in people["B"]]
print("\n  key batters, % on card (8-line C: BB / HBP; 7-line: FP):")
for nm in ("Alexia Jorge", "Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Kylee Lahners"):
    i = names_b.index(nm)
    parts = []
    for label_, (world, steps) in PLAN["B"].items():
        cd = full_card("B", world, steps, best[("B", label_)])
        lines = WORLD[world][0]
        fp = cd[i, lines.index("BB")] + cd[i, lines.index("HBP")] if world == "8" else cd[i, lines.index("FP")]
        parts.append(f"{label_.split()[0]} FP {100 * fp:.1f} HR {100 * cd[i, lines.index('HR')]:.1f} K {100 * cd[i, lines.index('K')]:.1f}")
    print(f"    {nm:17s} " + " | ".join(parts))

# ---------------- 2. nested ----------------
print("\n==================== 2. nested comparison (20 outer x 5 inner) ====================", flush=True)
orng = np.random.default_rng(SEED + 31)
for side, plan in PLAN.items():
    err = {n_: np.zeros(len(pa)) for n_ in plan}
    for r in range(OUTER):
        half_of = dict(zip(gids, orng.permutation(np.arange(len(gids)) % 2)))
        half = pa["game_id"].map(half_of).to_numpy()
        for fold in (0, 1):
            build_games = [gg for gg in gids if half_of[gg] != fold]
            inner = halves(build_games, INNER, orng)
            outer = [(pa.index[half != fold], np.flatnonzero(half == fold))]
            for world in ("8", "7"):
                inner_recs = records(None, side, world, inner)
                (Xo, coho), test, pos = records(None, side, world, outer)[0]
                for label_, (wld, steps) in plan.items():
                    if wld != world:
                        continue
                    ks = tune(steps, world, inner_recs)
                    use(world)
                    C = child_counts(Xo, steps)
                    T = targets(C, coho, hr_step(steps))
                    err[label_][test] += (V_FINE[test] - (card(C, T, ks, steps) @ w)[pos]) ** 2
        print(f"  {side}: outer {r + 1}/{OUTER}", flush=True)
    ref = list(plan)[0]
    for label_ in list(plan)[1:]:
        m, se = boot_diff((err[label_] - err[ref]) / OUTER)
        print(f"  {'batters' if side == 'B' else 'pitchers'}: {label_} minus {ref}: {m:+.0f} x1e-6 per PA, SE {se:.0f}"
              f"  (negative = free pass better)", flush=True)

# ---------------- 3. log5 matchup: best 7-line cards vs 8-line cards ----------------
print("\n==================== 3. log5 matchup on held-out games (usual 20 splits) ====================", flush=True)
COMBOS = {"8-line": ("8", "8-line C", "8-line tree")}
COMBOS.update({f"7-line {s.split()[0]}": ("7", s, "7-line tree") for s in ("S1 FP|K+HR", "S2 HR|K+FP", "S3 K|FP+HR")})
errs = {c: np.zeros(len(pa)) for c in COMBOS}
for build_idx, test in std:
    for combo, (world, bname, pname) in COMBOS.items():
        use(world)
        Lw = pa.loc[build_idx, "line"].value_counts(normalize=True).reindex(ALL, fill_value=0).to_numpy()
        cards = {}
        for side, nm in (("B", bname), ("P", pname)):
            steps = PLAN[side][nm][1]
            X = counts(pa.loc[build_idx], side)
            coh = all_cohorts(side, X)
            C = child_counts(X, steps)
            cards[side] = card(C, targets(C, coh, hr_step(steps)), best[(side, nm)], steps)
        Bc = cards["B"][pos_of["B"][pa.loc[test, "B"]].to_numpy()]
        Pc = cards["P"][pos_of["P"][pa.loc[test, "P"]].to_numpy()]
        q = Bc * Pc / Lw
        q /= q.sum(axis=1, keepdims=True)
        errs[combo][test] += (V_FINE[test] - q @ w) ** 2
for combo in list(COMBOS)[1:]:
    m, se = boot_diff((errs[combo] - errs["8-line"]) / REPEATS)
    print(f"  {combo} (with 7-line pitcher tree) minus 8-line: {m:+.0f} x1e-6 per PA, SE {se:.0f}  (negative = free pass better)")
print("  (k tuned on these same splits for every model; the nested results above are the fair test)")
