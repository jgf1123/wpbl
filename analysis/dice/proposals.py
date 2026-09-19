"""A: batter PA quartiles and group means.  B: do F/FB/B (+) reproduce every out?"""
from collections import Counter
import pandas as pd
from wpbl import tables
from wpbl.batters import contact
from wpbl.run_expectancy import HALF_KEY, damaged_halves

pd.set_option("display.width", 220)
plays = tables.read("plays", "training").sort_values(["game_id", "sequence"])
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
line = tables.read("line_score", "training")
games = tables.read("games", "training").set_index("game_id")
print("training games", plays["game_id"].nunique())

# ---------------- A: quartiles of plate appearances --------------------------
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["o"] = [contact(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
pa["pid"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
OUTS = ["groundout", "flyout", "popup", "lineout", "foul_out", "out"]
b = pa.groupby("pid").agg(PA=("o", "size"),
                          K=("o", lambda s: (s == "strikeout").sum()),
                          HR=("o", lambda s: (s == "home_run").sum()),
                          HBP=("o", lambda s: (s == "hit_by_pitch").sum()),
                          single=("o", lambda s: (s == "single").sum()),
                          gb=("o", lambda s: (s == "groundout").sum()),
                          outs=("o", lambda s: s.isin(OUTS).sum())).sort_values("PA")
total = b["PA"].sum()
b["mid"] = (b["PA"].cumsum() - b["PA"] / 2) / total        # midpoint of her block of PAs
b["quartile"] = (b["mid"] * 4).astype(int).clip(0, 3) + 1
print(f"\n=== A. {len(b)} batters, {total} PAs ===")
q = b.groupby("quartile").agg(batters=("PA", "size"), PA=("PA", "sum"),
                              min_PA=("PA", "min"), max_PA=("PA", "max"))
print(q.to_string())
rows = []
for label, sel in (("low half (Q1-2)", b["quartile"] <= 2), ("high half (Q3-4)", b["quartile"] >= 3),
                   ("all", b["PA"] > 0)):
    g = b[sel]
    rows.append({"group": label, "batters": len(g), "PA": int(g["PA"].sum()),
                 **{c: round(100 * g[c].sum() / g["PA"].sum(), 2) for c in ("K", "HR", "HBP", "single")},
                 "gb share of outs": round(100 * g["gb"].sum() / g["outs"].sum(), 1)})
print(pd.DataFrame(rows).to_string(index=False))
print("\nbatters in Q2 and Q3 (the interpolated band):")
print(b[b["quartile"].isin([2, 3])][["PA", "mid", "quartile"]]
      .rename(index=name).round(3).to_string())

# ---------------- B: out types by base-out transition ------------------------
damaged = damaged_halves(plays, line, games)
plays["half_key"] = list(map(tuple, plays[HALF_KEY].values))
plays = plays[~plays["half_key"].isin(damaged)]
last_half = {g: blk["half_key"].iloc[-1] for g, blk in plays.groupby("game_id")}


def occ(p):
    return tuple(isinstance(x, str) for x in (p.first_base, p.second_base, p.third_base))


def move(bases, outs, batter_out, out_runner, plus):
    """Apply one proposed line. bases: (1st, 2nd, 3rd) occupied flags.
    out_runner: None, or the base (1/2/3) of the runner put out.
    Forced runners advance one; unforced runners advance only with plus.
    Returns (bases after, outs made, runs)."""
    on = [i + 1 for i in range(3) if bases[i]]
    forced = set()
    for base in (1, 2, 3):                       # forced = unbroken chain from 1st
        if base in on:
            forced.add(base)
        else:
            break
    batter_safe = not batter_out
    made = int(batter_out) + int(out_runner is not None)
    after, runs = set(), 0
    for base in sorted(on, reverse=True):
        if base == out_runner:
            continue
        step = 1 if (batter_safe and base in forced) or plus else 0
        dest = base + step
        if dest >= 4:
            runs += 1
        else:
            after.add(dest)
    if batter_safe:
        after.add(1)
    if outs + made >= 3:                         # inning over; runs on a force out don't count
        return None, 3 - outs, 0 if out_runner is not None or batter_out else runs
    return tuple(i in after for i in (1, 2, 3)), made, runs


def candidates(bases, outs, f_rule):
    on = [i + 1 for i in range(3) if bases[i]]
    force = bases[0]
    lead_forced = max(b for b in (1, 2, 3) if all(bases[:b])) if force else None
    f_out = (lead_forced if f_rule == "lead" else 1) if force else None
    out = {}
    for plus in (False, True):
        sfx = "+" if plus else ""
        out["B" + sfx] = move(bases, outs, True, None, plus)
        out["F" + sfx] = move(bases, outs, False, f_out, plus) if force else out["B" + sfx]
        out["FB" + sfx] = move(bases, outs, True, 1, plus) if force else out["B" + sfx]
    return out


obs = []
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for i, p in enumerate(live):
        if p.play_kind != "plate_appearance" or p.outs_before >= 2:
            continue
        if i + 1 < len(live):
            nxt = live[i + 1]
            after, made = occ(nxt), int(nxt.outs_before) - int(p.outs_before)
        elif last_half.get(p.game_id) == key:
            continue                              # game's last play: may be a walk-off
        else:
            after, made = None, 3 - int(p.outs_before)
        bases = occ(p)
        if made < 1 or not any(bases):
            continue
        runs = int(p.runs_scored)
        obs.append({"bases": "".join(c if f else "_" for c, f in zip("123", bases)),
                    "outs": int(p.outs_before), "made": made, "runs": runs,
                    "label": contact(p.event_type, p.narrative),
                    "actual": (after if made + p.outs_before < 3 else None, made,
                               runs if made + p.outs_before < 3 else 0),
                    "raw_runs": runs, "narr": p.narrative})
f = pd.DataFrame(obs)
print(f"\n=== B. {len(f)} PAs with runners on, <2 outs, at least one out made ===")
for rule in ("lead", "trail"):
    hits = Counter()
    miss = []
    for r in f.itertuples():
        cand = candidates(tuple(c != "_" for c in r.bases), r.outs, rule)
        matched = [k for k, v in cand.items() if v == r.actual]
        # ending-inning plays: compare outs only (runs on the final out rarely count)
        if r.actual[0] is None:
            matched = [k for k, v in cand.items() if v[0] is None]
        if matched:
            hits[min(matched, key=len)] += 1       # shortest name = simplest line that fits
        else:
            miss.append(r)
    print(f"\nF rule = {rule} forced runner out: reproduced {sum(hits.values())}, "
          f"not reproduced {len(miss)}; simplest line that fits: {dict(hits)}")
    if rule == "trail":
        m = pd.DataFrame(miss)
        if len(m):
            m["after"] = m["actual"].map(lambda a: "end" if a[0] is None
                                         else "".join(c if x else "_" for c, x in zip("123", a[0])))
            print(m.groupby(["bases", "outs", "made", "runs", "after"]).size()
                  .rename("n").sort_values(ascending=False).to_string())
            print("\nexamples:")
            for r in m.head(12).itertuples():
                print(f"  {r.bases} {r.outs} out -> {r.after} made {r.made} runs {r.runs} [{r.label}]: {str(r.narr)[:110]}")
