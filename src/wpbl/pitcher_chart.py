"""The pitcher table drawn as a chart, on one axis in runs per batter faced.

    pixi run pitcher-chart data/img/pitchers.png

Same numbers as `pixi run pitchers`. Each row carries the team, pitcher,
RE24 total, ERA, FIP and her strikeout and walk rates as text, then
two ratings on a shared axis: FIP restated as runs saved per batter faced, and
RE24 per batter faced, each a dot with its 95% interval.

Putting them on one axis is the point of the restatement. FIP normally reads on
an ERA scale, which cannot be compared with a per-batter run value by eye;
dividing runs saved per seven innings by the league's batters per inning puts
both in the same unit. Two things follow that a reader should be told in the
caption: FIP's spread is narrower by construction, because it strips out
everything the defence did, and RE24 is the season's actual accounting while
FIP is the part of it the pitcher controlled.

Rows are sorted by FIP, the more repeatable of the two -- split-half
reliability 0.31 against 0.23 for RE24 per batter faced -- which mirrors the
batter chart's sort by the context-neutral rating.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

from wpbl.chart import MODELLED, SITUATIONAL, draw, signed
from wpbl.pitchers import SEED, charged, pitcher_table


def main() -> None:
    paths = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not paths:
        sys.exit("usage: pixi run pitcher-chart out.png")
    out = Path(paths[0])

    table = pitcher_table(charged(), np.random.default_rng(SEED))
    rows = table.to_dict("records")
    cells = [(r["tm"], r["pitcher"], signed(r["total"], 1), f"{r['era']:.2f}",
              f"{r['fip']:.2f}", f"{r['k9']:.1f}", f"{r['bb9']:.1f}") for r in rows]
    series = [("FIP as runs/BF", MODELLED, table["fip_bf"].to_numpy(),
               table["fip_bf_lo"].to_numpy(), table["fip_bf_hi"].to_numpy()),
              ("RE24/BF", SITUATIONAL, table["re24_bf"].to_numpy(),
               table["lo"].to_numpy(), table["hi"].to_numpy())]

    height = draw(out, ("Tm", "Pitcher", "RE24", "ERA", "FIP", "K/7", "BB/7"),
                  (False, False, True, True, True, True, True), cells, series)
    print(f"wrote {out}  (728x{height}px, {len(rows)} pitchers)")


if __name__ == "__main__":
    main()
