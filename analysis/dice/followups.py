"""ROE leave-one-out, HR leaders raw vs smoothed, rates by PA quartile, tryout vs kept rates."""
import numpy as np
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
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs; PAs with no pitcher id: {int(pa['pitcher_id'].isna().sum())}")
L = pa["line"].value_counts(normalize=True).reindex(LINES)

x = pd.crosstab(pa["B"], pa["line"]).reindex(columns=LINES, fill_value=0)
n = x.sum(axis=1)
by_n = n.groupby(n).sum().sort_index()
u = n.map((by_n.cumsum() - by_n / 2) / by_n.sum())          # pooled-tie midpoint position
low = x[u < 0.5].sum() / n[u < 0.5].sum()
high = x[u >= 0.5].sum() / n[u >= 0.5].sum()
frac = ((u - 0.25) / 0.5).clip(0, 1)
target = pd.DataFrame(np.outer(1 - frac, low) + np.outer(frac, high), index=n.index, columns=LINES)
rate = x.div(n, axis=0)
qual = n >= 25


def real_share(line, keep):
    """Method of moments around each batter's target: share of observed spread that is real, and k."""
    t, r, m = target.loc[keep, line], rate.loc[keep, line], n[keep]
    obs = float(((r - t) ** 2).mean())
    noise = float((t * (1 - t) / m).mean())
    tau2 = obs - noise
    k = L[line] * (1 - L[line]) / tau2 if tau2 > 0 else np.inf
    return max(tau2, 0) / obs, k

# ---------------- ROE leave-one-out ----------------
share, k = real_share("ROE", qual)
print(f"\n=== batter ROE: {int(qual.sum())} batters with 25+ PA; real share of spread {share:.0%}, k = {k:.0f} ===")
loo = []
for pid in n[qual].index:
    keep = qual & (n.index != pid)
    s, kk = real_share("ROE", keep)
    loo.append({"removed": name.get(pid, pid), "PA": int(n[pid]), "ROE": int(x.loc[pid, "ROE"]),
                "real share without her": round(s, 2), "k without her": round(kk) if np.isfinite(kk) else np.inf})
loo = pd.DataFrame(loo).sort_values("real share without her")
print(loo.head(6).to_string(index=False))
print("  ...  largest share after removing anyone:", loo["real share without her"].max())
for line in ("HBP", "HR", "K", "1B"):                       # same test on the other batter entries, for scale
    s, kk = real_share(line, qual)
    worst = min(real_share(line, qual & (n.index != pid))[0] for pid in n[qual].index)
    print(f"  {line}: real share {s:.0%} (k {kk:.0f}); lowest after removing any one batter {worst:.0%}")

# ---------------- HR leaders ----------------
_, k_hr = real_share("HR", qual)
card = (x["HR"] + k_hr * target["HR"]) / (n + k_hr)
hr = pd.DataFrame({"PA": n, "HR": x["HR"], "raw %": 100 * rate["HR"], "target %": 100 * target["HR"],
                   "card %": 100 * card, "card HR over same PA": card * n})
hr.index = [name.get(i, i) for i in hr.index]
print(f"\n=== home-run leaders (k = {k_hr:.0f}; league {100 * L['HR']:.2f}%) ===")
print(hr.sort_values("HR", ascending=False).head(10).round(2).to_string())

# ---------------- rates by PA quartile ----------------
q = (u * 4).astype(int).clip(0, 3) + 1
tab = x.groupby(q).sum()
out = (100 * tab.div(tab.sum(axis=1), axis=0)).round(2)
out.insert(0, "PAs", tab.sum(axis=1))
out.insert(0, "batters", q.value_counts().sort_index())
out.index = [f"Q{i}" for i in out.index]
print("\n=== batter rates by PA quartile (%, full data) ===")
print(out.to_string())
lin = pd.DataFrame({f"Q{i}": 100 * ((1 - f) * low + f * high) for i, f in ((1, 0), (2, .25), (3, .75), (4, 1))}).T
print("\nwhat the current straight-line targets give at each quartile's middle (%):")
print(lin.round(2).to_string())

# ---------------- kept vs tryout pitchers ----------------
reg = tables.read("pitching", "default").groupby("person_id")["ip_outs"].sum()
kept = set(reg[reg >= 18].index)
pg = pa.dropna(subset=["pitcher_id"]).assign(grp=lambda d: np.where(d["P"].isin(kept), "kept", "tryout"))
t = pd.crosstab(pg["grp"], pg["line"]).reindex(columns=LINES, fill_value=0)
print("\n=== pitchers, full training data: counts and % ===")
print(t.assign(PAs=t.sum(axis=1)).to_string())
print((100 * t.div(t.sum(axis=1), axis=0)).round(2).to_string())
