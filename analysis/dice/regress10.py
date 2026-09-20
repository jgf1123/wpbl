"""Table 2 of the blog: the top 10 in one set of games, and the same 10 in their other set.

Odd-numbered vs even-numbered games, so improvement over the season can't drive it.
For each outcome a batter is ranked on her better set (most walks, fewest strikeouts),
and we then read her other set. Strikeouts are ranked low-is-better: the contact
leaders, not the batters who struck out most.
"""
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 220)
MIN_PA = 20
LINES = {"Walks": "walk", "Hit by pitch": "hit_by_pitch", "Singles": "single",
         "Doubles": "double", "Strikeouts": "strikeout", "Home runs": "home_run"}
LOW_IS_BETTER = {"Strikeouts"}
ALSO_HIGH = {"Strikeouts": "Strikeouts (most, the old row)"}
plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["o"] = [contact(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
gids = sorted(pa["game_id"].unique())
pa["set"] = pa["game_id"].map({g: i % 2 for i, g in enumerate(gids)})
print(f"{len(gids)} games, {len(pa)} PAs; sets of {pa[pa['set']==0]['game_id'].nunique()} "
      f"and {pa[pa['set']==1]['game_id'].nunique()} games")

rows = []
JOBS = [(k, v, k in LOW_IS_BETTER) for k, v in LINES.items()]
JOBS += [(ALSO_HIGH[k], LINES[k], False) for k in ALSO_HIGH]
for label, ev, low in JOBS:
    d = pa.assign(hit=(pa["o"] == ev).astype(int))
    w = d.pivot_table(index="B", columns="set", values="hit", aggfunc=["size", "sum"])
    w.columns = ["n0", "n1", "x0", "x1"]
    w = w[(w["n0"] >= MIN_PA) & (w["n1"] >= MIN_PA)]
    r0, r1 = w["x0"] / w["n0"], w["x1"] / w["n1"]
    # her better set, and the other one
    best = pd.DataFrame({"best": r0.where((r0 <= r1) if low else (r0 >= r1), r1),
                         "other": r1.where((r0 <= r1) if low else (r0 >= r1), r0),
                         "xb": w["x0"].where((r0 <= r1) if low else (r0 >= r1), w["x1"]),
                         "nb": w["n0"].where((r0 <= r1) if low else (r0 >= r1), w["n1"]),
                         "xo": w["x1"].where((r0 <= r1) if low else (r0 >= r1), w["x0"]),
                         "no": w["n1"].where((r0 <= r1) if low else (r0 >= r1), w["n0"])})
    top = best.sort_values("best", ascending=low).head(10)
    lg = d["hit"].mean()
    out = {"Outcome": label, "batters": len(w), "League": round(100 * lg, 1)}
    # A: rank in the odd games only, read the even games
    a = pd.DataFrame({"r": r0, "x0": w["x0"], "n0": w["n0"], "x1": w["x1"], "n1": w["n1"]})
    a = a.sort_values("r", ascending=low).head(10)
    out["A rank"] = round(100 * a["x0"].sum() / a["n0"].sum(), 1)
    out["A other"] = round(100 * a["x1"].sum() / a["n1"].sum(), 1)
    # B: both directions pooled (rank in each set, read the other)
    b2 = pd.DataFrame({"r": r1, "x0": w["x1"], "n0": w["n1"], "x1": w["x0"], "n1": w["n0"]})
    b2 = b2.sort_values("r", ascending=low).head(10)
    both = pd.concat([a, b2])
    out["B rank"] = round(100 * both["x0"].sum() / both["n0"].sum(), 1)
    out["B other"] = round(100 * both["x1"].sum() / both["n1"].sum(), 1)
    # C: each batter's own better set (selects on the max: biased)
    out["C rank"] = round(100 * top["xb"].sum() / top["nb"].sum(), 1)
    out["C other"] = round(100 * top["xo"].sum() / top["no"].sum(), 1)
    edge = out["B rank"] - out["League"]
    out["keeps"] = f'{(out["B other"] - out["League"]) / edge:.0%}' if edge else "-"
    rows.append(out)
    if label in ("Strikeouts", "Walks"):
        print(f"\nthe 10 {'contact leaders (fewest K)' if low else 'best walkers'}:")
        print(top.assign(who=[name.get(i, i) for i in top.index])
                 .round(3).to_string(index=False, columns=["who", "nb", "xb", "best", "no", "xo", "other"]))
print(f"\n=== Table 2 ({MIN_PA}+ PAs in each set) ===")
print(pd.DataFrame(rows).to_string(index=False))
