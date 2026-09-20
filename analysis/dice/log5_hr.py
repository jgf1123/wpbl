"""How much can a pitcher move a batter's home-run chance, now that HR is on both cards?

    pixi run python analysis/dice/log5_hr.py

A: is the tier difference in home runs allowed (rest of the league, best vs worst
   third of pitchers) bigger than sampling noise?
B: flat log5, p proportional to B*P/L, over every pitcher card: the range of a
   given batter's home-run chance across opponents.
Cards come from data/dice (pixi run dice); note the game count printed below.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import CARD_LINES, LINES, plate_appearances

pd.set_option("display.width", 220)
pa = plate_appearances()
print(f"{pa['game_id'].nunique()} training games, {len(pa)} plate appearances")
B = pd.read_csv("data/dice/cards_batters.csv")
P = pd.read_csv("data/dice/cards_pitchers.csv")
print(f"cards: {len(B)} batters, {len(P)} pitchers (data/dice, from whenever `pixi run dice` last ran)")

# ---------------- A. is the tier gap real? ----------------
print("\n=== A. home runs allowed by pitcher tier, everyone except the two sluggers ===")
SLUG = ("Denae Benites", "Kelsie Whitmore")
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
pa = pa.assign(bname=pa["B"].map(nm), pname=pa["P"].map(nm))
rest = pa[~pa["bname"].isin(SLUG)]
bf = rest.groupby("pname").size().sort_values()
# rank pitchers by usage (share of batters faced), as hr_quality.py does
order = P.set_index("player")["BF"].reindex(bf.index).fillna(0).sort_values(ascending=False)
cum = order.cumsum() / order.sum()
tier = pd.Series(np.select([cum <= 1 / 3, cum <= 2 / 3], ["best", "middle"], "worst"), index=order.index)
rest = rest.assign(tier=rest["pname"].map(tier))
t = rest.groupby("tier").agg(PA=("line", "size"), HR=("line", lambda s: (s == "HR").sum()))
t["HR%"] = (100 * t["HR"] / t["PA"]).round(2)
print(t.reindex(["best", "middle", "worst"]).to_string())
b_, w_ = t.loc["best"], t.loc["worst"]
p_pool = (b_["HR"] + w_["HR"]) / (b_["PA"] + w_["PA"])
se = np.sqrt(p_pool * (1 - p_pool) * (1 / b_["PA"] + 1 / w_["PA"]))
d = w_["HR"] / w_["PA"] - b_["HR"] / b_["PA"]
print(f"worst minus best third: {100 * d:+.2f} points, SE {100 * se:.2f}  ->  {d / se:.1f} SE")

# ---------------- B. what log5 does with the cards ----------------
print("\n=== B. flat log5 (p proportional to B*P/L): a batter's HR% against each pitcher ===")
L = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
lg = {l: (L["BB"] + L["HBP"] if l == "FP" else L[l]) for l in CARD_LINES}
lvec = np.array([lg[l] for l in CARD_LINES])
Bm = B[CARD_LINES].to_numpy() / 100
Pm = P[CARD_LINES].to_numpy() / 100
hr = CARD_LINES.index("HR")
rows = []
for who in ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell"):
    b = Bm[B["player"].tolist().index(who)]
    q = b * Pm / lvec
    q = q / q.sum(axis=1, keepdims=True)
    s = pd.Series(100 * q[:, hr], index=P["player"])
    bybf = s.reindex(P.sort_values("BF", ascending=False)["player"].head(15))
    rows.append({"batter": who, "card HR%": round(100 * b[hr], 1),
                 "vs easiest": round(s.max(), 1), "vs hardest": round(s.min(), 1),
                 "middle half": f"{s.quantile(.25):.1f}-{s.quantile(.75):.1f}",
                 "the 15 most-used pitchers": f"{bybf.min():.1f}-{bybf.max():.1f}"})
print(pd.DataFrame(rows).to_string(index=False))
pit_hr = pd.Series(100 * Pm[:, hr], index=P["player"])
print(f"\npitcher cards' own HR line: {pit_hr.min():.1f}% to {pit_hr.max():.1f}% "
      f"(SD {pit_hr.std():.2f}); the HR/1B/2B step uses k = infinity, so this spread comes "
      "only from\nhow much contact each pitcher allows, not from any home-run skill of her own.")
