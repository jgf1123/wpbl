"""Who is in whose comparison group, for the batters the blog names.

    pixi run python analysis/dice/cohort_who.py [--who="Denae Benites,Kelsie Whitmore"]

Cohorts are the same at every step but the home-run one, where the two sluggers
use each other plus the next two power hitters, and are excluded from everyone
else's group. Prints each named batter's group, and whose groups she is in.
"""
import sys

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import (BATTER_STEPS, COHORT_PA, SLUGGERS, SLUGGER_COHORT, LINES,
                       cohorts, plate_appearances, usage)

pd.set_option("display.width", 220)
asked = next((a.split("=", 1)[1].split(",") for a in sys.argv[1:] if a.startswith("--who=")),
             list(SLUGGERS))
pa = plate_appearances()
shares = usage(pa)
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
X = pd.crosstab(pa["B"], pa["line"]).reindex(columns=LINES, fill_value=0)
ids = X.index.to_numpy()
names = [players["person_name"].get(i, i) for i in ids]
n = X.to_numpy().sum(axis=1).astype(float)
share = shares["B"].reindex(ids).fillna(0.0).to_numpy()
slug = np.isin(names, SLUGGERS)
everyone = cohorts(share, n, np.zeros(len(n), bool))
no_sluggers = cohorts(share, n, slug)
in_slug = np.isin(names, SLUGGER_COHORT)
hr_step = next(s for s, (_, parts) in enumerate(BATTER_STEPS) if ("HR",) in parts)
print(f"{len(names)} batters, cohort target {COHORT_PA} PA; "
      f"home-run step is step {hr_step + 1} of {len(BATTER_STEPS)}")


def table(idx):
    d = pd.DataFrame({"batter": [names[j] for j in idx],
                      "starts share": share[idx].round(3), "PA": n[idx].astype(int)})
    return d.sort_values("starts share", ascending=False).to_string(index=False)


for who in asked:
    i = names.index(who)
    print(f"\n{'=' * 70}\n{who}: starts share {share[i]:.3f}, {int(n[i])} PA\n{'=' * 70}")
    print(f"\nHER GROUP at the six ordinary steps ({int(n[everyone[i]].sum())} PA):")
    print(table(everyone[i]))
    hr = (np.flatnonzero(in_slug & (np.arange(len(n)) != i)) if slug[i] else no_sluggers[i])
    print(f"\nHER GROUP at the home-run step ({int(n[hr].sum())} PA)"
          f"{' - the slugger exception' if slug[i] else ''}:")
    print(table(hr))
    ord_in = [j for j in range(len(n)) if i in everyone[j]]
    hr_in = [j for j in range(len(n)) if not slug[j] and i in no_sluggers[j]]
    hr_in += [j for j in range(len(n)) if slug[j] and j != i and in_slug[i]]
    print(f"\nIN WHOSE GROUP she is, ordinary steps: {len(ord_in)} batters")
    print(table(ord_in) if ord_in else "  (none)")
    print(f"\nIN WHOSE GROUP she is, home-run step: {len(hr_in)} batters")
    print(table(hr_in) if hr_in else "  (none)")
