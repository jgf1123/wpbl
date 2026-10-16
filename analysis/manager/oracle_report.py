"""Read oracle.py's half-innings: when the aces pitch, how load spreads, and whether
starter and reliever shapes emerge. Oracle against B0-like on the same samples.

    pixi run python analysis/manager/oracle_report.py oracle.csv

rank is the arm's place on her team by fresh runs per inning (0 = the best).
Stakes bands are the run-value index at the start of the half-inning.
"""
import sys

import numpy as np
import pandas as pd

BANDS = [0, 0.3, 0.7, 1.2, 2.0, 99]
LABELS = ["<0.3", "0.3-0.7", "0.7-1.2", "1.2-2.0", "2.0+"]

df = pd.read_csv(sys.argv[1])
df["band"] = pd.cut(df["stakes"], BANDS, labels=LABELS, right=False)
pd.set_option("display.width", 200)

print("1. Who pitches the inning, by its stakes: share of half-innings pitched by the")
print("   team's best arm (rank 0), second (rank 1), and ranks 2-3, oracle against B0-like")
for who in ("oracle", "B0-like"):
    d = df[df["who"] == who]
    tab = pd.DataFrame({f"rank {r}": d.groupby("band", observed=False)["rank"].apply(
        lambda s, r=r: (s == r).mean() if r < 2 else s.isin([2, 3]).mean()) for r in (0, 1, 2)})
    tab = tab.rename(columns={"rank 2": "ranks 2-3"})
    tab["half-innings"] = d.groupby("band", observed=False).size()
    print(f"\n  {who}:\n" + tab.to_string(float_format=lambda x: f"{x:.2f}"))

print("\n2. Load by rank, per sampled postseason (8 dates)")
for who in ("oracle", "B0-like"):
    d = df[df["who"] == who]
    st = d.drop_duplicates(["team", "sample", "game", "arm", "stint_first"])
    n = d.groupby(["team", "sample"]).ngroups
    tab = pd.DataFrame({
        "stints": st.groupby("rank").size() / n,
        "innings": d.groupby("rank").size() / n,
        "innings per stint": st.groupby("rank")["stint_innings"].mean(),
        "pitches per warm-up": st.groupby("rank")["stint_pitches"].mean(),
        "mean stakes": d.groupby("rank")["stakes"].mean(),
        "entering count": st.groupby("rank")["entering"].mean(),
    })
    print(f"\n  {who}:\n" + tab.head(9).to_string(float_format=lambda x: f"{x:.2f}"))

print("\n3. Shapes: by inning, the pitcher's rank and stamina, and her stint's length")
for who in ("oracle", "B0-like"):
    d = df[df["who"] == who]
    st = d.drop_duplicates(["team", "sample", "game", "arm", "stint_first"])
    tab = pd.DataFrame({
        "mean rank": d.groupby("inning")["rank"].mean(),
        "mean stamina": d.groupby("inning")["stamina"].mean(),
        "mean stakes": d.groupby("inning")["stakes"].mean(),
        "stints starting here": st.groupby("stint_first").size() / st.groupby(["team", "sample", "game"]).ngroups,
        "their innings": st.groupby("stint_first")["stint_innings"].mean(),
    })
    print(f"\n  {who}:\n" + tab.to_string(float_format=lambda x: f"{x:.2f}"))

print("\n4. Per team, oracle: each arm's share of the high-stakes half-innings (1.2+)")
d = df[(df["who"] == "oracle")]
for team, g in d.groupby("team"):
    hi = g[g["stakes"] >= 1.2]
    share = hi.groupby("arm").size() / len(hi)
    allin = g.groupby("arm").size() / g.groupby(["sample"]).ngroups
    rate = g.groupby("arm")["fresh_rate"].first()
    t = pd.DataFrame({"fresh runs/inn": rate, "share of 1.2+ innings": share,
                      "innings per postseason": allin}).fillna(0).sort_values("fresh runs/inn")
    print(f"\n  {team}:\n" + t.to_string(float_format=lambda x: f"{x:.2f}"))
