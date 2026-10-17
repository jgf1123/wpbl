"""The leverage at real pitching changes (2026, postseason included): the stakes
a relief decision is typically made at, to set against the cost of a warm-up
(marginal_pitches.py).

    pixi run python analysis/manager/change_leverage.py

Every change of pitcher, with the leverage index of the situation the new
pitcher inherited (leverage.py; an average half-inning start = 1.00), split by
whether the starter was the one relieved, and by whether the change came at a
half-inning start or mid-inning.
"""
import numpy as np
import pandas as pd

from wpbl import manager as M, play, tables
from wpbl.leverage import Leverage

lev = Leverage()
cards, wp = play.shared()
model = M.Model(cards, wp)
plays = tables.read("plays", "all")
starters = tables.read("pitching", "all")
starters = set(zip(starters.loc[starters["is_starter"] == True, "game_id"],
                   starters.loc[starters["is_starter"] == True, "player_id"]))
live = (plays[(plays["outs_before"] < 3) & plays["is_plate_appearance"]]
        .dropna(subset=["pitching_team_id", "pitcher_id"]).sort_values(["game_id", "sequence"]))

rows = []
for (game, team), side in live.groupby(["game_id", "pitching_team_id"]):
    prev = None
    for (inning, half), block in side.groupby(["inning", "half"], sort=False):
        order = list(dict.fromkeys(block["pitcher_id"]))
        for k, name in enumerate(order):
            outgoing = order[k - 1] if k > 0 else prev
            if outgoing is None or outgoing == name:
                continue                                # game opener, or carrying on
            e = block[block["pitcher_id"] == name].iloc[0]
            bases = ("1" if pd.notna(e["first_base"]) else "_") + \
                    ("2" if pd.notna(e["second_base"]) else "_") + \
                    ("3" if pd.notna(e["third_base"]) else "_")
            d = int(e["home_score_before"] - e["away_score_before"])
            rows.append({"inning": inning, "mid": k > 0,
                         "starter_out": (game, outgoing) in starters,
                         "li": lev.state(int(inning), half, int(e["outs_before"]), bases, d),
                         "rv": model.run_value(int(inning), half == "top", int(e["outs_before"]),
                                               [c != "_" for c in bases], d)})
        prev = order[-1]
r = pd.DataFrame(rows)


def show(label, x):
    print(f"  {label:34s} n {len(x):3d}  mean {x.mean():.2f}  median {x.median():.2f}  "
          f"25-75% {x.quantile(.25):.2f}-{x.quantile(.75):.2f}  share >= 1: {100 * (x >= 1).mean():.0f}%")


print(f"{len(r)} pitching changes")
print("run-value index (dice model):")
show("all changes", r["rv"])
show("starter relieved", r.loc[r["starter_out"], "rv"])
show("reliever relieved", r.loc[~r["starter_out"], "rv"])
print("spread index (leverage.py):")
show("all changes", r["li"])
show("starter relieved", r.loc[r["starter_out"], "li"])
show("reliever relieved", r.loc[~r["starter_out"], "li"])
show("at a half-inning start", r.loc[~r["mid"], "li"])
show("mid-inning", r.loc[r["mid"], "li"])
print("\nstarter relieved, by inning of the change:")
for inn, x in r[r["starter_out"]].groupby(r["inning"].clip(upper=8))["li"]:
    show(f"inning {inn}{'+' if inn == 8 else ''}", x)
