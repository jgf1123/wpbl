"""League rates for the six out flavors: B, B+, F, F+, FB, FB+.

    pixi run python analysis/dice/out_flavors.py

The family comes from the feed's own label and the number of outs, not from
guessing at the base-out change:

    FB  two outs made          (the batter and a runner)
    F   one out, fielder's choice   (a runner out, the batter safe)
    B   one out, any other out label (the batter out)

Only the + is read off the transition: did a runner reach a base that the
family alone does not put her on. Inferring the family from the transition
instead leaves two thirds of plays ambiguous -- with a runner on 1st, "batter
out, runner holds" and "runner forced, batter safe" are the same state -- and a
tie-break then decides the rates, which is not a measurement.

Plays whose inning ended are dropped from the + rate: the feed never shows the
bases after the third out, so the + is unknowable there.
"""
import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("out_flavors.py", "proposals.py")
SRC = open(__file__, encoding="utf-8").read()
head = SRC[:SRC.index("# ---------------- A: quartiles")]
start = SRC.index("# ---------------- B: out types by base-out transition")
exec(head + SRC[start:SRC.index("obs = []")])          # loaders, occ(), move(), candidates()
__file__ = _here
pd.set_option("display.width", 220)
FLAVORS = ["B", "B+", "F", "F+", "FB", "FB+"]
OUT_EVENTS = {"groundout", "flyout", "popup", "lineout", "foul_out", "sacrifice",
              "fielders_choice", "out"}

rows = []
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for i, p in enumerate(live):
        if p.play_kind != "plate_appearance" or p.outs_before >= 2:
            continue
        if p.event_type not in OUT_EVENTS:
            continue
        bases = occ(p)
        if not any(bases):
            continue                       # bases empty: every flavor is the same
        if i + 1 < len(live):
            nxt = live[i + 1]
            after, made = occ(nxt), int(nxt.outs_before) - int(p.outs_before)
        elif last_half.get(p.game_id) == key:
            continue
        else:
            after, made = None, 3 - int(p.outs_before)
        if made < 1:
            continue
        family = "FB" if made >= 2 else ("F" if p.event_type == "fielders_choice" else "B")
        actual = (after if made + p.outs_before < 3 else None, made,
                  int(p.runs_scored) if made + p.outs_before < 3 else 0)
        cand = candidates(bases, int(p.outs_before), "trail")
        plus = np.nan                          # unknowable, or the family does not fit
        if actual[0] is not None and family in cand and family + "+" in cand:
            bare, with_plus = cand[family], cand[family + "+"]
            if bare == with_plus:
                plus = np.nan                  # the + changes nothing visible here
            elif actual == with_plus:
                plus = 1
            elif actual == bare:
                plus = 0
        rows.append({"B": person.get(p.batter_id, p.batter_id), "label": p.event_type,
                     "bases": "".join(c if f else "_" for c, f in zip("123", bases)),
                     "outs": int(p.outs_before), "family": family, "plus": plus,
                     "force": bases[0], "ended": after is None})
t = pd.DataFrame(rows)
print(f"{len(t)} out plays with runners on and <2 outs ({plays['game_id'].nunique()} games)")
print("\n=== family, from the feed's label (no inference) ===")
fam = t["family"].value_counts().reindex(["B", "F", "FB"])
print(pd.DataFrame({"plays": fam, "% of outs with runners on": (100 * fam / len(t)).round(1)}).to_string())

vis = t[t["plus"].notna()]
print(f"\n=== the + , on the {len(vis)} plays whose inning continued "
      f"({int(t['ended'].sum())} dropped: bases never shown) ===")
g = vis.groupby("family")["plus"].agg(["size", "sum", "mean"])
g.columns = ["plays", "with +", "+ rate"]
print(g.reindex(["B", "F", "FB"]).round(3).to_string())

print("\n=== the six flavors: family share x the + rate inside that family ===")
fam_share = fam / len(t)
plus_rate = vis.groupby("family")["plus"].mean()
out = pd.DataFrame({
    "family %": (100 * fam_share).round(1),
    "+ rate": plus_rate.round(3),
    "+ visible on": vis.groupby("family")["plus"].size(),
    "flavor %": (100 * fam_share * (1 - plus_rate)).round(1),
    "flavor+ %": (100 * fam_share * plus_rate).round(1)}).reindex(["B", "F", "FB"])
print(out.to_string())
print("  The family share is solid: the feed's label decides it. The + rate is not,")
print("  for F and FB -- those rest on a handful of plays, because with a runner")
print("  forced out the + usually changes nothing visible.")
fp = vis[vis["family"].isin(["F", "FB"])]
print(f"  So F and FB are POOLED: {int(fp['plus'].sum())} of {len(fp)} = "
      f"{fp['plus'].mean():.3f}. An F is a double-play attempt whose relay did not")
