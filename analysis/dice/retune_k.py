"""Re-tune k for the production structures at a different cohort target.

    pixi run python analysis/dice/retune_k.py [target]     # default 250

Part 1 of freepass_cv.py only: best k per step on the usual 20 game splits, for
the batter and pitcher structures dice.py actually ships. The k values in
dice.py were tuned at a 300 cohort; if the target moves, they should be re-tuned
so the two agree.
"""
import sys

import numpy as np
import pandas as pd

TARGET = int(sys.argv[1]) if len(sys.argv) > 1 else 250
_here = __file__
__file__ = _here.replace("retune_k.py", "freepass_cv.py")
SRC = open(__file__, encoding="utf-8").read()
head = SRC[:SRC.index("# ---------------- 1. best k on the usual 20 splits ----------------")]
exec(head)
__file__ = _here
COHORT_PA = TARGET                      # trees_cv.cohorts() reads this at call time
std = halves(gids, REPEATS, np.random.default_rng(SEED))
print(f"cohort target {COHORT_PA}; {pa['game_id'].nunique()} games, {len(pa)} PAs\n")
SHIP = [("B", "S2 HR|K+FP", PLAN["B"]["S2 HR|K+FP"]), ("P", "7-line tree", PLAN["P"]["7-line tree"])]
for side, label_, (world, steps) in SHIP:
    ks = tune(steps, world, records(None, side, world, std))
    print(f"{label_}: " + "; ".join(f"{' | '.join('+'.join(c) for c in parts)} {f(k)}"
                                    for (_, parts), k in zip(steps, ks)))
    print(f"  as a dice.py list: [{', '.join(repr(round(float(k), 4)) for k in ks)}]\n")
