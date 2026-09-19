"""Cards on full data with each line's best-scoring k vs the tie-rule k."""
import numpy as np
import pandas as pd
SRC = open(__file__.replace("k_best.py", "k_cv.py"), encoding="utf-8").read()
exec(SRC[:SRC.index("# scores[side][line]")])
BEST = {"B": {"K": 0, "BB": 100, "HBP": 25, "HR": 50, "1B": 100, "2B": 100, "ROE": 100},
        "P": {"K": 0, "BB": 200, "HBP": 200, "HR": 1000, "1B": 200, "2B": 200, "ROE": 50}}
TIE = {"B": {"K": 0, "BB": 10, "HBP": 5, "HR": 0, "1B": 25, "2B": 25, "ROE": 5},
       "P": {"K": 0, "BB": 25, "HBP": 0, "HR": 10, "1B": 50, "2B": 10, "ROE": 0}}
L = pa["line"].value_counts(normalize=True).reindex(ALL, fill_value=0)
for side, who in (("B", ["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay", "Lexi Hastings"]),
                  ("P", ["Jaida Lee", "Kelsie Whitmore", "Brittany Apgar", "Adelaide Frank", "Jua Park"])):
    x, n, T = targets(pa, side, L)
    raw = x.div(np.where(n > 0, n, 1), axis=0)
    res = {}
    for label, ks in (("best k", BEST), ("tie-rule k", TIE)):
        c = pd.DataFrame({l: card_line(x[l].to_numpy().astype(float), n, T[l].to_numpy(), ks[side][l]) for l in LINES}, index=people[side])
        c["OUT"] = 1 - c.sum(axis=1)
        res[label] = c
    val = pd.DataFrame({"PA": n, "raw": raw[ALL].to_numpy() @ w, **{k: v[ALL].to_numpy() @ w for k, v in res.items()}}, index=people[side])
    val.index = [name.get(i, i) for i in val.index]
    q = val["PA"] >= (25 if side == "B" else 40)
    print(f"\n=== {'batters' if side == 'B' else 'pitchers'}: runs per PA x1000 (pitchers: allowed) ===")
    print((val.loc[who] * [1, 1000, 1000, 1000]).round(0).to_string())
    print("spread (SD) among regulars:", {c: round(1000 * val.loc[q, c].std()) for c in ["raw", "best k", "tie-rule k"]})
    for nm in who[-3:] if side == "P" else ["Ashton Lansdell"]:
        pid = [i for i in people[side] if name.get(i) == nm][0]
        print(f"  {nm} ({int(n[list(people[side]).index(pid)])} {'PA' if side == 'B' else 'BF'}) %:",
              pd.DataFrame({"raw": 100 * raw.loc[pid, LINES], "best k": 100 * res["best k"].loc[pid, LINES],
                            "tie-rule k": 100 * res["tie-rule k"].loc[pid, LINES]}).round(1).T.to_string().replace("\n", "\n      "))
