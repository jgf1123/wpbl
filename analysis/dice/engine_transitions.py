"""Where the engine's base-out transitions differ from the season's.

    pixi run python analysis/dice/engine_transitions.py

Run expectancy collapses a state to one number, so two errors that cancel are
invisible in it. The transition distribution does not: from each base-out state
there is a fixed distribution over the state the next batter inherits and the
runs scored on the way, and the engine either reproduces it or it does not.

Both sides are counted in the same unit -- the state at the start of one plate
appearance, to the state at the start of the next, with every run in between.
That folds steals, wild pitches and pickoffs into the transition they belong to,
which is what the engine does anyway (it rolls a steal, then the plate
appearance, rerolling on a running play).
"""
import numpy as np
import pandas as pd

from wpbl import engine, tables

pd.set_option("display.width", 230)
N = 60000
BASES = engine.BASE_ORDER
STATES = [(b, o) for o in range(3) for b in BASES]
END = ("END", 3)


def code(p):
    return "".join(c if isinstance(b, str) else "_" for c, b in
                   zip("123", (p.first_base, p.second_base, p.third_base)))


def observed():
    """PA-to-PA transitions from the season."""
    plays = tables.read("plays", "training").copy()
    plays["half_key"] = list(zip(plays["game_id"], plays["inning"], plays["half"]))
    stopped = {g: blk.sort_values("sequence")["half_key"].iloc[-1]
               for g, blk in plays.groupby("game_id")}
    rows = []
    for key, half in plays.groupby("half_key", sort=False):
        live = [p for p in half.sort_values("sequence").itertuples() if p.outs_before < 3]
        idx = [i for i, p in enumerate(live) if p.play_kind == "plate_appearance"]
        for n, i in enumerate(idx):
            start = (code(live[i]), int(live[i].outs_before))
            j = idx[n + 1] if n + 1 < len(idx) else None
            runs = sum(float(live[k].runs_scored) for k in
                       range(i, j if j is not None else len(live)))
            if j is not None:
                target = (code(live[j]), int(live[j].outs_before))
            elif stopped.get(live[i].game_id) == key:
                continue                       # walk-off or called game: censored
            else:
                target = END
            rows.append({"start": start, "target": target, "runs": int(runs)})
    return pd.DataFrame(rows)


def simulated(table, n=N, seed=20260921):
    """The same thing, played."""
    rng = np.random.default_rng(seed)
    rows = []
    for bases, outs in STATES:
        occ = tuple(c != "_" for c in bases)
        for _ in range(n):
            b, o = occ, outs
            b2, made, early, runs = engine.plate_appearance(table, b, o, rng)
            o += made
            total = early + (runs if o < 3 else 0)
            if o < 3:                      # the steal belongs to THIS transition
                b2, made = engine.steal(b2, rng)
                o += made
            rows.append({"start": (bases, outs),
                         "target": END if o >= 3 else (
                             "".join(c if f else "_" for c, f in zip("123", b2)), o),
                         "runs": int(total)})
    return pd.DataFrame(rows)


def dist(frame):
    g = frame.groupby(["start", "target", "runs"]).size().rename("n").reset_index()
    g["p"] = g["n"] / g.groupby("start")["n"].transform("sum")
    return g


obs, sim = dist(observed()), dist(simulated(engine.league_table()))
seen = observed().groupby("start").size()
both = obs.merge(sim, on=["start", "target", "runs"], how="outer",
                 suffixes=("_obs", "_sim")).fillna({"p_obs": 0.0, "p_sim": 0.0, "n_obs": 0})
both["gap"] = both["p_sim"] - both["p_obs"]

print("=== how far each state's transition distribution is off ===")
print("TV distance: half the summed absolute gap, 0 = identical. A state seen only")
print("10 times will look far off even if the engine is exact, so each is compared")
print("with what sampling ALONE gives: n draws from the engine's own distribution.\n")
rng = np.random.default_rng(11)
rows = []
for st in STATES:
    s = both[both["start"] == st]
    n_obs = int(seen.get(st, 0))
    tv = 0.5 * s["gap"].abs().sum()
    p = s["p_sim"].to_numpy()
    p = p / p.sum() if p.sum() > 0 else p
    null = []
    if n_obs > 0 and len(p):
        draws = rng.multinomial(n_obs, p, size=400) / n_obs
        null = 0.5 * np.abs(draws - p).sum(axis=1)
    rows.append({"state": f"{st[0]} {st[1]}out", "PAs seen": n_obs,
                 "TV distance": round(tv, 3),
                 "sampling alone": round(float(np.mean(null)), 3) if len(null) else np.nan,
                 "excess": round(tv - float(np.mean(null)), 3) if len(null) else np.nan,
                 "p": round(float(np.mean(null >= tv)), 3) if len(null) else np.nan})
t2 = pd.DataFrame(rows).sort_values("excess", ascending=False)
print(t2.to_string(index=False))
w = t2["PAs seen"].clip(lower=1)
print(f"\n  PA-weighted mean TV distance {np.average(t2['TV distance'], weights=w):.3f}, "
      f"sampling alone {np.average(t2['sampling alone'], weights=w):.3f}, "
      f"excess {np.average(t2['excess'], weights=w):.3f}")
print(f"  states where the gap beats sampling at p < 0.05: "
      f"{int((t2['p'] < 0.05).sum())} of 24")

print("\n=== the individual transitions the engine gets most wrong ===")
big = both[both["n_obs"] >= 8].copy()
big = big.loc[big["gap"].abs().sort_values(ascending=False).index].head(16)
big["state"] = [f"{s[0]} {s[1]}out" for s in big["start"]]
big["to"] = [f"{x[0]} {x[1]}out" if x != END else "inning over" for x in big["target"]]
big["season %"] = (100 * big["p_obs"]).round(1)
big["engine %"] = (100 * big["p_sim"]).round(1)
big["gap pts"] = (100 * big["gap"]).round(1)
print(big[["state", "to", "runs", "season %", "engine %", "gap pts"]].to_string(index=False))
