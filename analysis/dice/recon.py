"""League rate of each card entry over three populations of the same PAs."""
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["o"] = [contact(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
print(f"training games {pa['game_id'].nunique()}, plate appearances {len(pa)}")
print("game types:", plays.drop_duplicates("game_id")["game_type"].value_counts().to_dict()
      if "game_type" in plays else "n/a")

# same qualifier floors as the 15 Sep cards.py: pitchers 40+ BF, batters 25+ PA
for col, floor in (("pitcher_id", 40), ("batter_id", 25)):
    pid = pa[col].map(person).fillna(pa[col])
    size = pid.map(pid.value_counts())
    pa["q_" + col] = size >= floor
    print(f"{col}: {pid.nunique()} people, {int((pid.value_counts() >= floor).sum())} qualify, "
          f"covering {pa['q_' + col].mean():.1%} of PAs")

ENTRIES = {"K": ["strikeout"], "BB": ["walk"], "HBP": ["hit_by_pitch"], "HR": ["home_run"],
           "single": ["single"], "double+triple": ["double", "triple"], "ROE": ["reached_on_error"]}
rows = []
for entry, labels in ENTRIES.items():
    hit = pa["o"].isin(labels)
    rows.append({"entry": entry,
                 "all PAs": round(100 * hit.mean(), 2),
                 "qualifying pitchers": round(100 * hit[pa["q_pitcher_id"]].mean(), 2),
                 "qualifying batters": round(100 * hit[pa["q_batter_id"]].mean(), 2),
                 "non-qualifying batters": round(100 * hit[~pa["q_batter_id"]].mean(), 2)})
print(pd.DataFrame(rows).to_string(index=False))
print("\nunlabelled outcomes:", pa.loc[~pa["o"].isin(sum(ENTRIES.values(), []) + [
    "groundout", "flyout", "popup", "lineout", "foul_out", "out"]), "o"].value_counts().to_dict())