print("  retire the batter, so the other runners do the same thing on both.")

print("\n=== family by whether a force at 1st was on ===")
for force, grp in t.groupby("force"):
    v = grp["family"].value_counts()
    print(f"  runner on 1st = {bool(force)} ({len(grp)} plays): " +
          ", ".join(f"{k} {100 * c / len(grp):.1f}%" for k, c in v.items()))

# ---------------- (b) is any batter's family mix real? ----------------
print("\n=== does a batter's B / F / FB mix differ for real? ===")
X = pd.crosstab(t["B"], t["family"]).reindex(columns=["B", "F", "FB"], fill_value=0)
n = X.sum(axis=1)
keep = n >= 8
Xq, nq = X[keep].to_numpy().astype(float), n[keep].to_numpy().astype(float)
L = Xq.sum(axis=0) / Xq.sum()
R = Xq / nq[:, None]
print(f"  {int(keep.sum())} batters with 8+ such outs ({int(nq.sum())} plays); "
      f"league mix B {100 * L[0]:.1f}% F {100 * L[1]:.1f}% FB {100 * L[2]:.1f}%")
rng = np.random.default_rng(20260920)
for j, fam_ in enumerate(["B", "F", "FB"]):
    obs = float(((R[:, j] - L[j]) ** 2).mean())
    noise = float((L[j] * (1 - L[j]) / nq).mean())
    boots = []
    for _ in range(4000):
        i = rng.integers(0, len(nq), len(nq))
        boots.append(float(((R[i, j] - L[j]) ** 2).mean())
                     - float(np.mean(L[j] * (1 - L[j]) / nq[i])))
    lo, hi = np.percentile(boots, [5, 95])
    print(f"  {fam_:3s} observed SD {100 * np.sqrt(obs):4.1f}, chance alone {100 * np.sqrt(noise):4.1f}, "
          f"real SD {100 * np.sqrt(max(obs - noise, 0)):4.1f} "
          f"(90% {100 * np.sqrt(max(lo, 0)):.1f} to {100 * np.sqrt(max(hi, 0)):.1f})")

# ---- raw, unquantized: the die mechanic is not decided yet ----
from wpbl.dice import OUT_DIR                                          # noqa: E402
OUT_DIR.mkdir(parents=True, exist_ok=True)
raw = []
for force, grp in t.groupby("force"):
    fam_g = grp["family"].value_counts()
    vis_g = grp[grp["plus"].notna()]
    for f in ["B", "F", "FB"]:
        share_f = fam_g.get(f, 0) / len(grp)
        # F and FB share one + rate: an F is a double-play attempt whose relay did
        # not retire the batter (45 of 56 read "out at second", none mentions 1b),
        # so the other runners do the same thing on both. Measured apart they are
        # 1 of 2 and 9 of 11 -- no evidence of a difference -- and pooling puts the
        # rate on 13 plays instead of 2. DECISION (user, 21 Sep).
        sub = vis_g[vis_g["family"].isin(["F", "FB"]) if f in ("F", "FB")
                    else vis_g["family"] == f]
        pr = float(sub["plus"].mean()) if len(sub) else np.nan
        raw.append({"runner on 1st": bool(force), "family": f,
                    "family share": round(share_f, 5), "plays": int(fam_g.get(f, 0)),
                    "plus rate": None if np.isnan(pr) else round(pr, 5),
                    "plus visible on": len(sub),
                    "flavor share": None if np.isnan(pr) else round(share_f * (1 - pr), 5),
                    "flavor+ share": None if np.isnan(pr) else round(share_f * pr, 5)})
out_csv = OUT_DIR / "out_flavors.csv"
HEADER = [
    "# Out flavours, measured and UNROUNDED. No die mechanic is chosen yet, so",
    "# nothing here is quantized; analysis/dice/out_quantize.py has what a",
    "# d6/d10/d12/d20 table would cost in runs.",
    "# Family comes from the feed's label (fielder's choice, double play); only",
    "# the + is inferred from the base-out change.",
    "# With nobody on 1st, F and FB act as B, so only the + matters there.",
    "# F and FB share one + rate, pooled: an F is a double-play attempt whose",
    "# relay did not get the batter, so the runners behave the same on both.",
    "# That rate still rests on 13 plays -- see plus visible on.",
]
NL = chr(10)
with out_csv.open("w", encoding="utf-8", newline="") as fh:
    fh.write(NL.join(HEADER) + NL)
    pd.DataFrame(raw).to_csv(fh, index=False, lineterminator=NL)
print(NL + f"raw probabilities -> {out_csv}")
