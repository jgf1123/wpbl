"""1. Benites/Whitmore HR by pitcher tier (leave-out quality).  2-3. context-neutral/PA raw vs card."""
import numpy as np
import pandas as pd
from math import comb


def hyper_sf(k, N, K, n):
    """P(X >= k) for X ~ hypergeometric: n draws from N items, K of them marked."""
    return sum(comb(K, i) * comb(N - K, n - i) for i in range(k, min(K, n) + 1)) / comb(N, n)
from wpbl.batters import neutral_values, plate_appearances
from wpbl.markov import run_expectancy, re_of

SRC = open(__file__.replace("hr_quality.py", "cohort_cards2.py"), encoding="utf-8").read()
SRC = SRC[:SRC.index("\nfor side, label in")]
# decision 1: the sluggers take the all-batter HR constant, not the rest-of-league one
SRC = SRC.replace("        cards[line] = pd.Series(card, index=ids)",
                  "        if special:\n"
                  "            ks = league_k(x, n, line, qual)\n"
                  "            card = np.where(slug, (xv + ks * t) / (nv + ks), card)\n"
                  "        cards[line] = pd.Series(card, index=ids)")
exec(SRC)
SLUG_IDS = {pid_of[s] for s in SLUGGERS}

# ---------------- per-PA RE24 with pitcher and batter ----------------
re_table = run_expectancy()
live = plays[plays["outs_before"] < 3].sort_values(["game_id", "sequence"]).copy()
live["bases"] = (live["first_base"].notna().map({True: "1", False: "_"}) + live["second_base"].notna().map({True: "2", False: "_"})
                 + live["third_base"].notna().map({True: "3", False: "_"}))
rv = {}
for _, half in live.groupby(["game_id", "inning", "half"], sort=False):
    rec = list(half.itertuples())
    for i, p in enumerate(rec):
        nxt = rec[i + 1] if i + 1 < len(rec) else None
        after = re_of(re_table, nxt.bases, int(nxt.outs_before)) if nxt is not None else 0.0
        rv[p.Index] = after + p.runs_scored - re_of(re_table, p.bases, int(p.outs_before))
pa["re24"] = pa.index.map(rv)

frame = plate_appearances("training")
_, wts = neutral_values(frame, "drop", "pool")
fip_w = {"HR": wts["home_run"], "BB": wts["free_pass"], "HBP": wts["free_pass"], "K": wts["strikeout"]}
pa["fip"] = pa["line"].map(fip_w).fillna(0.0)

# pitcher quality WITHOUT her PAs against the sluggers (higher = worse pitcher)
other = pa[~pa["B"].isin(SLUG_IDS)]
q = pd.DataFrame({"usage": -share["P"],                               # more use = better, so negate
                  "RE24/BF": other.groupby("P")["re24"].mean(),
                  "FIP/BF": other.groupby("P")["fip"].mean(),
                  "BF": other.groupby("P").size()})
print(f"{len(q)} pitchers; quality measured on {len(other)} PAs that exclude Benites and Whitmore")

slug_pa = pa[pa["B"].isin(SLUG_IDS)]
print(f"sluggers: {len(slug_pa)} PAs, {int((slug_pa['line'] == 'HR').sum())} HR, against {slug_pa['P'].nunique()} pitchers")
for measure in ("usage", "RE24/BF", "FIP/BF"):
    s = q.dropna(subset=[measure]).sort_values(measure)                 # best pitcher first
    cum = s["BF"].cumsum() / s["BF"].sum()
    tier = pd.Series(np.select([cum <= 1 / 3, cum <= 2 / 3], ["best third", "middle third"], "worst third"), index=s.index)
    rows = []
    for tname in ("best third", "middle third", "worst third"):
        ids = set(tier[tier == tname].index)
        sp, op = slug_pa[slug_pa["P"].isin(ids)], other[other["P"].isin(ids)]
        rows.append({"tier": tname, "pitchers": len(ids), "slugger PA": len(sp), "slugger HR": int((sp["line"] == "HR").sum()),
                     "slugger HR %": round(100 * (sp["line"] == "HR").mean(), 1),
                     "rest-of-league HR %": round(100 * (op["line"] == "HR").mean(), 2)})
    t = pd.DataFrame(rows)
    N, K = len(slug_pa), int((slug_pa["line"] == "HR").sum())
    n_worst, k_worst = int(t.iloc[2]["slugger PA"]), int(t.iloc[2]["slugger HR"])
    p = hyper_sf(k_worst, N, K, n_worst)
    print(f"\n=== pitcher tiers by {measure} (each third faced 1/3 of league BF) ===")
    print(t.to_string(index=False))
    print(f"  expected HR in worst third if the pitcher didn't matter: {K * n_worst / N:.1f}; observed {k_worst}; "
          f"chance of {k_worst}+ by luck: {p:.2f}")

