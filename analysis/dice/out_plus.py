"""Do batters differ in how often their outs advance a runner (the + modifier)?"""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("out_plus.py", "proposals.py")
SRC = open(_here.replace("out_plus.py", "proposals.py"), encoding="utf-8").read()
head = SRC[:SRC.index("# ---------------- A: quartiles")]
start = SRC.index("# ---------------- B: out types by base-out transition")
body = SRC[start:SRC.index("obs = []")]
exec(head + body)
__file__ = _here
pd.set_option("display.width", 220)
rng = np.random.default_rng(20260919)

rows = []
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for i, p in enumerate(live):
        if p.play_kind != "plate_appearance" or p.outs_before >= 2:
            continue
        if i + 1 < len(live):
            nxt = live[i + 1]
            after, made = occ(nxt), int(nxt.outs_before) - int(p.outs_before)
        elif last_half.get(p.game_id) == key:
            continue
        else:
            after, made = None, 3 - int(p.outs_before)
        bases = occ(p)
        if made < 1 or not any(bases):
            continue
        runs = int(p.runs_scored)
        actual = (after if made + p.outs_before < 3 else None, made,
                  runs if made + p.outs_before < 3 else 0)
        cand = candidates(bases, int(p.outs_before), "trail")
        if actual[0] is None:
            match = [k for k, v in cand.items() if v[0] is None]
        else:
            match = [k for k, v in cand.items() if v == actual]
        # Did a runner advance? Read it off the transition, not the line name: with a
        # runner on 1st only, B (batter out, runner holds) and F+ (runner forced out,
        # batter safe) leave the same state, so a name would call a held runner "+".
        if actual[0] is None or not match:
            plus = np.nan                      # inning ended: the feed never shows the bases
        else:
            plus = 0 if any(not k.endswith("+") for k in match) else 1
        rows.append({"B": person.get(p.batter_id, p.batter_id), "game": p.game_id,
                     "bases": "".join(c if f else "_" for c, f in zip("123", bases)),
                     "outs": int(p.outs_before), "made": made,
                     "label": contact(p.event_type, p.narrative),
                     "state": "".join(c if f else "_" for c, f in zip("123", bases)) + f"/{int(p.outs_before)}",
                     "plus": plus, "ended": actual[0] is None,
                     "unmatched": len(match) == 0})
t = pd.DataFrame(rows)
print(f"=== {len(t)} PAs: runner on, <2 outs, an out made ({plays['game_id'].nunique()} games) ===")
print("  unmatched by any B/F/FB line:", int(t["unmatched"].sum()),
      "| inning ended, bases never shown:", int(t["ended"].sum()))
IN_PLAY = ["groundout", "flyout", "popup", "lineout", "foul_out", "out"]
d = t[t["plus"].notna() & t["label"].isin(IN_PLAY)].copy()
print(f"  determinate: {len(d)} PAs, {d['plus'].mean():.1%} carry +, {d['B'].nunique()} batters")
print("\nby situation (+ rate):")
s = d.groupby("state").agg(n=("plus", "size"), plus=("plus", "sum"))
s["rate"] = (s["plus"] / s["n"]).round(3)
print(s.sort_values("n", ascending=False).to_string())
print("\nby label (+ rate):")
lb = d.groupby("label").agg(n=("plus", "size"), plus=("plus", "sum"))
lb["rate"] = (lb["plus"] / lb["n"]).round(3)
print(lb.sort_values("n", ascending=False).to_string())

# ---- expectation matched to the situations each batter actually faced ----
KS = 10.0
L = d["plus"].mean()
srate = (s["plus"] + KS * L) / (s["n"] + KS)          # league + rate per base-out state, smoothed
d["exp"] = d["state"].map(srate)
g = d.groupby("B").agg(n=("plus", "size"), plus=("plus", "sum"), exp=("exp", "sum"))
g["rate"], g["exp_rate"] = g["plus"] / g["n"], g["exp"] / g["n"]
g["diff"] = g["rate"] - g["exp_rate"]
q = g[g["n"] >= 8]
print(f"\n=== {len(q)} batters with 8+ such PAs ({int(q['n'].sum())} PAs) ===")
print(q.assign(name=[name.get(i, i) for i in q.index]).sort_values("diff")
       .round(3).to_string(index=False,
       columns=["name", "n", "plus", "rate", "exp_rate", "diff"]))


