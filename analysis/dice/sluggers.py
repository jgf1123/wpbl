"""Where do Benites's and Whitmore's home runs come from? And do box-score rosters vary by game?"""
import glob
import json
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 220)
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["who"] = pa["batter_id"].map(person).fillna(pa["batter_id"]).map(name)

EVERYDAY = ["Amanda Gianelloni", "Andreanne Leblanc", "Ashton Lansdell", "Denae Benites", "Joely Leguizamon",
            "Kelsie Whitmore", "Natsuki Yonetani", "Ticara Geldenhuis"]
group = pd.Series("rest of league", index=pa.index)
group[pa["who"].isin(EVERYDAY)] = "other everyday starters"
for n in ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"):
    group[pa["who"] == n] = n
t = pd.crosstab(group, pa["line"]).reindex(columns=LINES, fill_value=0)
t.loc["all batters"] = t.sum()
rate = (100 * t.div(t.sum(axis=1), axis=0)).round(1)
bip = t[["HR", "1B", "2B", "ROE", "OUT"]].sum(axis=1)
rate.insert(0, "PA", t.sum(axis=1))
rate["HR per ball in play"] = (100 * t["HR"] / bip).round(1)
rate["hits per ball in play"] = (100 * t[["HR", "1B", "2B"]].sum(axis=1) / bip).round(1)
order = ["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay", "other everyday starters",
         "rest of league", "all batters"]
print("=== outcome rates, % of PA ===")
print(rate.reindex(order).to_string())

# do box-score rosters list a different set of names from game to game?
rows = []
for f in glob.glob("data/raw/boxscore/*.json"):
    box = json.load(open(f, encoding="utf-8"))["boxscore"]
    for team in box["teams"]:
        ps = team["players"]
        rows.append({"game": f[-21:-5], "team": team.get("name") or team.get("id"), "listed": len(ps),
                     "appeared": sum(1 for p in ps if p.get("id"))})
r = pd.DataFrame(rows)
r = r[r["listed"] > 0]
print("\n=== names listed per team-game in the box-score roster ===")
print(r.groupby("team")["listed"].describe()[["count", "min", "50%", "max"]].to_string())