# ---------------- context-neutral/PA: raw vs card ----------------
LINES8 = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
lw = frame.assign(line=frame["outcome"].map(TO_LINE).fillna("OUT"))
w = lw.groupby("line")["run_value"].mean()
w["BB"] = w["HBP"] = lw.loc[lw["line"].isin(["BB", "HBP"]), "run_value"].mean()     # pooled free pass
w = w.reindex(LINES8)
x, n, s, card, floored, rows_, info = build("B")
raw = x.reindex(columns=LINES8, fill_value=0).div(n, axis=0)
hr_only = raw.copy()
hr_only["OUT"] += raw["HR"] - card["HR"]
hr_only["HR"] = card["HR"]
full = pd.DataFrame({l: L[l] for l in LINES8}, index=raw.index)
for l in card.columns:
    full[l] = card[l]
full["OUT"] = 1 - full.drop(columns="OUT").sum(axis=1)
out = pd.DataFrame({"PA": n, "HR": x["HR"], "raw": raw @ w, "HR swapped only": hr_only @ w, "full card": full @ w})
out.index = [name.get(i, i) for i in out.index]
cols = ["raw", "HR swapped only", "full card"]
print("\n=== context-neutral runs per PA x1000 (line weights, free passes pooled) ===")
show = out.copy(); show[cols] = (1000 * show[cols]).round(0)
print(show.loc[["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"]].to_string())
print("\ntop 10 by raw:")
print(show.sort_values("raw", ascending=False).head(10).to_string())
wgt = out["PA"] / out["PA"].sum()
print("\nwhole league, PA-weighted:")
for c in cols:
    print(f"  {c:16s} mean {1000 * (out[c] * wgt).sum():6.1f}   SD across batters (25+ PA) {1000 * out.loc[out['PA'] >= 25, c].std():5.1f}")
print(f"  HR: actual {int(out['HR'].sum())}, card {float((card['HR'] * n).sum()):.1f}")
q25 = out["PA"] >= 25
print(f"  rank correlation raw vs full card (25+ PA): {out.loc[q25, 'raw'].rank().corr(out.loc[q25, 'full card'].rank()):.2f}")
print(f"  rank correlation raw vs HR-swapped (25+ PA): {out.loc[q25, 'raw'].rank().corr(out.loc[q25, 'HR swapped only'].rank()):.2f}")
d = show[q25].assign(**{"card - raw": show["full card"] - show["raw"], "HR part": show["HR swapped only"] - show["raw"]})
d["other lines part"] = d["card - raw"] - d["HR part"]
print("\nbatters with 25+ PA: biggest falls from raw to card (mruns/PA)")
print(d.sort_values("card - raw").head(8)[["PA", "HR", "raw", "full card", "card - raw", "HR part", "other lines part"]].to_string())
print("\nbiggest rises:")
print(d.sort_values("card - raw").tail(5)[["PA", "HR", "raw", "full card", "card - raw", "HR part", "other lines part"]].to_string())
print(f"\nacross all 25+ PA batters, mean |card - raw| {d['card - raw'].abs().mean():.0f}; "
      f"of which HR part {d['HR part'].abs().mean():.0f}, other lines {d['other lines part'].abs().mean():.0f}")
