"""Does keeping BB/HBP and 1B/ROE apart make the log5 matchup prediction more accurate?

Production cards (wpbl.dice) built on random game halves; held-out PAs predicted by
flat log5 of the batter and pitcher cards. Merged versions sum the cards' (and the
league's) probabilities before log5; a merged line is valued at the PA-weighted mean
run value of its members. Score: squared error of expected run value per PA."""
import numpy as np
import pandas as pd
from wpbl import tables, dice
from wpbl.batters import plate_appearances

REPEATS, BOOT, SEED = 20, 2000, 20260919
L8 = dice.LINES
pa = dice.plate_appearances()
shares = dice.usage(pa)
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
lw = plate_appearances("training")
lw["line"] = lw["outcome"].map(dice.TO_LINE).fillna("OUT")
w = lw.groupby("line")["run_value"].mean().reindex(L8).to_numpy()
freq = lw["line"].value_counts().reindex(L8).to_numpy().astype(float)
y = pa["line"].map({l: i for i, l in enumerate(L8)}).to_numpy()
ids = {s: np.array(sorted(pa[s].unique())) for s in ("B", "P")}
names = {s: [players["person_name"].get(i, i) for i in ids[s]] for s in ("B", "P")}
pos = {s: pd.Series(np.arange(len(ids[s])), index=ids[s])[pa[s]].to_numpy() for s in ("B", "P")}
SPEC = {"B": (dice.BATTER_STEPS, dice.BATTER_K), "P": (dice.PITCHER_STEPS, dice.PITCHER_K)}
VERSIONS = {"8 lines": [], "BB+HBP merged": [("BB", "HBP")], "1B+ROE merged": [("1B", "ROE")],
            "both merged": [("BB", "HBP"), ("1B", "ROE")]}


def groups(merges):
    """List of index lists: merged groups plus every untouched line."""
    used = {l for m in merges for l in m}
    return [[L8.index(l) for l in m] for m in merges] + [[i] for i, l in enumerate(L8) if l not in used]


def predict(Bc, Pc, L, merges):
    """Expected run value per PA under flat log5 on the (possibly merged) lines."""
    G = groups(merges)
    b = np.column_stack([Bc[:, g].sum(axis=1) for g in G])
    p = np.column_stack([Pc[:, g].sum(axis=1) for g in G])
    l = np.array([L[g].sum() for g in G])
    q = b * p / l
    q /= q.sum(axis=1, keepdims=True)
    wg = np.array([(w[g] * freq[g]).sum() / freq[g].sum() for g in G])
    return q @ wg


gids = sorted(pa["game_id"].unique())
rng = np.random.default_rng(SEED)
err = {v: np.zeros(len(pa)) for v in VERSIONS}
for r in range(REPEATS):
    half = pa["game_id"].map(dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))).to_numpy()
    for fold in (0, 1):
        build, test = pa[half != fold], np.flatnonzero(half == fold)
        cards = {}
        for s in ("B", "P"):
            X = pd.crosstab(build[s], build["line"]).reindex(index=ids[s], columns=L8, fill_value=0)
            steps, ks = SPEC[s]
            c7, hs = dice.build(X.to_numpy().astype(float), names[s],
                                shares[s].reindex(ids[s]).fillna(0.0).to_numpy(), steps, ks,
                                dice.SLUGGERS if s == "B" else ())
            # dice now prints a free pass plus a walk / HBP split; rebuild the 8 lines.
            # The 19 Sep result in the spec came from the 8-line module (commit d175b22).
            cards[s] = np.column_stack([c7[:, 0], c7[:, 1] * (1 - hs), c7[:, 1] * hs, c7[:, 2:]])
        L = build["line"].value_counts(normalize=True).reindex(L8, fill_value=0).to_numpy()
        Bc, Pc = cards["B"][pos["B"][test]], cards["P"][pos["P"][test]]
        v = w[y[test]]
        for name, merges in VERSIONS.items():
            err[name][test] += (v - predict(Bc, Pc, L, merges)) ** 2
    print(f"  split {r + 1}/{REPEATS}", flush=True)

g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
print("\nheld-out runs error, merged version minus 8 lines (x1e-6 per PA; positive = keeping them apart predicts better)")
for name in ("BB+HBP merged", "1B+ROE merged", "both merged"):
    d = (err[name] - err["8 lines"]) / REPEATS
    bt = (Wb @ np.bincount(g, weights=d, minlength=nG)) / (Wb @ cnt)
    print(f"  {name:15s} {1e6 * d.mean():+7.1f}  SE {1e6 * bt.std():5.1f}")
print("\nrun values:", dict(zip(L8, w.round(3))))
