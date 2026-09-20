"""Every non-card number the blog draft quotes, recomputed from the current data.

    pixi run python analysis/dice/post_facts.py

Card-derived numbers (run values, card lines) come from `post_numbers.py`; the
out-flavour numbers from `proposals.py` and `label_vs_line.py`. This covers the
rest: the season totals, the extreme cases, the sluggers, and the signatures.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import contact
from wpbl.dice import LINES, TO_LINE, plate_appearances

pd.set_option("display.width", 220)
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
games = tables.read("games", "training")
allg = tables.read("games", "all")
pa = pa.assign(bname=pa["B"].map(nm), pname=pa["P"].map(nm))

print("=== 1. the data we have ===")
print(f"training games {pa['game_id'].nunique()}, plate appearances {len(pa)}, "
      f"batters {pa['B'].nunique()}, pitchers {pa['P'].nunique()}")
kind = allg["game_kind"] if "game_kind" in allg.columns else None
if kind is not None:
    print("all games by kind:", allg["game_kind"].value_counts().to_dict())
    tr = allg[allg["game_id"].isin(pa["game_id"].unique())]
    print("training games by kind:", tr["game_kind"].value_counts().to_dict())
    print("excluded games:", allg[~allg["game_id"].isin(pa["game_id"].unique())]
          [["game_id", "game_kind"]].to_dict("records"))
bpa = pa.groupby("B").size()
ppa = pa.groupby("P").size()
print(f"batters with 50+ PA: median {int(bpa[bpa >= 50].median())}; "
      f"pitchers with 50+ BF: median {int(ppa[ppa >= 50].median())}")
L = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
print("in 75 PA at league rates: "
      f"HR {75 * L['HR']:.1f}, 2B {75 * L['2B']:.1f}, BB {75 * L['BB']:.1f}")

print("\n=== 3. the extreme cases ===")
p = pa.groupby("pname").agg(BF=("line", "size"), BB=("line", lambda s: (s == "BB").sum()),
                            HR=("line", lambda s: (s == "HR").sum())).sort_values("BF")
print(p.head(3).to_string())
b = pa.groupby("bname").agg(PA=("line", "size"), K=("line", lambda s: (s == "K").sum())).sort_values("PA")
print(b[b["PA"] <= 3].to_string())

print("\n=== 8. a class of two ===")
hr = pa[pa["line"] == "HR"].groupby("bname").size().sort_values(ascending=False)
print("home run leaders:", hr.head(5).to_dict())
SLUG = ["Denae Benites", "Kelsie Whitmore"]
bip = pa[pa["line"].isin(["1B", "2B", "ROE", "OUT"])].groupby("bname").size()
hrr = (hr.reindex(bip.index).fillna(0) / (bip + hr.reindex(bip.index).fillna(0)))
print("HR per ball in play + HR:  sluggers " +
      ", ".join(f"{s} {100 * hrr[s]:.0f}%" for s in SLUG))
starts = pa.groupby("bname").size()
reg = [x for x in starts[starts >= 60].index if x not in SLUG]
tot_hr = hr.reindex(reg).fillna(0).sum()
tot_bip = (bip.reindex(reg).fillna(0) + hr.reindex(reg).fillna(0)).sum()
print(f"  other batters with 60+ PA: {100 * tot_hr / tot_bip:.1f}%")

print("\n=== 10. signatures ===")
g = pa.groupby("bname")["game_id"].nunique()
print(f"batters in 17+ games: {int((g >= 17).sum())}")
tab = pd.crosstab(pa["bname"], pa["line"]).reindex(columns=LINES, fill_value=0)
n = tab.sum(axis=1)
rate = 100 * tab.div(n, axis=0)
for who, line in (("Alexia Jorge", "HBP"), ("Samaria Benitez", "1B"),
                  ("Andreanne Leblanc", "K"), ("Skylar Kaplan", "K"),
                  ("Caitlin Eynon", "2B"), ("Joely Leguizamon", "HR")):
    print(f"  {who:18s} {line:4s} {rate.loc[who, line]:5.1f}%  ({int(tab.loc[who, line])} in {int(n[who])} PA)")
print(f"  league: HBP {100 * L['HBP']:.1f}%, K {100 * L['K']:.1f}%, "
      f"1B {100 * L['1B']:.1f}%, 2B {100 * L['2B']:.1f}%, OUT {100 * L['OUT']:.1f}%")
print(f"  Lansdell OUT {rate.loc['Ashton Lansdell', 'OUT']:.1f}% vs league {100 * L['OUT']:.1f}%")
inplay = tab[["1B", "2B", "ROE", "OUT"]].sum(axis=1)
hits = tab[["1B", "2B"]].sum(axis=1)
print(f"  hits per ball in play: league {hits.sum() / inplay.sum():.3f}; " +
      ", ".join(f"{s} {hits[s] / inplay[s]:.3f}" for s in SLUG))
print(f"\n=== 11. league totals ===\nactual home runs {int(tab['HR'].sum())}")
