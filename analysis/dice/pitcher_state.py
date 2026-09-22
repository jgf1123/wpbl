"""Which of the published fatigue/state rules does WPBL data actually support?

    pixi run python analysis/dice/pitcher_state.py

Deadball and History Maker Baseball both carry two kinds of rule: WORKLOAD
(innings pitched, freshness tiers) and STATE (HMB's STRUGGLER after three
consecutive baserunners, self-clearing on an out; Deadball's run-allowed
triggers). fatigue.py found no workload effect within an appearance. These are
the state rules, which have a different clock -- a pitcher who cannot get anyone
out in a third of an inning is not tired, she is struggling.

Everything is scored as a RESIDUAL against the matchup: what the two cards,
mixed as the game mixes them, expect this plate appearance to be worth. That
removes both who batted and who pitched, so a rule cannot be credited for the
fact that good pitchers face fewer jams, or that heavily used relievers are the
ones a manager trusts. fatigue.py subtracted only the batter, which is enough
when the comparison is within one appearance and not enough when it is across
pitchers.

Rules tested:
  STRUGGLER   after n consecutive batters reach base, is the next one worse?
  ACE         a reliever entering mid-inning, on her first batter
  FRESHNESS   HMB's tiers: a starter's innings 1-3, 4-6, 7+
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import CARD_LINES, MIX_ALPHA, TO_LINE, cards

pd.set_option("display.width", 215)
ON_BASE = {"BB", "HBP", "1B", "2B", "HR", "ROE"}

lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean().reindex(CARD_LINES)

p = tables.read("plays", "all")
pl = tables.read("players", "training")
person = pl.set_index("player_id")["person_id"].to_dict()
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
pa["rv"] = pa["line"].map(W).astype(float)
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
B, P = cards("B"), cards("P")
ev = (B @ W).reindex(pa["B"]).to_numpy()
pv = (P @ W).reindex(pa["P"]).to_numpy()
lgm = float(pa["rv"].mean())
exp = MIX_ALPHA * np.where(np.isnan(pv), lgm, pv) + (1 - MIX_ALPHA) * np.where(np.isnan(ev), lgm, ev)
pa["resid"] = pa["rv"] - exp

pa = pa.sort_values(["game_id", "sequence"])
streak, first_bf, mid_inning, inn_seen = [], [], [], []
for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
    run = 0
    innings = {}
    for i, r in enumerate(grp.itertuples()):
        streak.append(run)
        first_bf.append(i == 0)
        mid_inning.append(i == 0 and int(r.outs_before) > 0)
        innings.setdefault(r.inning, len(innings) + 1)
        inn_seen.append(innings[r.inning])
        run = run + 1 if r.line in ON_BASE else 0
pa["streak"] = streak
pa["first_bf"] = first_bf
pa["entered_mid"] = mid_inning
pa["inning_n"] = inn_seen
starters = pa.groupby(["game_id", "pitcher_id"])["sequence"].min()
first_of_game = pa.groupby(["game_id", "pitching_team_id"])["sequence"].min()
pa["is_starter"] = [starters.get((g, q)) == first_of_game.get((g, tm))
                    for g, q, tm in zip(pa["game_id"], pa["pitcher_id"], pa["pitching_team_id"])]

g = pd.Categorical(pa["game_id"]).codes
nG = g.max() + 1
rng = np.random.default_rng(20260922)
DRAWS = [np.concatenate([np.flatnonzero(g == k) for k in rng.integers(0, nG, nG)])
         for _ in range(1500)]


def show(mask_map, title):
    print(f"\n=== {title} ===")
    v = pa["resid"].to_numpy()
    rows = []
    for label, m in mask_map.items():
        m = np.asarray(m)
        if m.sum() < 15:
            rows.append({"group": label, "BF": int(m.sum()), "resid": np.nan, "SE": np.nan})
            continue
        bs = [v[d][m[d]].mean() for d in DRAWS if m[d].sum() > 5]
        rows.append({"group": label, "BF": int(m.sum()), "resid": round(v[m].mean(), 4),
                     "SE": round(float(np.std(bs)), 4)})
    print(pd.DataFrame(rows).to_string(index=False))


s = pa["streak"].to_numpy()
show({"0 consecutive on": s == 0, "1": s == 1, "2": s == 2,
      "3+ (HMB STRUGGLER)": s >= 3}, "STRUGGLER: after n consecutive batters reached base")
show({"reliever, entered mid-inning, 1st batter": (~pa["is_starter"] & pa["entered_mid"]).to_numpy(),
      "reliever, started the inning, 1st batter": (~pa["is_starter"] & pa["first_bf"]
                                                   & ~pa["entered_mid"]).to_numpy(),
      "reliever, all later batters": (~pa["is_starter"] & ~pa["first_bf"]).to_numpy()},
     "ACE: a reliever's first batter")
i = pa["inning_n"].to_numpy()
st = pa["is_starter"].to_numpy()
show({"starter, her innings 1-3 (FRESH)": st & (i <= 3), "her innings 4-6 (SEMI-FRESH)":
      st & (i >= 4) & (i <= 6), "her innings 7+": st & (i >= 7)},
     "FRESHNESS: HMB's tiers")
