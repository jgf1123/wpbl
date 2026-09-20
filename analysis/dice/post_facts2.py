"""The rest of the blog's non-card numbers: season shape, everyday starters, singles."""
import pandas as pd

from wpbl import tables
from wpbl.dice import plate_appearances, usage

pd.set_option("display.width", 220)
allg = tables.read("games", "all")
tr = tables.read("games", "training")
pa = plate_appearances()
print("games columns:", list(allg.columns))
tid = set(pa["game_id"].unique())
print(f"\nall games {len(allg)}, training {len(tr)}, used by plate appearances {len(tid)}")
for c in allg.columns:
    if allg[c].dtype == object and allg[c].nunique() <= 8:
        print(f"  {c}: {allg[c].value_counts().to_dict()}")
miss = allg[~allg["game_id"].isin(tid)]
if len(miss):
    cols = [c for c in ("game_id", "date", "home_team_name", "away_team_name",
                        "home_runs", "away_runs") if c in miss.columns]
    print("\nexcluded from training:")
    print(miss[cols].to_string(index=False))

print("\n=== everyday starters ===")
share = usage(pa)["B"]
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
s = share[share >= 0.999]
n = pa.groupby("B").size()
t = pd.DataFrame({"batter": [players["person_name"].get(i, i) for i in s.index],
                  "share": s.round(3), "PA": n.reindex(s.index)}).sort_values("PA", ascending=False)
print(t.to_string(index=False))
print(f"  {len(t)} batters at 100% of team games started; median PA {t['PA'].median():.0f}")
bf = pa.groupby("P").size()
print(f"  pitchers with 50+ BF: {int((bf >= 50).sum())}, median {bf[bf >= 50].median():.0f}")

print("\n=== who counts as a regular ===")
g = pa.groupby("B")["game_id"].nunique()
for thr in (15, 17, 20):
    print(f"  batters in {thr}+ games: {int((g >= thr).sum())}")
for thr in (25, 40, 50, 60):
    print(f"  batters with {thr}+ PA: {int((n >= thr).sum())}")

print("\n=== singles: did the runner from 2nd score? ===")
plays = tables.read("plays", "training").sort_values(["game_id", "sequence"])
live = plays[plays["outs_before"] < 3]
rows = []
for _, half in live.groupby(["game_id", "batting_team_id", "inning", "half"], sort=False):
    rec = list(half.itertuples())
    for i, p in enumerate(rec):
        if p.play_kind != "plate_appearance" or not isinstance(p.second_base, str):
            continue
        if str(p.event_type) != "single":
            continue
        nxt = rec[i + 1] if i + 1 < len(rec) else None
        if nxt is None:
            continue
        on3 = isinstance(nxt.third_base, str) and nxt.third_base == p.second_base
        on2 = isinstance(nxt.second_base, str) and nxt.second_base == p.second_base
        rows.append({"outs": int(p.outs_before), "scored": not (on3 or on2)})
d = pd.DataFrame(rows)
print(d.groupby(d["outs"] == 2)["scored"].agg(["size", "mean"]).rename(
    index={False: "0-1 out", True: "2 out"}).round(3).to_string())
