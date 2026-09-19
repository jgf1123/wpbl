"""How was k chosen, how uncertain is it, and what does it do to Lansdell?"""
import numpy as np
import pandas as pd

SRC = open(__file__.replace("k_uncertainty.py", "cohort_cards2.py"), encoding="utf-8").read()
SRC = SRC[:SRC.index("\nfor side, label in")]
SRC = SRC.replace("        cards[line] = pd.Series(card, index=ids)",
                  "        if special:\n"
                  "            ks = league_k(x, n, line, qual)\n"
                  "            card = np.where(slug, (xv + ks * t) / (nv + ks), card)\n"
                  "        cards[line] = pd.Series(card, index=ids)")
exec(SRC)
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE"]
rng = np.random.default_rng(20260918)


def tau2_of(r, nn, p):
    """Method of moments: observed variance of player rates minus expected sampling variance."""
    return float(np.var(r, ddof=1)) - float((p * (1 - p) / nn).mean())


def k_of(t2, p):
    return p * (1 - p) / t2 if t2 > 0 else np.inf


print("k = p(1-p) / real-spread-variance; card = (own count + k * target) / (own PA + k)")
print("own share of a card for a 75-PA batter (or 150-BF pitcher) = n / (n + k)\n")
for side, label, floor, n_ref in (("B", "batters", 25, 75), ("P", "pitchers", 40, 150)):
    x = pd.crosstab(pa[side], pa["line"])
    n = x.sum(axis=1)
    q = n >= floor
    rows = []
    for line in LINES:
        p = L[line]
        r = (x[line] / n)[q].to_numpy()
        nn = n[q].to_numpy()
        t2 = tau2_of(r, nn, p)
        boot = []
        for _ in range(2000):                          # resample players
            i = rng.integers(0, len(r), len(r))
            boot.append(tau2_of(r[i], nn[i], p))
        lo, hi = np.percentile(boot, [5, 95])
        k, k_small = k_of(t2, p), k_of(hi, p)
        rows.append({"line": line, "league %": round(100 * p, 1),
                     "real spread SD (pts)": round(100 * np.sqrt(max(t2, 0)), 2),
                     "90% range of SD": f"{100 * np.sqrt(max(lo, 0)):.2f}-{100 * np.sqrt(max(hi, 0)):.2f}",
                     "k (estimate)": round(k) if np.isfinite(k) else "inf",
                     "smallest plausible k": round(k_small) if np.isfinite(k_small) else "inf",
                     f"own share at {n_ref} (estimate)": f"{n_ref / (n_ref + k):.0%}" if np.isfinite(k) else "0%",
                     f"own share at {n_ref} (smallest k)": f"{n_ref / (n_ref + k_small):.0%}" if np.isfinite(k_small) else "0%"})
    print(f"=== {label} with {floor}+ PA ({int(q.sum())} of them), k measured around the league average ===")
    print(pd.DataFrame(rows).to_string(index=False) + "\n")

# Lansdell, line by line, under the current cohort cards
x, n, s, card, floored, rows_, info = build("B")
lid = pid_of["Ashton Lansdell"]
print("=== Ashton Lansdell (78 PA) under the current cohort cards ===")
out = []
for line in LINES:
    raw = x.loc[lid, line] / n[lid]
    if line in card.columns:
        k = info[line]["k"]
        kk = np.inf if k == "inf" else float(k)
        if line == "HR":                                 # rest-of-league HR constant applies to her
            kk = float(info["HR"]["k"])
        own = n[lid] / (n[lid] + kk) if np.isfinite(kk) else 0.0
        tgt = rows_[line].loc[lid, "target"]
        out.append({"line": line, "raw %": round(100 * raw, 1), "target %": round(100 * tgt, 1),
                    "card %": round(100 * card.loc[lid, line], 1), "k": k, "her own share": f"{own:.0%}"})
    else:
        out.append({"line": line, "raw %": round(100 * raw, 1), "target %": "league",
                    "card %": round(100 * L[line], 1), "k": "inf (not on card)", "her own share": "0%"})
print(pd.DataFrame(out).to_string(index=False))
