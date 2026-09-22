"""A round band plus a marked group: does two levels beat one flat rate?

    pixi run python analysis/dice/band_two_level.py

Doubles and errors are fixed league bands because neither has real spread on
either side. But 4.54% and 2.22% are awkward cells. The proposal: print 4% for
everyone, mark the players who hit the most doubles, and give the marked group
an extra point, choosing the group so the league total comes back to 4.54%.

That restores the round number and, if there is any real signal in who doubles,
recovers a little of it. If there is not -- line_owner.py put the batter's real
2B spread at exactly zero -- it sorts noise and should lose to the flat band.

The marked group is chosen INSIDE each build half and scored on the held-out
half, so the choice cannot see the games it is judged on. Variants with a bigger
bonus need a smaller group, so those are tried too.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import LINES, plate_appearances

pd.set_option("display.width", 240)
SPLITS = 20
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
gids = sorted(pa["game_id"].unique())
gcode = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = gcode.max() + 1

CASES = [("2B", "B", 0.04, [0.04, 0.05]), ("ROE", "P", 0.02, [0.02, 0.03])]
BONUS = [0.01, 0.02, 0.03]


def marked(train, line, side, base, bonus):
    """Top players by rate on the build half, until the bonus restores the league total."""
    x = pd.crosstab(train[side], train["line"]).reindex(columns=LINES, fill_value=0)
    n = x.sum(axis=1)
    lg = x[line].sum() / n.sum()
    need = max(lg - base, 0.0) / bonus              # share of PAs that must be marked
    rate = (x[line] + 1.0) / (n + 25.0)             # light shrink: 2B is thin
    order = rate.sort_values(ascending=False).index
    share, take = 0.0, []
    for pid in order:
        if share >= need:
            break
        take.append(pid)
        share += n[pid] / n.sum()
    return set(take), share, lg


rng = np.random.default_rng(20260921)
acc = {}
cnt = np.zeros(nG)
for line, side, base, flats in CASES:
    for name in ["flat measured"] + [f"flat {f:.0%}" for f in flats]             + [f"{base:.0%} + {b:.0%}" for b in BONUS]:
        acc[(line, name)] = np.zeros(nG)
info = {c[0]: [] for c in CASES}

for rep in range(SPLITS):
    half = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    side_of = pa["game_id"].map(half).to_numpy()
    for fold in (0, 1):
        tr, te = pa[side_of != fold], np.flatnonzero(side_of == fold)
        first = True
        for line, side, base, flats in CASES:
            lg = (tr["line"] == line).mean()
            hit = (pa["line"].iloc[te] == line).to_numpy().astype(float)
            gg = gcode[te]
            if first:
                np.add.at(cnt, gg, 1.0)
                first = False
            preds = {"flat measured": np.full(len(te), lg)}
            for f in flats:
                preds[f"flat {f:.0%}"] = np.full(len(te), f)
            for b in BONUS:
                take, share, _ = marked(tr, line, side, base, b)
                info[line].append((b, len(take), share))
                who = pa[side].iloc[te].isin(take).to_numpy()
                preds[f"{base:.0%} + {b:.0%}"] = np.where(who, base + b, base)
            for k, p in preds.items():
                p = np.clip(p, 1e-6, 1 - 1e-6)
                np.add.at(acc[(line, k)], gg, -(hit * np.log(p) + (1 - hit) * np.log(1 - p)))
    print(f"  split {rep + 1}/{SPLITS}", flush=True)

draws = np.random.default_rng(9).integers(0, nG, size=(3000, nG))
for line, side, base, flats in CASES:
    print(f"\n=== {line} ({'batters' if side == 'B' else 'pitchers'}) ===")
    for b in BONUS:
        rows_ = [r for r in info[line] if r[0] == b]
        print(f"  a +{b:.0%} bonus needs {np.mean([r[1] for r in rows_]):.0f} players "
              f"covering {100 * np.mean([r[2] for r in rows_]):.1f}% of plate appearances")
    base_key = (line, "flat measured")
    out = []
    for name in ["flat measured"] + [f"flat {f:.0%}" for f in flats]             + [f"{base:.0%} + {b:.0%}" for b in BONUS]:
        d = acc[(line, name)] - acc[base_key]
        bs = 1000 * d[draws].sum(axis=1) / cnt[draws].sum(axis=1)
        out.append({"band": name,
                    "log loss x1000": round(1000 * acc[(line, name)].sum() / cnt.sum(), 3),
                    "vs flat measured": f"{1000 * d.sum() / cnt.sum():+.3f} (SE {bs.std():.3f})"})
    print(pd.DataFrame(out).to_string(index=False))
