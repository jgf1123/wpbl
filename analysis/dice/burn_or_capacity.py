"""Is a reliever's faster burn a separate parameter, or just a smaller capacity?

    pixi run python analysis/dice/burn_or_capacity.py

History Maker gives a reliever one FRESH inning against a starter's three, which
is where the "3x burn" in other games comes from. Our capacities are 68 pitches
against 31, about 2.2:1. The question is whether those are two ways of saying the
same thing.

WITHIN one outing they are algebraically identical: a threshold of 31 with a rate
of 1 behaves exactly like a threshold of 93 with a rate of 3. Nothing can
distinguish them.

ACROSS days they are not, because recovery is in track units. At rate 3 a
reliever's 31-pitch outing puts 93 on her track and takes almost seven days to
clear at 14 a day -- but relievers pitch far more often than that. At rate 1 it
puts 31 on and clears in a bit over two days.

So the test is the observed rhythm: how often each role pitches, and what that
implies for a sustainable pitches-per-day. If one recovery rate serves both roles,
the burn multiplier is redundant and capacity carries it.
"""
import numpy as np
import pandas as pd

from wpbl import tables

pd.set_option("display.width", 215)
p = tables.read("plays", "all")
pl = tables.read("players", "training")
person = pl.set_index("player_id")["person_id"].to_dict()
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["pitches"] = pd.to_numeric(pa["n_pitches"], errors="coerce").fillna(3.7)
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["date"] = pd.to_datetime(pa["game_date"].astype(str).str[:10])
pa = pa.sort_values(["game_id", "sequence"])
first = pa.groupby(["game_id", "pitching_team_id"])["sequence"].min()
opens = pa.groupby(["game_id", "pitcher_id"])["sequence"].min()
pa["is_starter"] = [opens.get((g, q)) == first.get((g, tm))
                    for g, q, tm in zip(pa["game_id"], pa["pitcher_id"], pa["pitching_team_id"])]
app = pa.groupby(["game_id", "P", "date"], as_index=False).agg(
    BF=("pitches", "size"), pitches=("pitches", "sum"), starter=("is_starter", "first"))

rows = []
for pid, grp in app.groupby("P"):
    grp = grp.sort_values("date")
    d = grp["date"].to_numpy()
    for i in range(1, len(grp)):
        rows.append({"P": pid, "starter": bool(grp["starter"].iloc[i]),
                     "rest": (d[i] - d[i - 1]) / np.timedelta64(1, "D"),
                     "pitches": grp["pitches"].iloc[i]})
g = pd.DataFrame(rows)
print("=== how often each role works, and how much ===")
t = g.groupby("starter").agg(appearances=("rest", "size"), rest_median=("rest", "median"),
                             rest_mean=("rest", "mean"), pitches_median=("pitches", "median"))
t.index = ["relief", "start"]
t["sustainable pitches/day"] = (t["pitches_median"] / t["rest_median"]).round(1)
print(t.round(2).to_string())

print("\n=== what a 3x burn would imply, against what is observed ===")
for role, lbl in ((True, "starter"), (False, "reliever")):
    sub = g[g["starter"] == role]
    med_p, med_r = sub["pitches"].median(), sub["rest"].median()
    mult = 1.0 if role else 3.0
    print(f"  {lbl}: {med_p:.0f} pitches every {med_r:.0f} days")
    print(f"    at burn 1x, the track carries {med_p:.0f} and clears in "
          f"{med_p/14:.1f} days at 14/day")
    if not role:
        print(f"    at burn 3x, it carries {med_p*3:.0f} and clears in "
              f"{med_p*3/14:.1f} days -- longer than she actually rests")

print("\n=== 7-day load, the section 7 target ===")
loads = []
for pid, grp in app.groupby("P"):
    grp = grp.sort_values("date")
    d, pit, st = grp["date"].to_numpy(), grp["pitches"].to_numpy(), grp["starter"].to_numpy()
    for i in range(len(grp)):
        win = (d <= d[i]) & (d > d[i] - np.timedelta64(7, "D"))
        loads.append({"had_start": bool(st[win].any()), "load": pit[win].sum()})
L = pd.DataFrame(loads)
print(L.groupby("had_start")["load"].agg(["size", "median"]).rename(
    index={True: "week with a start", False: "relief-only week"}).to_string())
print("  section 7 targets: 85 with a start, 45 relief-only")