def tau2(sub):
    """Method of moments: spread of true + rates left after sampling noise."""
    obs = float((sub["diff"] ** 2).mean())
    noise = float((sub["exp_rate"] * (1 - sub["exp_rate"]) / sub["n"]).mean())
    return obs - noise, obs, noise


tt, obs, noise = tau2(q)
boots = [tau2(q.iloc[rng.integers(0, len(q), len(q))])[0] for _ in range(4000)]
lo, hi = np.percentile(boots, [5, 95])
print(f"\nobserved spread (SD) {np.sqrt(obs):.3f}; expected from chance alone {np.sqrt(noise):.3f}")
print(f"real spread (SD) {np.sqrt(max(tt,0)):.3f}, 90% interval "
      f"{np.sqrt(max(lo,0)):.3f} to {np.sqrt(max(hi,0)):.3f}; real share of spread {max(tt,0)/obs:.0%}")
chi = float((((q['plus'] - q['exp']) ** 2) / (q['n'] * q['exp_rate'] * (1 - q['exp_rate']))).sum())
print(f"chi-square {chi:.1f} on ~{len(q)} batters (equal skill predicts about {len(q)})")

# ---- split-half: does a batter's + rate in one half of the games predict the other? ----
gids = sorted(d["game"].unique())
half = {gid: i % 2 for i, gid in enumerate(gids)}
d["half"] = d["game"].map(half)
sh = d.pivot_table(index="B", columns="half", values="plus", aggfunc=["size", "mean"])
sh.columns = ["n0", "n1", "r0", "r1"]
sh = sh[(sh["n0"] >= 5) & (sh["n1"] >= 5)]
print(f"\nsplit-half (alternating games): {len(sh)} batters with 5+ in each half, "
      f"correlation {sh['r0'].corr(sh['r1']):+.2f}")


# ---- B: the + rate implied by each batter's out-type mix, over all her outs ----
w = lb["rate"].reindex(IN_PLAY).fillna(L)            # league + rate per out label
pa_all = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa_all["label"] = [contact(e, n) for e, n in zip(pa_all["event_type"], pa_all["narrative"])]
pa_all["B"] = pa_all["batter_id"].map(person).fillna(pa_all["batter_id"])
pa_all["game"] = pa_all["game_id"]
o = pa_all[pa_all["label"].isin(IN_PLAY)]
X = pd.crosstab(o["B"], o["label"]).reindex(columns=IN_PLAY, fill_value=0)
N = X.sum(axis=1)
P = X.div(N, axis=0)
imp = P @ w
lg = (X.sum() / X.sum().sum()) @ w
qq = N >= 25
print(f"\n=== B. {int(qq.sum())} batters with 25+ in-play outs ({int(N[qq].sum())} outs); "
      f"league + rate {lg:.1%} ===")
tab = pd.DataFrame({"name": [name.get(i, i) for i in N.index], "outs": N,
                    "gb%": (100 * P["groundout"]).round(1),
                    "air%": (100 * P[["flyout", "popup", "lineout", "foul_out"]].sum(axis=1)).round(1),
                    "implied +": (100 * imp).round(1)})[qq].sort_values("implied +")
print(pd.concat([tab.head(5), tab.tail(5)]).to_string(index=False))


def spread(mask):
    Pq, Nq = P[mask].values, N[mask].values
    m = (Pq @ w.values)
    obs = float(((m - lg) ** 2).mean())
    noise = float(np.mean([(p @ (w.values ** 2) - (p @ w.values) ** 2) / n for p, n in zip(Pq, Nq)]))
    return obs - noise, obs, noise


tt2, obs2, noise2 = spread(qq)
bt = []
idx = np.where(qq.values)[0]
for _ in range(4000):
    take = rng.integers(0, len(idx), len(idx))
    Pq, Nq = P.values[idx[take]], N.values[idx[take]]
    m = Pq @ w.values
    o_ = float(((m - lg) ** 2).mean())
    nz = float(np.mean([(p @ (w.values ** 2) - (p @ w.values) ** 2) / n for p, n in zip(Pq, Nq)]))
    bt.append(o_ - nz)
