"""Unqualified pitchers, Benites/Whitmore HR by halves, batter rates by PA decile."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 220)
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
plays = tables.read("plays", "training")
games = tables.read("games", "training").set_index("game_id")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pa["P"] = pa["pitcher_id"].map(person)
pa["date"] = pa["game_id"].map(games["first_pitch_utc"])
pa = pa.sort_values(["date", "game_id", "sequence"])

# ---------------- 1. unqualified pitchers ----------------
reg_games = tables.read("games", "default")
reg_games = reg_games[reg_games["is_final"] == True]
team_games = pd.concat([reg_games["home_team_name"], reg_games["away_team_name"]]).value_counts()
print("regular-season games per team:", team_games.to_dict())
cut_outs = 3 * 7 / 9 * team_games.max()
reg = tables.read("pitching", "default").groupby("person_id")["ip_outs"].sum()
print(f"qualified = at least 7 IP per 9 team games = {cut_outs / 3:.2f} IP ({cut_outs:.0f} outs)")
with_p = pa.dropna(subset=["P"])
pit_pa = with_p.groupby("P").size()
rows = []
for label, cut in (("under 6 IP (tryout)", 18), (f"under {cut_outs / 3:.2f} IP (unqualified)", cut_outs)):
    under = set(reg[reg < cut].index) | (set(pit_pa.index) - set(reg.index))   # no regular-season IP -> under
    sel = with_p["P"].isin(under)
    rows.append({"group": label, "pitchers": len(under & set(pit_pa.index)),
                 "PAs": int(sel.sum()), "share of PAs": f"{sel.mean():.1%}",
                 **{l: round(100 * (with_p.loc[sel, 'line'] == l).mean(), 1) for l in ("K", "BB", "HR", "1B")}})
    rows.append({"group": "  the rest", "pitchers": len(set(pit_pa.index) - under), "PAs": int((~sel).sum()),
                 "share of PAs": f"{(~sel).mean():.1%}",
                 **{l: round(100 * (with_p.loc[~sel, 'line'] == l).mean(), 1) for l in ("K", "BB", "HR", "1B")}})
print(pd.DataFrame(rows).to_string(index=False))
unq = reg[reg < cut_outs].sort_values()
print("unqualified pitchers (regular-season IP, training PAs):")
print(", ".join(f"{name.get(i, i)} {v // 3}.{v % 3} ({int(pit_pa.get(i, 0))})" for i, v in unq.astype(int).items()))

# ---------------- 2. Benites / Whitmore by halves ----------------
print("\n=== home runs by halves of each slugger's own PAs ===")
for who in ("Denae Benites", "Kelsie Whitmore"):
    mine = pa[pa["B"].map(name) == who].copy()
    mine["i"] = np.arange(len(mine))
    gidx = {g: k for k, g in enumerate(mine["game_id"].unique())}
    parts = {"first half of her PAs": mine["i"] < len(mine) / 2, "second half": mine["i"] >= len(mine) / 2,
             "odd games": mine["game_id"].map(gidx) % 2 == 0, "even games": mine["game_id"].map(gidx) % 2 == 1}
    cells = [f"{k}: {int((mine.loc[s, 'line'] == 'HR').sum())}/{int(s.sum())} = "
             f"{100 * (mine.loc[s, 'line'] == 'HR').mean():.1f}%" for k, s in parts.items()]
    print(f"  {who}: " + "; ".join(cells))

# ---------------- 3. batter rates by PA decile ----------------
x = pd.crosstab(pa["B"], pa["line"]).reindex(columns=LINES, fill_value=0)
n = x.sum(axis=1)
by_n = n.groupby(n).sum().sort_index()
u = n.map((by_n.cumsum() - by_n / 2) / by_n.sum())
dec = (u * 10).astype(int).clip(0, 9) + 1
tab = x.groupby(dec).sum()
out = (100 * tab.div(tab.sum(axis=1), axis=0)).round(1)
out.insert(0, "PAs", tab.sum(axis=1))
out.insert(0, "PA each", [f"{int(n[dec == d].min())}-{int(n[dec == d].max())}" for d in tab.index])
out.insert(0, "batters", dec.value_counts().sort_index())
who = {d: ", ".join(name.get(i, i).split()[-1] for i in dec[dec == d].index
                    if name.get(i) in ("Denae Benites", "Kelsie Whitmore")) for d in tab.index}
out["sluggers"] = pd.Series(who)
out.index = [f"D{d}" for d in out.index]
print("\n=== batter rates by decile of plate appearances (%, 36 training games) ===")
print(out.to_string())
