"""Held-out runs score: protect vs same, each at its own best k; plus per-line best-k cards for reference."""
import numpy as np
import pandas as pd
SRC = open(__file__.replace("tree_compare.py", "tree_cv.py"), encoding="utf-8").read()
SRC = SRC.replace("__file__.replace(\"tree_cv.py\", \"k_cv2.py\")", repr(__file__.replace("tree_compare.py", "k_cv2.py")))
exec(SRC[:SRC.index("# ---------------- held-out scoring")])
BEST = {"protect": [32, 64, 16], "same": [64, 64, 4]}
gids = sorted(pa["game_id"].unique())
rng = np.random.default_rng(SEED)
S = {v: np.zeros(len(pa)) for v in BEST}
for r in range(REPEATS):
    half = pa["game_id"].map(dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))).to_numpy()
    for fold in (0, 1):
        build, test = pa[half != fold], np.flatnonzero(half == fold)
        X = counts(build, "B")
        pos = pd.Series(np.arange(len(people["B"])), index=people["B"])[pa.loc[test, "B"]].to_numpy()
        for v, ks in BEST.items():
            C, T = targets("B", X, v)
            S[v][test] += (w[y[test]] - (card(C, T, ks) @ w)[pos]) ** 2
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)
d = (S["same"] - S["protect"]) / REPEATS
G = np.bincount(g, weights=d, minlength=nG)
boot = (Wb @ G) / (Wb @ cnt)
print(f"held-out runs error, same minus protect: {1e6 * d.mean():+.0f} x1e-6 per PA, SE {1e6 * boot.std():.0f}"
      f"  (positive = protecting the sluggers predicts better)")
