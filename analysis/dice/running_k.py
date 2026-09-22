"""Should the running-play rate be a flat band, or smoothed per pitcher?

    pixi run python analysis/dice/running_k.py

running_plays.py found no spread that clears sampling noise. But the league has
position players pressed into pitching (Izumi, Studer) and a knuckleballer
(Gilder), and giving the ace the same rate as an emergency arm does not feel
right. "Does not feel right" is testable: if the spread is real, smoothing each
pitcher's own rate toward a target should predict held-out games better than one
flat rate does.

    rate = (her running plays + k * target) / (her opportunities + k)

k = inf IS the flat band, so the flat band is a point on the sweep rather than a
rival to it. If the best k is finite by more than noise, the line belongs on the
pitcher's card; if the curve is flat out to inf, the band wins on its merits.

Two targets, because they disagree about exactly the pitchers in question:
  league   one rate for everyone
  cohort   her neighbours by usage, the same ranking the cards use -- which puts
           Sato among the workhorses and Izumi and Studer among the emergency arms

Scored on the log loss of the per-pitch binary (did a running play happen). This
is rate estimation, not a choice between outcomes of similar value, so spec 9.0's
runs-first rule does not bite; runs are reported alongside.

An event counts if it advanced a runner, which is the only kind the feed records
and the only kind the game needs. Mid-plate-appearance wild pitches folded into a
PA narrative are counted too.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import COHORT_PA, cohorts, plate_appearances, usage

pd.set_option("display.width", 220)
SPLITS = 20
GRID = [2 ** (e / 2) for e in range(0, 25)] + [np.inf]
DROP_BALKS = False
NAMED = ("Ayami Sato", "Liz Gilder", "Keira Izumi", "London Studer")

plays = tables.read("plays", "training").copy()
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
nm = players.drop_duplicates("person_id").set_index("person_id")["person_name"]
plays["P"] = plays["pitcher_id"].map(person).fillna(plays["pitcher_id"])
plays["kind"] = np.where(plays["play_kind"] == "balk", "balk", plays["event_type"])
narr = plays["narrative"].astype(str).str.lower()
on = plays["runners_on"].fillna(0) > 0

# dedicated rows, plus wild pitches / passed balls folded into a PA narrative
ded = plays["kind"].isin(["wild_pitch", "passed_ball"] + ([] if DROP_BALKS else ["balk"]))
mid = ((plays["play_kind"] == "plate_appearance")
       & (narr.str.contains("wild pitch") | narr.str.contains("passed ball")))
ev = plays[(ded | mid) & on].copy()

pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["pitches"] = pa["n_pitches"].fillna(pa["n_pitches_est"]).fillna(0)
pa_on = pa[pa["runners_on"].fillna(0) > 0]
print(f"running plays {len(ev)} (balks {'dropped' if DROP_BALKS else 'included'}); "
      f"opportunities {pa_on['pitches'].sum():.0f} pitches with a runner on")

ids = sorted(set(pa_on["P"]) | set(ev["P"]))
share = usage(plate_appearances())["P"].reindex(ids).fillna(0).to_numpy()
gids = sorted(plays["game_id"].unique())
rng = np.random.default_rng(20260921)


def tally(frame_ev, frame_opp):
    x = frame_ev.groupby("P").size().reindex(ids).fillna(0).to_numpy(float)
    n = frame_opp.groupby("P")["pitches"].sum().reindex(ids).fillna(0).to_numpy(float)
    return x, n


loss = np.zeros((2, len(GRID), len(gids)))
cnt = np.zeros(len(gids))
gpos = {g: i for i, g in enumerate(gids)}
for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    for fold in (0, 1):
        tr_ev = ev[ev["game_id"].map(half) != fold]
        tr_op = pa_on[pa_on["game_id"].map(half) != fold]
        te_ev = ev[ev["game_id"].map(half) == fold]
        te_op = pa_on[pa_on["game_id"].map(half) == fold]
        x, n = tally(tr_ev, tr_op)
        L = x.sum() / max(n.sum(), 1)
        coh = cohorts(share, n, np.zeros(len(n), bool))
        tgt_coh = np.array([x[c].sum() / max(n[c].sum(), 1e-9) if len(c) else L for c in coh])
        # held-out counts per pitcher, per game
        te_x = te_ev.groupby(["game_id", "P"]).size()
        te_n = te_op.groupby(["game_id", "P"])["pitches"].sum()
        for (gid, pid), opp in te_n.items():
            if opp <= 0 or pid not in ids:
                continue
            i = ids.index(pid)
            k_ev = float(te_x.get((gid, pid), 0.0))
            gp = gpos[gid]
            cnt[gp] += opp
            for m, tgt in enumerate((np.full(len(ids), L), tgt_coh)):
                for j, k in enumerate(GRID):
                    if np.isinf(k):
                        p = tgt[i]
                    else:
                        p = (x[i] + k * tgt[i]) / (n[i] + k)
                    p = min(max(p, 1e-6), 1 - 1e-6)
                    loss[m, j, gp] += -(k_ev * np.log(p) + (opp - k_ev) * np.log(1 - p))
    print(f"  split {rep + 1}/{SPLITS}", flush=True)

tot = loss.sum(axis=2) / cnt.sum()
draws = np.random.default_rng(7).integers(0, len(gids), size=(2000, len(gids)))
lab = ["inf" if np.isinf(k) else f"{k:g}" for k in GRID]
for m, name in enumerate(("target = league", "target = usage cohort")):
    best = int(np.argmin(tot[m]))
    flat = len(GRID) - 1
    d = loss[m, best] - loss[m, flat]
    se = (1000 * d[draws].sum(axis=1) / cnt[draws].sum(axis=1)).std()
    print(f"\n=== {name} ===")
    print("  log loss x1000 by k: " + ", ".join(
        f"{lab[j]}:{1000 * tot[m, j]:.3f}" for j in range(0, len(GRID), 3)) +
        f", inf:{1000 * tot[m, flat]:.3f}")
    print(f"  best k = {lab[best]} (log loss {1000 * tot[m, best]:.4f}); "
          f"the flat band (k=inf) is {1000 * (tot[m, flat] - tot[m, best]):+.4f}, SE {se:.4f}")
