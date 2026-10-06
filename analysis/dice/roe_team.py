"""Should the ROE band depend on the fielding team?

    pixi run python analysis/dice/roe_team.py

ROE is a flat league band (2 of 94 cells) because neither the batter's nor the
pitcher's record shows real spread (line_owner.py). The owner that was never
tested is the defence. Four measurements, all by fielding team:

  ROE per PA         the quantity the band stands for
  ROE per fielded    ROE / (balls in play that are not home runs), so a
                     strikeout staff cannot make its defence look clean
  DER                share of fielded balls turned into outs (context)
  held-out           leave-one-game-out log loss: team rate shrunk toward the
                     league vs the flat rate, SE from resampling whole games

plus a split-half check: does a team's ROE rate in its odd-numbered games
predict the rate in its even-numbered ones?
"""
import numpy as np
import pandas as pd
from scipy.stats import chi2

from wpbl.dice import plate_appearances

pd.set_option("display.width", 200)
pa = plate_appearances()
pa["roe"] = pa["line"] == "ROE"
pa["fielded"] = ~pa["line"].isin(["K", "BB", "HBP", "HR"])
pa["out"] = pa["line"] == "OUT"
T = "P_team"


def spread(x, n):
    """chi-square for 'all groups share one rate', and method-of-moments real SD."""
    lg = x.sum() / n.sum()
    x2 = float(((x - n * lg) ** 2 / (n * lg * (1 - lg))).sum())
    df = len(n) - 1
    real = float(((x / n - lg) ** 2).mean() - (lg * (1 - lg) / n).mean())
    return lg, x2, df, 1 - chi2.cdf(x2, df), np.sqrt(max(real, 0.0))


g = pa.groupby(T).agg(PA=("roe", "size"), ROE=("roe", "sum"),
                      fielded=("fielded", "sum"), outs=("out", "sum"))
g["ROE/PA %"] = 100 * g.ROE / g.PA
g["ROE/fielded %"] = 100 * g.ROE / g.fielded
g["DER"] = g.outs / g.fielded
print(f"{len(pa)} PAs, {pa.game_id.nunique()} games, {int(pa.roe.sum())} ROE\n")
print(g.round(3).to_string(), "\n")

for name, x, n in (("ROE per PA", g.ROE, g.PA),
                   ("ROE per fielded ball", g.ROE, g.fielded),
                   ("DER (outs per fielded ball)", g.outs, g.fielded)):
    lg, x2, df, p, sd = spread(x.to_numpy(float), n.to_numpy(float))
    print(f"{name:30s} league {lg:.4f}  chi2 {x2:5.2f} on {df} df, p={p:.2f}  "
          f"real SD {sd:.4f}")

# split-half: odd vs even games within each team
pa["gnum"] = pa.groupby(T)["game_id"].transform(lambda s: s.rank(method="dense"))
half = pa.assign(h=pa.gnum % 2).groupby([T, "h"]).agg(ROE=("roe", "sum"), PA=("roe", "size"))
half["rate %"] = 100 * half.ROE / half.PA
print("\nsplit-half ROE/PA % (odd games | even games)")
print(half["rate %"].unstack().round(2).to_string())

# held-out: leave one game out, team rate shrunk with k phantom PAs at the league rate
games = pa.game_id.unique()
def held_out(k):
    """per-PA log loss contribution (x1000) for each game, team rate shrunk by k."""
    out = {}
    for gid in games:
        tr, te = pa[pa.game_id != gid], pa[pa.game_id == gid]
        lg = tr.roe.mean()
        if k is None:
            p = np.full(len(te), lg)
        else:
            t = tr.groupby(T).roe.agg(["sum", "size"])
            rate = (t["sum"] + k * lg) / (t["size"] + k)
            p = te[T].map(rate).fillna(lg).to_numpy()
        y = te.roe.to_numpy()
        out[gid] = -(y * np.log(p) + (1 - y) * np.log(1 - p)).sum()
    return pd.Series(out)

flat = held_out(None)
rng = np.random.default_rng(20261003)
print("\nheld-out log loss vs flat, x1000 per PA (negative = team rate better)")
for k in (100, 250, 500, 1000, 2000):
    d = held_out(k) - flat
    boots = [d.sample(len(d), replace=True, random_state=int(s)).sum() / len(pa)
             for s in rng.integers(0, 2**31, 2000)]
    print(f"  k={k:5d}  {1000 * d.sum() / len(pa):+.3f}  SE {1000 * np.std(boots):.3f}")
