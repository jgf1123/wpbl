"""Is there matchup selection at all? Because a lot was resting on it.

    pixi run python analysis/dice/matchup_selection.py

Three files asserted the same convenient thing: a steal is chosen, managers choose
favourable matchups, so a strong-armed catcher is only tested by fast runners and
her caught-stealing rate reads LOW. Selection compresses the spread between
players, any spread that survives is a floor rather than an estimate, a null would
prove nothing and a positive result is safe.

That argument needs a mechanism, and the mechanism is testable: if runners avoid the
strong arms, the catchers with the best numbers faced the fastest runners. **They
did not.** Opposition quality runs from 0.83 to 0.89 across all seven catchers and
correlates -0.47 with caught-stealing rate over seven points, which is noise; the
deterrence test in steals.py is -1.1 SE. Everyone faced much the same runners, so
the spreads should be read as estimates and not as floors.

A CIRCULARITY to avoid, because the first version of this walked into it. Scoring a
catcher's opposition by those runners' overall success rates lets her own results
count toward it: she throws out eight of twenty-one, those eight look slower, and
her opposition looks weak BECAUSE SHE IS GOOD. That version returned -0.86. Scoring
each runner from her attempts against OTHER catchers only takes it to -0.47, and
most of what is left is seven points of nothing.

The mirror test -- do better runners face harder catchers? -- cannot be cleaned the
same way, because facing a hard catcher lowers a runner's success directly. It is
reported for completeness and should not be read as evidence about selection.

What this does NOT overturn: selection on whether to go at all. Only about a tenth
of chances become attempts, so every success rate in this repo is conditional on
somebody liking the odds, and that is exactly why must_attempt.py cannot price a
forced steal. Biasing the LEVEL and compressing the SPREAD BETWEEN PLAYERS are
different claims. The first survives; the second does not.
"""

from __future__ import annotations

import importlib
import sys

import numpy as np
import pandas as pd

from wpbl import tables

sys.path.insert(0, "analysis/dice")
sl = importlib.import_module("steals")

pd.set_option("display.width", 200)
MIN_CATCHER_ATT = 5     # attempts faced before her opposition mix means anything
MIN_RUNNER_ATT = 4
GHOST = 6.0             # ghost attempts, from the success spread in steals.py


def attempts_with_catcher() -> pd.DataFrame:
    """Every credited attempt, with the catcher who was behind the plate."""
    d = sl.runner_chances(tables.read("plays", "training"))
    f = tables.read("fielding", "training")
    cat = f[f["position"].astype(str).str.lower() == "c"]
    who = (cat.sort_values("sba", ascending=False)
              .drop_duplicates(["game_id", "team_id"])
              .set_index(["game_id", "team_id"])["person_name"].to_dict())
    d["catcher"] = [who.get((g, t)) for g, t in zip(d.game_id, d.fielding)]
    return d.dropna(subset=["catcher"]).query("att == 1"), cat


def opposition(att: pd.DataFrame, cat: pd.DataFrame) -> pd.DataFrame:
    """How good were the runners who ran on each catcher, leaving her out of it."""
    p = att.ok.sum() / len(att)
    rows = []
    for c, g in att.groupby("catcher"):
        if len(g) < MIN_CATCHER_ATT:
            continue
        qs = []
        for r in g.runner:
            other = att[(att.runner == r) & (att.catcher != c)]
            if len(other):          # no evidence about her anywhere else
                qs.append((other.ok.sum() + GHOST * p) / (len(other) + GHOST))
        if not qs:
            continue
        cs = cat[cat.person_name == c]
        rows.append({"catcher": c, "att": len(g), "rated": len(qs),
                     "CS%": round(100 * cs.csb.sum() / (cs.sba.sum() + cs.csb.sum()), 1),
                     "opp_quality": round(float(np.mean(qs)), 3)})
    return pd.DataFrame(rows).sort_values("CS%", ascending=False)


def mirror(att: pd.DataFrame) -> pd.DataFrame:
    """How hard were the catchers each runner took on. Confounded; see docstring."""
    p = att.ok.sum() / len(att)
    rows = []
    for rn, g in att.groupby("runner"):
        if len(g) < MIN_RUNNER_ATT:
            continue
        ds = []
        for c in g.catcher:
            other = att[(att.catcher == c) & (att.runner != rn)]
            if len(other):
                ds.append(1 - (other.ok.sum() + GHOST * p) / (len(other) + GHOST))
        if ds:
            rows.append({"runner": rn, "att": len(g), "success": round(g.ok.mean(), 3),
                         "faced_difficulty": round(float(np.mean(ds)), 3)})
    return pd.DataFrame(rows).sort_values("success", ascending=False)


def main() -> None:
    att, cat = attempts_with_catcher()
    t = opposition(att, cat)
    print("=== did the better catchers face the better runners? ===")
    print("  Compression needs YES. Each runner scored from her attempts against")
    print("  OTHER catchers, so a good catcher cannot depress her own opposition.\n")
    print(t.to_string(index=False))
    r = float(np.corrcoef(t["CS%"], t.opp_quality)[0, 1])
    print(f"\n  corr(caught-stealing rate, quality of runners faced) = {r:+.2f} "
          f"over {len(t)} catchers")
    print(f"  opposition quality spans {t.opp_quality.min():.3f} to "
          f"{t.opp_quality.max():.3f} -- every catcher faced much the same runners")
    print("  NO COMPRESSION MECHANISM. Read the player spreads as estimates.")
    print("  (Scoring opposition without leaving the catcher out returns -0.86,")
    print("   which is her own arm counted twice. See the module docstring.)")

    u = mirror(att)
    print("\n\n=== the mirror, reported but not evidence ===")
    print(u.to_string(index=False))
    r2 = float(np.corrcoef(u.success, u.faced_difficulty)[0, 1])
    print(f"\n  corr(runner success, difficulty faced) = {r2:+.2f} over {len(u)} runners")
    print("  Facing a hard catcher lowers success directly, so this correlation is")
    print("  mechanical whatever the selection is. It cannot settle anything.")


if __name__ == "__main__":
    main()
