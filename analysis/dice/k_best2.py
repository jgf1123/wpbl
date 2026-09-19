"""Cards on full data with each line's best-scoring k vs the tie-rule k."""
import numpy as np
import pandas as pd
SRC = open(__file__.replace("k_best2.py", "k_cv2.py"), encoding="utf-8").read()
exec(SRC[:SRC.index("# scores[side][line]")])
BEST = {"B": {"K": 1, "BB": 128, "HBP": 32, "HR": 32, "1B": 128, "2B": 128, "ROE": 128}, "P": {"K": 1, "BB": 128, "HBP": 128, "HR": 1024, "1B": 256, "2B": 256, "ROE": 64}}
TIE = {"B": {"K": 1, "BB": 32, "HBP": 8, "HR": 32, "1B": 64, "2B": 64, "ROE": 8}, "P": {"K": 1, "BB": 64, "HBP": 32, "HR": 64, "1B": 128, "2B": 32, "ROE": 1}}
L = pa["line"].value_counts(normalize=True).reindex(ALL, fill_value=0)
for side, who in (("B", ["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay", "Lexi Hastings"]),
                  ("P", ["Jaida Lee", "Kelsie Whitmore", "Brittany Apgar", "Adelaide Frank", "Jua Park"])):
    x, n, T = targets(pa, side, L)
    raw = x.div(np.where(n > 0, n, 1), axis=0)
    res = {}
    for label, ks in (("best k", BEST), ("low end 1 SE", TIE)):
        c = pd.DataFrame({l: card_line(x[l].to_numpy().astype(float), n, T[l].to_numpy(), ks[side][l]) for l in LINES}, index=people[side])
        c["OUT"] = 1 - c.sum(axis=1)
        res[label] = c
    val = pd.DataFrame({"PA": n, "raw": raw[ALL].to_numpy() @ w, **{k: v[ALL].to_numpy() @ w for k, v in res.items()}}, index=people[side])
    val.index = [name.get(i, i) for i in val.index]
    q = val["PA"] >= (25 if side == "B" else 40)
    print(f"\n=== {'batters' if side == 'B' else 'pitchers'}: runs per PA x1000 (pitchers: allowed) ===")
    print((val.loc[who] * [1, 1000, 1000, 1000]).round(0).to_string())
    print("spread (SD) among regulars:", {c: round(1000 * val.loc[q, c].std()) for c in ["raw", "best k", "low end 1 SE"]})
    for nm in who[-3:] if side == "P" else ["Ashton Lansdell"]:
        pid = [i for i in people[side] if name.get(i) == nm][0]
        print(f"  {nm} ({int(n[list(people[side]).index(pid)])} {'PA' if side == 'B' else 'BF'}) %:",
              pd.DataFrame({"raw": 100 * raw.loc[pid, LINES], "best k": 100 * res["best k"].loc[pid, LINES],
                            "low end 1 SE": 100 * res["low end 1 SE"].loc[pid, LINES]}).round(1).T.to_string().replace("\n", "\n      "))
