"""The batter table drawn as a chart, so overlap between players is visible.

    pixi run batter-chart data/img/batters.png
    pixi run batter-chart data/img/batters.png --error=drop --hbp=split

Same numbers as `pixi run batters`, same options, same seed. Each row carries
the team, batter, plate appearances and RE24 total as text, then both per-PA
ratings on one shared axis: RE24 per plate appearance above, context-neutral
below, each a dot with its 95% interval.

Rows are sorted by the context-neutral rating, as in the table. A dagger marks
a batter whose rating moves more than batters.SENSITIVE across the attribution
options. The drawing itself lives in chart.py, shared with the pitcher chart.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from wpbl.batters import (ERROR_CHOICES, HBP_CHOICES, SEED, SENSITIVE, batter_table,
                          option, plate_appearances)
from wpbl.chart import MODELLED, SITUATIONAL, draw, signed


def main() -> None:
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        sys.exit("usage: pixi run batter-chart out.png [--error=...] [--hbp=...]")
    out = Path(paths[0])
    error = option("error", ERROR_CHOICES, sys.argv[1:])
    hbp = option("hbp", HBP_CHOICES, sys.argv[1:])

    table, _, _ = batter_table(plate_appearances(), error, hbp, np.random.default_rng(SEED))
    rows = table.to_dict("records")
    cells = [(r["tm"], r["batter"] + (" †" if r["swing"] > SENSITIVE else ""),
              str(r["pa"]), signed(r["re24"], 1)) for r in rows]
    series = [("RE24/PA", SITUATIONAL, table["situational"].to_numpy(),
               table["lo"].to_numpy(), table["hi"].to_numpy()),
              ("Neutral/PA", MODELLED, table["neutral"].to_numpy(),
               table["nlo"].to_numpy(), table["nhi"].to_numpy())]

    height = draw(out, ("Tm", "Batter", "PA", "RE24"), (False, False, True, True),
                  cells, series)
    print(f"wrote {out}  (728x{height}px, {len(rows)} batters)")


if __name__ == "__main__":
    main()
