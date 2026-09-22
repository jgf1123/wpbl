"""Who owns each line? The evidence that should set the bin sort order.

    pixi run python analysis/dice/line_owner.py

The layout sorts lines most-batter to most-pitcher, so the order needs an
argument, not a guess. Three independent measurements bear on it, all on a
common denominator (per plate appearance, so batters and pitchers compare):

  real share of spread   how much of the spread between players in that line
                         survives after sampling noise is removed. A line with
                         real batter spread and no real pitcher spread belongs
                         on the batter's card.
  k                      how hard the line has to be smoothed toward the cohort
                         to predict held-out games. Large k means little of the
                         player's own record is worth keeping.
  fitted mixing weight   from mixture_eight.py, the weight that predicts best
                         when the line is read off the pitcher's card.

They should agree. Where they do not, the sort order is resting on one of them
and it is worth knowing which.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import LINES, plate_appearances

pd.set_option("display.width", 240)
ALPHA = {"K": 0.30, "BB": 0.70, "HBP": 0.20, "HR": 0.15,
         "1B": 0.30, "2B": None, "ROE": 0.85, "OUT": 0.35}
pa = plate_appearances()
rng = np.random.default_rng(20260921)
rows = []
for line in LINES:
    rec = {"line": line, "league %": round(100 * (pa["line"] == line).mean(), 1),
           "fitted a": ALPHA[line]}
    for side, tag, floor_n in (("B", "batter", 25), ("P", "pitcher", 25)):
        X = pd.crosstab(pa[side], pa["line"]).reindex(columns=LINES, fill_value=0)
        n = X.sum(axis=1).to_numpy().astype(float)
        x = X[line].to_numpy().astype(float)
        keep = n >= floor_n
        r, nn = x[keep] / n[keep], n[keep]
        lg = x[keep].sum() / nn.sum()
        obs = float(((r - lg) ** 2).mean())
        noise = float((lg * (1 - lg) / nn).mean())
        real = max(obs - noise, 0.0)
        boots = []
        for _ in range(2000):
            i = rng.integers(0, len(nn), len(nn))
            boots.append(float(((r[i] - lg) ** 2).mean())
                         - float(np.mean(lg * (1 - lg) / nn[i])))
        lo = max(np.percentile(boots, 5), 0.0)
        rec[f"{tag} real SD"] = round(100 * np.sqrt(real), 2)
        rec[f"{tag} real %"] = f"{real / obs:.0%}" if obs else "-"
        rec[f"{tag} 90% low"] = round(100 * np.sqrt(lo), 2)
        # method-of-moments k: how many phantom PAs the real spread justifies
        rec[f"{tag} k"] = round(lg * (1 - lg) / real) if real > 0 else "inf"
    rows.append(rec)
t = pd.DataFrame(rows)
print(f"{len(pa)} plate appearances; spread measured per PA on both sides "
      f"so the two are comparable\n")
print(t.to_string(index=False))

print("\n=== who owns the line, by each measure ===")
for _, r in t.iterrows():
    if r["line"] == "2B":
        verdict = "neither (fixed band)"
    else:
        b, p = r["batter real SD"], r["pitcher real SD"]
        verdict = ("batter" if b > 2 * p else "pitcher" if p > 2 * b else "both")
    a = r["fitted a"]
    by_a = "-" if a is None else ("batter" if a < 0.35 else "pitcher" if a > 0.55 else "both")
    flag = "" if verdict == by_a or "-" in (verdict, by_a) else "   <-- DISAGREE"
    print(f"  {r['line']:4s} spread says {verdict:20s} mixing weight says {by_a:8s}{flag}")
