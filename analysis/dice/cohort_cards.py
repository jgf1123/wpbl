"""Cards smoothed toward a sliding cohort of players with similar team share.

Rank: share of her team's PAs (batters) / batters faced (pitchers), with traded
players' denominator limited to each team's games during her tenure there.
Cohort for each line: nearest players by share, excluding her, until their
PAs reach that line's size (4k). Target = cohort's pooled rate; card =
(own count + k * target) / (own PA + k), k re-estimated around the targets."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 250)
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
SIZES = {"B": {"K": 184, "HBP": 122, "HR": 145, "1B": 287}, "P": {"K": 191, "BB": 328}}
FLOOR = {"B": 25, "P": 40}

plays = tables.read("plays", "training")
games = tables.read("games", "all")
team_name = pd.concat([games.set_index("home_team_id")["home_team_name"],
                       games.set_index("away_team_id")["away_team_name"]]).groupby(level=0).first()
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["B_team"] = pa["batting_team_id"].map(team_name)
pa["P_team"] = pa["pitching_team_id"].map(team_name)
pa["date"] = pa["game_date"].astype(str).str[:10]
L = pa["line"].value_counts(normalize=True)
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs")


def shares(side):
    """Her PAs / her team's PAs over her tenure. Traded players: tenure with a
    team runs until her first appearance for the next one."""
    team_by_date = pa.groupby([side + "_team", "date"]).size()
    own = pa.groupby(side).size()
    out, traded = {}, []
    for pid, g in pa.groupby(side):
        firsts = g.groupby(side + "_team")["date"].min().sort_values()
        denom = 0
        for i, (team, first) in enumerate(firsts.items()):
            dates = team_by_date.loc[team]
            lo = first if i > 0 else "0000"
            hi = firsts.iloc[i + 1] if i + 1 < len(firsts) else "9999"
            denom += int(dates[(dates.index >= lo) & (dates.index < hi)].sum())
        if len(firsts) > 1:
            traded.append(f"{name.get(pid, pid)} ({' -> '.join(firsts.index)})")
        out[pid] = own[pid] / denom
    return pd.Series(out), traded


def cohort_cards(side, sizes):
    share, traded = shares(side)
    x = pd.crosstab(pa[side], pa["line"])
    n = x.sum(axis=1).reindex(share.index)
    x = x.reindex(share.index)
    ids = share.index.to_numpy()
    s = share.to_numpy()
    targets, members = {}, {}
    for line, size in sizes.items():
        t = {}
        for i, pid in enumerate(ids):
            order = np.argsort(np.abs(s - s[i]), kind="stable")
            order = order[order != i]                      # never her own PAs
            cum = np.cumsum(n.to_numpy()[order])
            take = order[: int(np.searchsorted(cum, size)) + 1]
            t[pid] = x[line].to_numpy()[take].sum() / n.to_numpy()[take].sum()
            members[(pid, line)] = ids[take]
        targets[line] = pd.Series(t)
    target = pd.DataFrame(targets)
    rate = x[list(sizes)].div(n, axis=0)
    qual = n >= FLOOR[side]
    card, ks = pd.DataFrame(index=ids), {}
    for line in sizes:
        tt = target[line]
        tau2 = float(((rate[line] - tt) ** 2 - tt * (1 - tt) / n)[qual].mean())
        k = L[line] * (1 - L[line]) / tau2 if tau2 > 0 else np.inf
        ks[line] = k
        card[line] = tt if np.isinf(k) else (x[line] + k * tt) / (n + k)
    return share, n, x, rate, target, card, ks, members, traded


def half_scheme(side, line):
    """The previous batter scheme: straight line between low- and high-half means by PA position."""
    x = pd.crosstab(pa[side], pa["line"])
    n = x.sum(axis=1)
    by = n.groupby(n).sum().sort_index()
    u = n.map((by.cumsum() - by / 2) / by.sum())
    low, high = x[u < .5][line].sum() / n[u < .5].sum(), x[u >= .5][line].sum() / n[u >= .5].sum()
    t = low + (high - low) * ((u - .25) / .5).clip(0, 1)
    r, q = x[line] / n, n >= 25
    tau2 = float(((r - t) ** 2 - t * (1 - t) / n)[q].mean())
    k = L[line] * (1 - L[line]) / tau2
    return (x[line] + k * t) / (n + k), k


# ---------------- batters: HR ----------------
share, n, x, rate, target, card, ks, members, traded = cohort_cards("B", SIZES["B"])
print("traded batters:", traded)
old_card, old_k = half_scheme("B", "HR")
hr = pd.DataFrame({"team share %": 100 * share, "PA": n, "HR": x["HR"], "raw %": 100 * rate["HR"],
                   "cohort target %": 100 * target["HR"], "card %": 100 * card["HR"],
                   "card HR": card["HR"] * n, "old card %": 100 * old_card.reindex(n.index),
                   "old card HR": old_card.reindex(n.index) * n})
hr["share rank"] = hr["team share %"].rank(ascending=False).astype(int)
hr["cohort"] = [", ".join(name.get(m, m).split()[-1] for m in members[(pid, "HR")]) for pid in hr.index]
hr.index = [name.get(i, i) for i in hr.index]
print(f"\n=== batter HR: cohort size 145 PA, k = {ks['HR']:.0f} (old scheme k = {old_k:.0f}) ===")
top = hr.sort_values("HR", ascending=False).head(12)
print(top.round(2).to_string())
print("\nlowest-share batters with a home run:")
print(hr[hr["HR"] > 0].sort_values("team share %").head(5).round(2).drop(columns="cohort").to_string())


def spread(col):
    v = col.dropna()
    return f"min {v.min():.1f}  median {v.median():.1f}  max {v.max():.1f}  SD {v.std():.2f}  distinct at 1pp {int(v.round().nunique())}"
print(f"\nHR cards, all {len(hr)} batters (%):")
print(f"  cohort scheme: {spread(hr['card %'])}")
print(f"  old scheme:    {spread(hr['old card %'])}")
print(f"  raw:           {spread(hr['raw %'])}")
print(f"  total HR: actual {int(hr['HR'].sum())}, cohort cards {hr['card HR'].sum():.1f}, old cards {hr['old card HR'].sum():.1f}")

print("\nother batter lines: k around cohort targets:", {l: (round(v) if np.isfinite(v) else "inf") for l, v in ks.items()})
for line in ("K", "HBP", "1B"):
    oc, ok = half_scheme("B", line)
    print(f"  {line}: cohort {spread(100 * card[line])}\n       old    {spread(100 * oc)}")

# rank changes: PA order vs share order
rk = pd.DataFrame({"PA rank": n.rank(ascending=False, method="min"), "share rank": share.rank(ascending=False, method="min")})
rk["moved"] = rk["PA rank"] - rk["share rank"]
rk.index = [name.get(i, i) for i in rk.index]
print("\nbatters whose rank moves most from PA order to share order:")
print(rk.reindex(rk["moved"].abs().sort_values(ascending=False).index).head(6).astype(int).to_string())

# ---------------- pitchers ----------------
share, n, x, rate, target, card, ks, members, traded = cohort_cards("P", SIZES["P"])
print("\ntraded pitchers:", traded)
print("pitcher k around cohort targets:", {l: (round(v) if np.isfinite(v) else "inf") for l, v in ks.items()})
pt = pd.DataFrame({"team share %": 100 * share, "BF": n, "K raw %": 100 * rate["K"], "K target %": 100 * target["K"],
                   "K card %": 100 * card["K"], "BB raw %": 100 * rate["BB"], "BB target %": 100 * target["BB"],
                   "BB card %": 100 * card["BB"]})
pt.index = [name.get(i, i) for i in pt.index]
print(pt.sort_values("team share %", ascending=False).round(1).to_string())
