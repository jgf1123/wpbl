"""Can a "must attempt" success rate be estimated, and is it a distinct thing?

    pixi run python analysis/dice/must_attempt.py

stolen_base_spec.md section 10 proposes a third manager option. Red-light, and she
never goes. Green-light, and she goes when a pitch worth going on arrives, which is
q = 0.041 a pitch stealing second. Must-attempt, and she goes whether or not one
arrives -- so she runs on an average pitch rather than a chosen one, and should be
caught more often. The spec notes no estimate exists for it. This is why.

**It is a counterfactual, not an unmeasured quantity.** Every one of the 133
attempts on record is one somebody chose to make. Three are pickoffs, where the
pitcher caught her leaning before she had committed, and that is the closest the
feed comes to a steal nobody elected. There is no forced attempt to measure.

**And it is not identified.** Writing S for her chance of being safe on a given
takeable pitch and q for the share of pitches she goes on,

    mu = q * E[S | she went] + (1 - q) * E[S | she stayed]

Everything is known except E[S | she stayed], which is the whole point: those are
the pitches she declined. Bounding it by [0, E[S | went]] leaves mu anywhere in
[0.04, 0.89]. Recovering it needs something that shifts whether she goes without
shifting whether she would be safe, and steal_decision.py already established there
is no such thing here -- the inning and the score move the attempt rate by 1.1 SE
and 0.03 SE.

**What can be tested is the gradient mu sits at the bottom of.** If she goes on the
best pitch available, then wherever she goes MORE often she is reaching further down
the pitch-quality distribution, and success should FALL as the hazard rises. A
must-attempt is the limit of that: the hazard goes to 1 and she takes whatever comes.
Three ways of looking, spanning an eleven-fold range of hazard across base states and
a four-fold range of attempt rate across runners, all give nothing or a small
POSITIVE number. Under the selection model that says the pitches she passes up are
about as good as the ones she takes, and a must-attempt would convert at close to the
ordinary rate.

Two cautions against reading that as settled:

  The cross-state hazards may be about how attractive the situation is rather than
  how picky she is. First-and-third runs at eight times the rate of first-and-second
  partly because the catcher risks the runner on third, not because runners relax
  their standard there. So that comparison is not a clean test of pickiness.

  Pickiness itself is untestable here. Which pitch she went on is unknowable (130 of
  133 attempts have an empty pitch string), and the per-pitch hazard is equally well
  explained by EXPOSURE -- more takeable pitches, more chances for a steal to be
  filed -- as by a runner holding out for a good one. Section 10's "the data supports
  that runners can identify good opportunities" is stronger than the evidence.

So a must-attempt penalty would be a design choice, in the same way the gassed
column is: reasonable, directionally defensible, and not a measurement. It should be
labelled that way if it ships.
"""

from __future__ import annotations

import importlib
import sys

import numpy as np
import pandas as pd

from wpbl import tables

sys.path.insert(0, "analysis/dice")
sp = importlib.import_module("steal_pitches")
sl = importlib.import_module("steals")

pd.set_option("display.width", 200)
MIN_OPP, MIN_ATT = 10, 3        # enough to place a runner on the gradient


def weighted_corr(x, y, w) -> float:
    c = np.cov(x, y, aweights=w)[0, 1]
    return float(c / np.sqrt(np.cov(x, x, aweights=w)[0, 1] * np.cov(y, y, aweights=w)[0, 1]))


def does_it_exist(d, censored) -> None:
    print("=== 1. is any attempt on record one she did not choose? ===")
    both = pd.concat([d[d.attempt][["pickoff", "ok"]], censored[["pickoff", "ok"]]],
                     ignore_index=True)
    print(f"  attempts inside a finished plate appearance    {int(d.attempt.sum())}")
    print(f"  attempts whose plate appearance never finished  {len(censored)}")
    print(f"  of all {len(both)}, pickoffs                          "
          f"{int(both.pickoff.sum())}")
    print("  A pickoff is the pitcher catching her leaning, so she had not")
    print("  committed. Nothing else marks an attempt as forced: no count, no")
    print("  sign, no pitch. A must-attempt has never happened.")


