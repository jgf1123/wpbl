"""Read one card or the other: does a mixture work as a combination rule?

    pixi run python analysis/dice/mixture.py

The mechanic: the d100 decides whose card to read. Roll under 100a and read the
pitcher's line, otherwise the batter's. That is

    p = a * P + (1 - a) * B

which sums to 100% because exactly one card is read, needs no arithmetic at the
table, and gives every line its trade-off for free -- each card is already a
distribution, so a batter with more singles has less of something else.

The risk is compression. A mixture can never be more extreme than either card,
while a real matchup of two extremes compounds. Pitchers vary little, so mixing
in 40% of a near-league pitcher card dilutes the batter by 40% toward average --
undoing some of the smoothing work the cards exist to do.

Two versions are scored:
  plain        print the cards as they are and mix
  compensated  print B' = (B - aP) / (1 - a), so the mixture reproduces the
               batter's true card exactly -- if B' is printable at all
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_K, BATTER_STEPS, CARD_LINES, LINES, PITCHER_K,
                       PITCHER_STEPS, SLUGGERS, build, plate_appearances, usage)

pd.set_option("display.width", 230)
SPLITS, SEED, FLOOR = 20, 20260920, 0.002
ALPHAS = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
shares = usage(pa)
gids = sorted(pa["game_id"].unique())
IX = {l: i for i, l in enumerate(CARD_LINES)}
y = pa["line"].map(lambda l: IX["FP"] if l in ("BB", "HBP") else IX[l]).to_numpy()
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1
rng = np.random.default_rng(SEED)

NAMES = ([f"mix a={a:.1f}" for a in ALPHAS]
         + [f"league-mix a={a:.1f}" for a in ALPHAS if a]
         + ["log5"])
ll = {r: np.zeros(nG) for r in NAMES}
seen = np.zeros(nG)

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
        ok = [i for i in te if pa["B"].iloc[i] in built["B"].index
              and pa["P"].iloc[i] in built["P"].index]
        if not ok:
            continue
        Bm = built["B"].loc[pa["B"].iloc[ok]].to_numpy()
        Pm = built["P"].loc[pa["P"].iloc[ok]].to_numpy()
        yy, gg = y[ok], gcode[ok]
        np.add.at(seen, gg, 1.0)
        preds = {f"mix a={a:.1f}": a * Pm + (1 - a) * Bm for a in ALPHAS}
        # the control: mix in the LEAGUE instead of this pitcher. Same shrinkage,
        # no matchup information. If it scores the same, the pitcher adds nothing.
        preds.update({f"league-mix a={a:.1f}": a * lvec + (1 - a) * Bm
                      for a in ALPHAS if a})
        q = Bm * Pm / lvec
        preds["log5"] = q / q.sum(axis=1, keepdims=True)
        for r, p in preds.items():
            z = np.clip(p, FLOOR, None)
            z = z / z.sum(axis=1, keepdims=True)
            np.add.at(ll[r], gg, -np.log(z[np.arange(len(yy)), yy]))

draws = np.random.default_rng(SEED + 2).integers(0, nG, size=(2000, nG))
base = ll["mix a=0.0"]
rows = []
for r in NAMES:
    d = ll[r] - base
    bs = 1000 * d[draws].sum(axis=1) / seen[draws].sum(axis=1)
    rows.append({"rule": r, "log loss x1000": round(1000 * ll[r].sum() / seen.sum(), 2),
                 "vs batter alone": f"{1000 * d.sum() / seen.sum():+.2f} (SE {bs.std():.2f})"})
print(f"held-out, {SPLITS} splits x 2 folds. a=0.0 is the batter's card alone.\n")
print(pd.DataFrame(rows).to_string(index=False))

# ---- how much does mixing compress the spread between batters? ----
from wpbl.dice import cards                                            # noqa: E402
B, _ = cards("B")
P, _ = cards("P")
n = pa.groupby("B").size().reindex(B.index).fillna(0)
reg = (n >= 25).to_numpy()
print("\n=== compression: SD across batters of the resulting line, "
      "averaged over pitchers ===")
rows = []
for a in ALPHAS:
    mix = a * P.to_numpy().mean(axis=0) + (1 - a) * B.to_numpy()[reg]
    rows.append({"a": a, **{l: round(100 * mix[:, IX[l]].std(ddof=1), 2)
                            for l in ("K", "FP", "HR", "1B", "OUT")}})
print(pd.DataFrame(rows).to_string(index=False))

# ---- can a compensated card be printed? ----
print("\n=== compensated cards: B' = (B - aP) / (1 - a) ===")
rows = []
for a in ALPHAS[1:]:
    bad, worst = 0, 0.0
    for b in B.to_numpy():
        for p in P.to_numpy():
            comp = (b - a * p) / (1 - a)
            bad += int((comp < 0).any())
            worst = min(worst, comp.min())
    tot = len(B) * len(P)
    rows.append({"a": a, "matchups needing a negative cell": f"{bad}/{tot}",
                 "most negative": round(100 * worst, 1)})
print(pd.DataFrame(rows).to_string(index=False))