lo2, hi2 = np.percentile(bt, [5, 95])
print(f"spread of implied + rate: observed SD {np.sqrt(obs2):.3f}, chance alone {np.sqrt(noise2):.3f}")
print(f"real SD {np.sqrt(max(tt2,0)):.3f} (90% {np.sqrt(max(lo2,0)):.3f} to {np.sqrt(max(hi2,0)):.3f}), "
      f"real share {max(tt2,0)/obs2:.0%}")
half2 = {gid: i % 2 for i, gid in enumerate(sorted(o["game"].unique()))}
o = o.assign(h=o["game"].map(half2))
sp = []
for h in (0, 1):
    Xi = pd.crosstab(o[o["h"] == h]["B"], o[o["h"] == h]["label"]).reindex(columns=IN_PLAY, fill_value=0)
    Ni = Xi.sum(axis=1)
    sp.append(pd.DataFrame({"n": Ni, "r": (Xi.div(Ni, axis=0) @ w)}))
j = sp[0].join(sp[1], lsuffix="0", rsuffix="1").dropna()
j = j[(j["n0"] >= 12) & (j["n1"] >= 12)]
print(f"split-half of implied + rate: {len(j)} batters, correlation {j['r0'].corr(j['r1']):+.2f}")


# ---- C: the ground-ball share itself, and what a + is worth in runs ----
gb = X["groundout"][qq]
ng = N[qq]
rg = gb / ng
lgb = float(gb.sum() / ng.sum())
obs3 = float(((rg - lgb) ** 2).mean())
noise3 = float((lgb * (1 - lgb) / ng).mean())
b3 = []
for _ in range(4000):
    i = rng.integers(0, len(rg), len(rg))
    b3.append(float(((rg.values[i] - lgb) ** 2).mean()) - float(np.mean(lgb * (1 - lgb) / ng.values[i])))
l3, h3 = np.percentile(b3, [5, 95])
print(f"\n=== C. ground-ball share of in-play outs: league {lgb:.1%} ===")
print(f"observed SD {np.sqrt(obs3):.3f}, chance alone {np.sqrt(noise3):.3f}, "
      f"real SD {np.sqrt(max(obs3-noise3,0)):.3f} (90% {np.sqrt(max(l3,0)):.3f} to {np.sqrt(max(h3,0)):.3f})")

from wpbl.run_expectancy import states, BASE_ORDER
re_frame = states()
RE = re_frame.pivot_table(index="bases", columns="outs", values="runs_rest", aggfunc="mean")


def value(v):
    """Run value of a resulting state: runs now, plus what the next state is worth."""
    after, made, runs = v
    if after is None:
        return runs
    code = "".join(c if x else "_" for c, x in zip("123", after))
    outs = made  # outs after the play, within this comparison both candidates match
    return runs + (RE.loc[code, outs] if outs < 3 else 0)


prices = []
for r in d.itertuples():
    cand = candidates(tuple(c != "_" for c in r.bases), r.outs, "trail")
    for fam in ("B", "F", "FB"):
        a, bpl = cand.get(fam), cand.get(fam + "+")
        if a is None or bpl is None or a[1] != bpl[1] or a[0] is None or bpl[0] is None:
            continue
        o_after = r.outs + a[1]
        if o_after >= 3:
            continue
        va = a[2] + RE.loc["".join(c if x else "_" for c, x in zip("123", a[0])), o_after]
        vb = bpl[2] + RE.loc["".join(c if x else "_" for c, x in zip("123", bpl[0])), o_after]
        prices.append(vb - va)
        break
price = float(np.mean(prices))
opp = t[t["B"].isin(N[qq].index)].groupby("B").size().mean()
print(f"\na + is worth {price:.3f} runs on average ({len(prices)} priced opportunities)")
print(f"opportunities per batter over the training games: {opp:.1f} "
      f"(runner-on, <2-out, out-made PAs, averaged over the {int(qq.sum())} qualified batters)")
print(f"a real SD of {np.sqrt(max(tt2,0)):.3f} in + rate is worth "
      f"{np.sqrt(max(tt2,0)) * price * opp:+.2f} runs per batter per season "
      f"(top of the 90% interval: {np.sqrt(max(hi2,0)) * price * opp:+.2f})")
