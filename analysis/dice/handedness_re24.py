"""Does handedness move RE24 -- the situational run value of a plate appearance?

    pixi run python analysis/dice/handedness_re24.py

The line-by-line test (handedness.py) asks eight noisy questions at once. RE24
asks one: how many runs did this plate appearance actually produce, counting the
base-out state it happened in. One number per plate appearance has far more power
than an eight-way distribution, so if a platoon effect is hiding anywhere it
should show here.

    RE24 = RE(state after) - RE(state before) + runs scored

Two confounds have to come out before the raw split means anything:

  situation   managers bring a same-handed reliever into tight spots, so the two
              groups may not sit in the same base-out states to begin with. The
              RE BEFORE the play is reported, and RE24 is also computed with each
              state's own mean removed.
  who bats    handedness is a property of players, and better players take more
              plate appearances. The context-neutral run value (the same outcomes
              priced by league linear weights, ignoring the situation) separates
              "this matchup produced more runs" from "these were better hitters".
"""
import numpy as np
import pandas as pd

from wpbl import markov, tables
from wpbl.batters import plate_appearances as bat_pa
from wpbl.dice import TO_LINE, plate_appearances

pd.set_option("display.width", 210)
RE = markov.run_expectancy()


def code(p):
    return "".join(c if isinstance(b, str) else "_" for c, b in
                   zip("123", (p.first_base, p.second_base, p.third_base)))


plays = tables.read("plays", "training").copy()
plays["half_key"] = list(zip(plays["game_id"], plays["inning"], plays["half"]))
stopped = {g: blk.sort_values("sequence")["half_key"].iloc[-1]
           for g, blk in plays.groupby("game_id")}
rows = []
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.sort_values("sequence").itertuples() if p.outs_before < 3]
    for i, p in enumerate(live):
        if p.play_kind != "plate_appearance":
            continue
        before = (code(p), int(p.outs_before))
        if i + 1 < len(live):
            nxt = live[i + 1]
            after = RE[(code(nxt), int(nxt.outs_before))]
        elif stopped.get(p.game_id) == key:
            continue                              # walk-off or called: censored
        else:
            after = 0.0                           # three outs
        rows.append({"game_id": p.game_id, "batter_id": p.batter_id,
                     "pitcher_id": p.pitcher_id, "event_type": p.event_type,
                     "state": before[0], "outs": before[1],
                     "re_before": RE[before],
                     "re24": after - RE[before] + float(p.runs_scored)})
d = pd.DataFrame(rows)

pa = plate_appearances()
pl = tables.read("players", "training")
person = pl.set_index("player_id")["person_id"].to_dict()
info = pl.drop_duplicates("person_id").set_index("person_id")
d["B"] = d["batter_id"].map(person).fillna(d["batter_id"])
d["P"] = d["pitcher_id"].map(person).fillna(d["pitcher_id"])
bats, throws = info["bats"].to_dict(), info["throws"].to_dict()


def side(b, t):
    if not isinstance(b, str) or not isinstance(t, str):
        return None
    if b.upper().startswith("S"):
        return "opposite"
    return "same" if b.upper()[0] == t.upper()[0] else "opposite"


d["side"] = [side(bats.get(b), throws.get(p)) for b, p in zip(d["B"], d["P"])]
d = d.dropna(subset=["side"])

# context-neutral value: the same outcome priced by league linear weights
lw = bat_pa("training").copy()
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
W = lw.groupby("line")["run_value"].mean()
d["line"] = [TO_LINE.get(e, "OUT") for e in d["event_type"]]
d["neutral"] = d["line"].map(W)
d["re24_adj"] = d["re24"] - d.groupby(["state", "outs"])["re24"].transform("mean")

g = pd.Series(pd.Categorical(d["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
draws = np.random.default_rng(20260922).integers(0, nG, size=(4000, nG))


def gap(col):
    """Same minus opposite, with a standard error from resampling whole games."""
    v = d[col].to_numpy(float)
    s = (d["side"] == "same").to_numpy()
    obs = v[s].mean() - v[~s].mean()
    out = []
    for row in draws:
        idx = np.concatenate([np.flatnonzero(g == k) for k in row[:60]])
        ss = s[idx]
        if ss.sum() and (~ss).sum():
            out.append(v[idx][ss].mean() - v[idx][~ss].mean())
    return obs, float(np.std(out))


print(f"{len(d)} plate appearances with both hands known "
      f"({int((d['side'] == 'same').sum())} same, {int((d['side'] == 'opposite').sum())} opposite)")
print("\n=== the confound: are the two groups in the same situations? ===")
print(d.groupby("side")["re_before"].agg(["size", "mean"]).round(4).to_string())
b, se = gap("re_before")
print(f"  run expectancy BEFORE the play, same - opposite: {b:+.4f} (SE {se:.4f}) "
      f"= {b/se:.2f} SE")

print("\n=== the tests ===")
for col, label in (("re24", "RE24 (situational)"),
                   ("re24_adj", "RE24, each base-out state's mean removed"),
                   ("neutral", "context-neutral run value")):
    b, se = gap(col)
    print(f"  {label:42s} same - opposite {b:+.4f} (SE {se:.4f}) = {b/se:+.2f} SE")
