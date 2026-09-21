"""What die resolves the out flavors without costing runs?

    pixi run python analysis/dice/out_quantize.py

The flavor only matters through what it does to the runners, so the test is the
user's: does the quantized table give the same expected runs as the measured
one? For each base-out state, each flavor's value is the runs it scores plus the
run expectancy of the state it leaves. Those are averaged over the states that
actually occur, separately for "no runner on 1st" and "runner on 1st", because
a force is what makes F and FB possible at all.

Then every allocation of N cells over the six flavors is searched for the one
whose expected runs land closest to the measured distribution. N = 10 (d10),
12 (d12) and 20 (d20) are compared, per base state and pooled.
"""
from itertools import product

import numpy as np
import pandas as pd

_here = __file__
__file__ = _here.replace("out_quantize.py", "proposals.py")
SRC = open(__file__, encoding="utf-8").read()
head = SRC[:SRC.index("# ---------------- A: quartiles")]
start = SRC.index("# ---------------- B: out types by base-out transition")
exec(head + SRC[start:SRC.index("obs = []")])          # loaders, occ(), move(), candidates()
__file__ = _here
from wpbl.run_expectancy import states                                  # noqa: E402

pd.set_option("display.width", 220)
FLAVORS = ["B", "B+", "F", "F+", "FB", "FB+"]
OUT_EVENTS = {"groundout", "flyout", "popup", "lineout", "foul_out", "sacrifice",
              "fielders_choice", "out"}
RE = states().pivot_table(index="bases", columns="outs", values="runs_rest", aggfunc="mean")

# ---- measured distribution, from out_flavors.py: family by label, + within family ----
FAMILY = {False: {"B": .964, "F": .009, "FB": .027},          # no runner on 1st
          True: {"B": .635, "F": .191, "FB": .174}}           # runner on 1st
PLUS = {"B": .371, "F": .500, "FB": .818}                     # F and FB rest on 2 and 11 plays
TRUE = {}
for force, fam in FAMILY.items():
    TRUE[force] = {f + ("+" if p else ""): fam[f] * (PLUS[f] if p else 1 - PLUS[f])
                   for f in fam for p in (0, 1)}

# ---- how often each base-out state carries an out, by force ----
seen = Counter()
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for p in live:
        if p.play_kind != "plate_appearance" or p.outs_before >= 2:
            continue
        if p.event_type not in OUT_EVENTS:
            continue
        bases = occ(p)
        if any(bases):
            seen[(bases, int(p.outs_before))] += 1


def value(v):
    """Runs on the play plus what the state it leaves is worth."""
    after, made, runs = v
    if after is None:
        return float(runs)
    code = "".join(c if x else "_" for c, x in zip("123", after))
    return float(runs) + (float(RE.loc[code, made]) if made < 3 else 0.0)


# ---- expected runs per flavor, averaged over the states that occur ----
val = {False: {}, True: {}}
for force in (False, True):
    tot = sum(c for (b, o), c in seen.items() if b[0] == force)
    for f in FLAVORS:
        s = 0.0
        for (bases, outs), c in seen.items():
            if bases[0] != force:
                continue
            cand = candidates(bases, outs, "trail")
            s += c * value(cand[f])
        val[force][f] = s / tot
    print(f"\nrunner on 1st = {force}: {tot} out plays")
    print("  run value of each flavor: " +
          ", ".join(f"{f} {val[force][f]:.3f}" for f in FLAVORS))
    print("  measured mix: " + ", ".join(f"{f} {100 * TRUE[force][f]:.1f}%" for f in FLAVORS))
    print(f"  expected runs, measured mix: "
          f"{sum(TRUE[force][f] * val[force][f] for f in FLAVORS):.4f}")

# ---- best allocation of N cells ----
def compositions(n, k):
    if k == 1:
        yield (n,)
        return
    for i in range(n + 1):
        for rest in compositions(n - i, k - 1):
            yield (i,) + rest


# Expected runs alone leaves five degrees of freedom, and a search on it will
# happily return a table that matches the run total while looking nothing like
# the season. So the objective is distribution fidelity, with the run error
# reported alongside and used only to break ties.
print("\n=== best allocation of N cells: closest distribution, runs as tie-break ===")
weight = {force: sum(c for (b, o), c in seen.items() if b[0] == force) for force in (False, True)}
rows = []
for N in (6, 10, 12, 20):
    for force in (False, True):
        target = sum(TRUE[force][f] * val[force][f] for f in FLAVORS)
        pick, score = None, (1e9, 1e9)
        for comp in compositions(N, 6):
            q = [c / N for c in comp]
            dist = sum(abs(a - TRUE[force][f]) for a, f in zip(q, FLAVORS))
            runs = abs(sum(a * val[force][f] for a, f in zip(q, FLAVORS)) - target)
            if (round(dist, 9), round(runs, 9)) < score:
                pick, score = comp, (round(dist, 9), round(runs, 9))
        rows.append({"die": f"d{N}", "runner on 1st": force,
                     "B/B+/F/F+/FB/FB+": "/".join(map(str, pick)),
                     "total |dp|": round(score[0], 3),
                     "runs error per out": round(score[1], 4),
                     "runs per game": round(score[1] * weight[force]
                                            / plays["game_id"].nunique() / 2, 3)})
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== without a force, the six flavors are three duplicates of two ===")
print("F and FB act as B when nobody is on 1st, so only the + matters there.")
p_plus = sum(TRUE[False][f] for f in FLAVORS if f.endswith("+"))
for N in (6, 10, 12, 20):
    k = round(p_plus * N)
    gap = abs(k / N - p_plus)
    print(f"  d{N}: + on {k} of {N} = {100 * k / N:.1f}% against {100 * p_plus:.1f}% measured; "
          f"{gap * (val[False]['B+'] - val[False]['B']):.4f} runs per out play")
