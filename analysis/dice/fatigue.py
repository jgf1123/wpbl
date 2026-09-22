"""Does a pitcher get worse as her appearance goes on?

    pixi run python analysis/dice/fatigue.py

Spec section 7 assumes fatigue strength is a tuned setting rather than an
estimate, because observed decline is confounded: managers pull pitchers who are
struggling, so the late innings belong to whoever was allowed to stay. That
biases the measured decline TOWARD ZERO -- the ones who would have collapsed were
already gone -- so a decline that survives the correction is real, and a flat
result is genuinely uninformative rather than evidence of no fatigue.

The correction is to condition on SURVIVORS. Among appearances that reached a
given depth, compare that same pitcher's early batters with her late ones.
Everyone in the comparison was allowed to stay, so the manager's decision no
longer decides who appears in the late bucket. It does not fix everything: a
manager still pulls mid-appearance, so the very last batters faced are still
selected. The residual bias points the same way, toward understating decline.

Scored on context-neutral run value -- the outcome priced by league linear
weights, ignoring the base-out state -- so that a pitcher who happens to face
tougher situations late is not counted as tiring. WHO batted is removed too, by
subtracting what the batter's own card expects: a pitcher's first 25 pitches
face the top of the order and her next 25 the bottom, so an uncorrected pitch
cut makes every pitcher look like she improves. That confound alone flips the
sign of the result.

Two cuts, because they fail differently:
  pitches       what the game's fatigue track would actually count
  times through the order   coarser, and insensitive to how pitches were counted
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import TO_LINE

pd.set_option("display.width", 215)
SCOPE = "training"

lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean()


def appearances(scope):
    p = tables.read("plays", scope)
    pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
    pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
    pa["rv"] = pa["line"].map(W).astype(float)
    pa["pitches"] = pd.to_numeric(pa["n_pitches"], errors="coerce").fillna(3.7)
    # what the batter's own card expects, so lineup order cannot masquerade as fatigue
    from wpbl.dice import CARD_LINES, cards, plate_appearances as _dpa
    B = cards("B")
    person = tables.read("players", scope if scope == "training" else "training")
    person = person.set_index("player_id")["person_id"].to_dict()
    bid = pa["batter_id"].map(person).fillna(pa["batter_id"])
    exp = (B @ W.reindex(CARD_LINES)).reindex(bid).to_numpy()
    pa["exp"] = np.where(np.isnan(exp), pa["rv"].mean(), exp)
    pa["resid"] = pa["rv"] - pa["exp"]
    pa = pa.sort_values(["game_id", "sequence"])
    out = []
    for (gm, pid), grp in pa.groupby(["game_id", "pitcher_id"], sort=False):
        grp = grp.sort_values("sequence")
        before = grp["pitches"].cumsum() - grp["pitches"]     # pitches thrown BEFORE this PA
        seen = {}
        tto = []
        for b in grp["batter_id"]:
            seen[b] = seen.get(b, 0) + 1
            tto.append(seen[b])
        out.append(grp.assign(before=before.to_numpy(), tto=tto,
                              total=grp["pitches"].sum(), bf=len(grp)))
    return pd.concat(out, ignore_index=True)


def gap(frame, col, lo, hi, seed=11, val="resid"):
    """Mean run value in bucket `hi` minus bucket `lo`, SE from resampling games."""
    a = frame[frame[col] == hi][val].to_numpy()
    b = frame[frame[col] == lo][val].to_numpy()
    if len(a) < 20 or len(b) < 20:
        return np.nan, np.nan, len(b), len(a)
    g = pd.Categorical(frame["game_id"]).codes
    nG = g.max() + 1
    rng = np.random.default_rng(seed)
    v, m_hi, m_lo = frame[val].to_numpy(), (frame[col] == hi).to_numpy(), (frame[col] == lo).to_numpy()
    boots = []
    for _ in range(2000):
        idx = np.concatenate([np.flatnonzero(g == k) for k in rng.integers(0, nG, nG)])
        h, l = m_hi[idx], m_lo[idx]
        if h.sum() > 5 and l.sum() > 5:
            boots.append(v[idx][h].mean() - v[idx][l].mean())
    return a.mean() - b.mean(), float(np.std(boots)), len(b), len(a)


app = appearances(SCOPE)
print(f"{app['game_id'].nunique()} games, {len(app)} plate appearances, "
      f"{app.groupby(['game_id','pitcher_id']).ngroups} appearances")
print(f"league run value allowed per batter faced: {app['rv'].mean():.4f}\n")

print("=== NO correction: everyone, bucketed by pitches already thrown ===")
app["bucket"] = pd.cut(app["before"], [-1, 24, 49, 74, 999],
                       labels=["0-24", "25-49", "50-74", "75+"])
t = app.groupby("bucket", observed=True)[["rv", "resid"]].agg(["size", "mean"]).round(4)
print(t.to_string())
print("  (this is the biased number: the late buckets hold only pitchers who were left in)")

print("\n=== survivor-conditioned: appearances that REACHED each depth ===")
rows = []
for depth in (50, 75, 90):
    sub = app[app["total"] >= depth].copy()
    if not len(sub):
        continue
    sub["bucket"] = pd.cut(sub["before"], [-1, 24, 49, 74, 999],
                           labels=["0-24", "25-49", "50-74", "75+"])
    means = sub.groupby("bucket", observed=True)["resid"].mean()
    last = "75+" if depth >= 90 else ("50-74" if depth >= 75 else "25-49")
    d, se, n0, n1 = gap(sub, "bucket", "0-24", last)
    rows.append({"reached": f"{depth}+ pitches",
                 "appearances": sub.groupby(['game_id','pitcher_id']).ngroups,
                 "early 0-24": round(means.get("0-24", np.nan), 4),
                 "late bucket": last, "late": round(means.get(last, np.nan), 4),
                 "late - early": round(d, 4) if d == d else np.nan,
                 "SE": round(se, 4) if se == se else np.nan,
                 "SE units": round(d / se, 2) if se == se and se else np.nan})
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== times through the order, among appearances that got that far ===")
rows = []
for n in (2, 3):
    sub = app[app.groupby(["game_id", "pitcher_id"])["tto"].transform("max") >= n]
    d, se, n0, n1 = gap(sub, "tto", 1, n)
    m = sub.groupby("tto", observed=True)["resid"].mean()
    rows.append({"reached": f"{n}x through",
                 "appearances": sub.groupby(['game_id','pitcher_id']).ngroups,
                 "1st time": round(m.get(1, np.nan), 4), f"{n}x": round(m.get(n, np.nan), 4),
                 "BF 1st": n0, f"BF {n}x": n1,
                 "difference": round(d, 4) if d == d else np.nan,
                 "SE": round(se, 4) if se == se else np.nan,
                 "SE units": round(d / se, 2) if se == se and se else np.nan})
print(pd.DataFrame(rows).to_string(index=False))


# ---- the other axis: workload carried in from previous days --------------------
# Semifinal G3, the one game played with genuinely spent bullpens, is excluded
# from training and is the only clean observation of fatigue there is. Within it,
# more pitches did NOT mean worse -- the 83-pitch outing was fine and the 42-pitch
# one was the worst -- so what it shows is a bullpen tired across DAYS, which is
# the axis section 7's usage targets describe and not the one measured above.
def between_games():
    p = tables.read("plays", "all")
    pl = tables.read("players", "training")
    person = pl.set_index("player_id")["person_id"].to_dict()
    from wpbl.dice import CARD_LINES, cards
    pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
    pa["line"] = [TO_LINE.get(e, "OUT") for e in pa["event_type"]]
    pa["rv"] = pa["line"].map(W).astype(float)
    pa["pitches"] = pd.to_numeric(pa["n_pitches"], errors="coerce").fillna(3.7)
    pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
    pa["Bp"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
    pa["date"] = pd.to_datetime(pa["game_date"].astype(str).str[:10])
    # Across days the buckets hold DIFFERENT pitchers -- the heavily used ones are
    # the arms a manager trusts -- so the pitcher's own card comes out too, not
    # just the batter's. (Within one appearance the pitcher is constant and
    # cancels, which is why the cut above subtracts only the batter.)
    from wpbl.dice import MIX_ALPHA
    P = cards("P")
    lgm = float(pa["rv"].mean())
    ev = (cards("B") @ W.reindex(CARD_LINES)).reindex(pa["Bp"]).to_numpy()
    pv = (P @ W.reindex(CARD_LINES)).reindex(pa["P"]).to_numpy()
    pa["resid"] = pa["rv"] - (MIX_ALPHA * np.where(np.isnan(pv), lgm, pv)
                              + (1 - MIX_ALPHA) * np.where(np.isnan(ev), lgm, ev))
    app = pa.groupby(["game_id", "P", "date"], as_index=False).agg(
        BF=("rv", "size"), pitches=("pitches", "sum"), resid=("resid", "mean"))
    rows = []
    for _, grp in app.groupby("P"):
        grp = grp.sort_values("date")
        d, pit = grp["date"].to_numpy(), grp["pitches"].to_numpy()
        for i in range(len(grp)):
            rows.append({"BF": grp["BF"].iloc[i], "resid": grp["resid"].iloc[i],
                         "prior3": pit[(d < d[i]) & (d >= d[i] - np.timedelta64(3, "D"))].sum(),
                         "prior7": pit[(d < d[i]) & (d >= d[i] - np.timedelta64(7, "D"))].sum()})
    a = pd.DataFrame(rows)
    a = a[a["BF"] >= 4]
    rng = np.random.default_rng(4)
    for col, cuts, lbl in (("prior3", [-1, 0, 25, 9999], "pitches in the prior 3 days"),
                           ("prior7", [-1, 0, 30, 70, 9999], "pitches in the prior 7 days")):
        a["b"] = pd.cut(a[col], cuts)
        rows2 = []
        for b, sub in a.groupby("b", observed=True):
            v, wt = sub["resid"].to_numpy(), sub["BF"].to_numpy()
            bs = [np.average(v[i], weights=wt[i])
                  for i in (rng.integers(0, len(v), len(v)) for _ in range(2000))
                  if wt[i].sum() > 0]
            rows2.append({"bucket": str(b), "appearances": len(sub), "BF": int(wt.sum()),
                          "run value per BF": round(float(np.average(v, weights=wt)), 4),
                          "SE": round(float(np.std(bs)), 4)})
        print(f"\n=== {lbl} ===")
        print(pd.DataFrame(rows2).to_string(index=False))


between_games()
