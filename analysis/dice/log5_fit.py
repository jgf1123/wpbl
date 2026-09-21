"""Does log5 actually describe each of the seven lines?

    pixi run python analysis/dice/log5_fit.py

Not "how close is the additive shortcut to log5" (that is additive_vs_log5.py)
but whether log5 is the right rule at all, line by line, judged on games the
cards were not built from.

Cards are built from half the games, 20 random splits; every plate appearance in
the other half is then predicted by five rules and scored by log loss on that
one line treated as a binary:

    league      the league rate, ignoring both players
    batter      her card alone
    pitcher     his card alone
    additive    B + P - L, floored
    log5        B*P/L, renormalised over the seven lines

A line where log5 beats "batter" and "pitcher" is one where both sides matter
and the multiplicative form earns its keep. A line where "batter" alone wins is
one where the pitcher contributes nothing to predict, whatever the theory says.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, build, plate_appearances, usage)

pd.set_option("display.width", 230)
SPLITS, SEED, EPS = 20, 20260920, 1e-6
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares = usage(pa)
gids = sorted(pa["game_id"].unique())
line_i = {l: i for i, l in enumerate(CARD_LINES)}
y = pa["line"].map(lambda l: line_i["FP"] if l in ("BB", "HBP") else line_i[l]).to_numpy()
rng = np.random.default_rng(SEED)

RULES = ["league", "batter", "pitcher", "additive", "log5"]
loss = {r: np.zeros(len(CARD_LINES)) for r in RULES}
count = np.zeros(len(CARD_LINES))
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
per_game = {r: np.zeros((nG, len(CARD_LINES))) for r in RULES}   # for a bootstrap over games
game_n = np.zeros((nG, len(CARD_LINES)))

for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        built = {}
        for side, steps, ks, slug in (("B", BATTER_STEPS, BATTER_K, SLUGGERS),
                                      ("P", PITCHER_STEPS, PITCHER_K, ())):
            X = pd.crosstab(tr[side], tr["line"]).reindex(columns=LINES, fill_value=0)
            ids = X.index.to_numpy()
            names = [players["person_name"].get(i, i) for i in ids]
            c, _ = build(X.to_numpy().astype(float), names,
                         shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug)
            built[side] = pd.DataFrame(c, index=ids, columns=CARD_LINES)
        Lh = tr["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
        lvec = np.array([Lh["BB"] + Lh["HBP"] if l == "FP" else Lh[l] for l in CARD_LINES])

        # only PAs whose batter and pitcher both appear in the build half
        ok = [i for i in te if pa["B"].iloc[i] in built["B"].index
              and pa["P"].iloc[i] in built["P"].index]
        if not ok:
            continue
        Bm = built["B"].loc[pa["B"].iloc[ok]].to_numpy()
        Pm = built["P"].loc[pa["P"].iloc[ok]].to_numpy()
        yy = y[ok]
        preds = {"league": np.tile(lvec, (len(ok), 1)), "batter": Bm, "pitcher": Pm}
        a = Bm + Pm - lvec
        preds["additive"] = np.clip(a, EPS, 1)
        q = Bm * Pm / lvec
        preds["log5"] = q / q.sum(axis=1, keepdims=True)
        for j in range(len(CARD_LINES)):
            hit = (yy == j).astype(float)
            count[j] += len(yy)
            np.add.at(game_n[:, j], gcode[ok], 1.0)
            for r in RULES:
                p = np.clip(preds[r][:, j], EPS, 1 - EPS)
                ll = -(hit * np.log(p) + (1 - hit) * np.log(1 - p))
                loss[r][j] += ll.sum()
                np.add.at(per_game[r][:, j], gcode[ok], ll)

tab = pd.DataFrame({r: loss[r] / count for r in RULES}, index=CARD_LINES)
print(f"held-out log loss per plate appearance, {SPLITS} splits x 2 folds\n")
show = (1000 * tab).round(2)
show["best"] = tab.idxmin(axis=1)
show["log5 vs league"] = (1000 * (tab["league"] - tab["log5"])).round(2)
show["log5 vs batter"] = (1000 * (tab["batter"] - tab["log5"])).round(2)
show["log5 vs pitcher"] = (1000 * (tab["pitcher"] - tab["log5"])).round(2)
print(show.to_string())
print("\n(x1000; lower loss is better, so a positive difference means log5 wins)")

print("\n=== is the difference bigger than noise? bootstrap over games ===")
rb = np.random.default_rng(SEED + 1)
draws = rb.integers(0, nG, size=(2000, nG))
rows = []
for j, line in enumerate(CARD_LINES):
    row = {"line": line}
    for other in ("league", "batter", "pitcher"):
        d = per_game[other][:, j] - per_game["log5"][:, j]
        n = game_n[:, j]
        point = 1000 * d.sum() / n.sum()
        bs = 1000 * d[draws].sum(axis=1) / n[draws].sum(axis=1)
        row[f"log5 vs {other}"] = f"{point:+.2f} (SE {bs.std():.2f})"
    rows.append(row)
print(pd.DataFrame(rows).to_string(index=False))
print("positive = log5 predicts better; SE from resampling the 37 games")