def bounds(d) -> None:
    print("\n=== 2. what selection bounds the rate to ===")
    print("      mu = q * E[S | went] + (1 - q) * E[S | stayed]")
    for target, lab in (("2nd", "stealing 2nd"), ("3rd", "stealing 3rd")):
        sub = d[(d.target == target) & (d.n >= 1)]
        q = sp.fit_q(sub.n.to_numpy(float), sub.attempt.to_numpy(float))
        a = sub[sub.attempt]
        obs = float(a.ok.mean())
        print(f"  {lab}: q = {q:.4f}, E[S | went] = {obs:.3f} on {len(a)} attempts"
              f"  ->  mu in [{q * obs:.3f}, {obs:.3f}]")
    print("  E[S | stayed] is the pitches she declined, so the interval is the whole")
    print("  range. NOT IDENTIFIED, and there is no instrument to fix that.")


def gradient(d, censored) -> None:
    print("\n=== 3. does success fall where she goes more often? ===")
    rows = []
    for state, g in d[d.n >= 1].groupby("state"):
        if g.attempt.sum() < 5:
            continue
        q = sp.fit_q(g.n.to_numpy(float), g.attempt.to_numpy(float))
        a = g[g.attempt]
        cen = censored[censored.state == state]
        ok = int(a.ok.sum()) + int(cen.ok.sum())
        n = len(a) + len(cen)
        rows.append({"state": state, "target": a.target.iloc[0], "hazard": round(q, 4),
                     "att": n, "ok": ok, "success": round(ok / n, 3)})
    t = pd.DataFrame(rows).sort_values("hazard")
    print("\n  by base state (hazard spans %.0fx):" % (t.hazard.max() / t.hazard.min()))
    print(t.to_string(index=False))
    print(f"  weighted corr(hazard, success) = "
          f"{weighted_corr(t.hazard, t.success, t.att.to_numpy(float)):+.2f}")

    cum = t.att.cumsum()
    lo, hi = t[cum <= cum.iloc[-1] / 2], t[cum > cum.iloc[-1] / 2]
    pa_, pb = lo.ok.sum() / lo.att.sum(), hi.ok.sum() / hi.att.sum()
    se = np.sqrt(pa_ * (1 - pa_) / lo.att.sum() + pb * (1 - pb) / hi.att.sum())
    print(f"  pooled: low-hazard states {list(lo.state)} {pa_:.3f}, "
          f"high {list(hi.state)} {pb:.3f}")
    print(f"  high minus low {pb - pa_:+.3f} (SE {se:.3f}) = {(pb - pa_) / se:+.2f} SE"
          f"   -- selection predicts NEGATIVE")

    ch = sl.runner_chances(tables.read("plays", "training"))
    for label, sub in (("stealing 2nd", ch[ch.target == "2nd"]), ("either base", ch)):
        g = sub.groupby("runner").agg(opp=("att", "size"), att=("att", "sum"), ok=("ok", "sum"))
        g = g[(g.opp >= MIN_OPP) & (g.att >= MIN_ATT)]
        if len(g) < 5:
            continue
        g["rate"] = (g.att / g.opp).round(3)
        g["success"] = (g.ok / g.att).round(3)
        r = weighted_corr(g.rate, g.success, g.att.to_numpy(float))
        print(f"\n  by runner, {label}: {len(g)} runners, attempt rate "
              f"{g.rate.min():.3f} to {g.rate.max():.3f}")
        print(f"  weighted corr(attempt rate, success) = {r:+.2f}")
    print("\n  Nothing is negative. Either she is not choosing, or what she passes")
    print("  up is no worse than what she takes. The data cannot separate those,")
    print("  and neither reading makes a must-attempt measurably worse.")


def main() -> None:
    pl = tables.read("plays", "training")
    d, censored = sp.attach(pl)
    does_it_exist(d, censored)
    bounds(d)
    gradient(d, censored)


if __name__ == "__main__":
    main()
