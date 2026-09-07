"""Are bullpens deep enough to answer the moments that matter?

    pixi run depth

A separate question from whether managers choose well. They mostly do -- given
who was callable, better arms do go into tighter spots. This asks whether the
arms on hand were any good in the first place, which is the question a
15-player roster actually raises.

Every pitching change is scored three ways:

    what they used   -- the chosen pitcher's RE24 per batter faced
    what they had    -- the best arm still callable at that moment
    the shortfall    -- whether the best callable arm was itself below average

That third one is the point. A below-average pitcher entering a tight spot is
one of two very different things: a manager passing over someone better, or a
manager with nobody better to pass to. Only the second is a depth problem, and
separating them is what this does.

League average is RE24/BF = 0 by construction, so "above average" is a real
benchmark rather than a chosen cutoff.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.leverage import Leverage
from wpbl.parse import OUT_DIR
from wpbl.relievers import (MIN_BF, TIRED_PITCHES, availability, batter_values,
                            entries)
from wpbl.usage_chart import CODES

HIGH_LEVERAGE = 1.25       # index units; the top ~30% of situations
AVERAGE = 0.0              # RE24 per batter faced, league average by construction


def rated_pitchers() -> pd.DataFrame:
    values = batter_values()
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    outs = pitching.groupby("person_id")["ip_outs"].sum()
    teams = pitching.groupby("person_id")["team_name"].last()
    rows = []
    for pid, group in values.groupby("pitcher_id"):
        if pid in outs.index and len(group) >= MIN_BF:
            rows.append({"pitcher_id": pid, "pitcher": group["pitcher"].iloc[0],
                         "team": teams.get(pid), "ip": outs[pid] / 3,
                         "re24": -group["run_value"].mean()})
    return pd.DataFrame(rows).set_index("pitcher_id")


def calls(lev: Leverage, rated: pd.DataFrame) -> pd.DataFrame:
    """Each pitching change, with what was used and what was available."""
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    staff, tired = availability(pitching)
    used_order = {(g, t): list(b.sort_values("appear_order")["person_id"])
                  for (g, t), b in pitching.groupby(["game_id", "team_id"])}

    rows = []
    for call in entries(lev).itertuples():
        if call.pitcher_id not in rated.index:
            continue
        order = used_order.get((call.game_id, call.team), [])
        already = set(order[:order.index(call.pitcher_id)]) if call.pitcher_id in order else set()
        pool = (staff.get((call.team, call.game_id), set())
                - already - tired.get((call.team, call.game_id), set()))
        options = [p for p in pool if p in rated.index]
        if not options:
            continue
        available = rated.loc[options, "re24"]
        rows.append({
            "game_id": call.game_id, "team": CODES.get(rated.loc[call.pitcher_id, "team"], "?"),
            "pitcher": call.pitcher, "li": call.li, "mid_inning": call.mid_inning,
            "used_re24": float(rated.loc[call.pitcher_id, "re24"]),
            "best_re24": float(available.max()),
            "options": len(options),
            "above_average_available": int((available > AVERAGE).sum()),
        })
    frame = pd.DataFrame(rows)
    frame["high"] = frame["li"] >= HIGH_LEVERAGE
    frame["used_below"] = frame["used_re24"] < AVERAGE
    frame["best_below"] = frame["best_re24"] < AVERAGE
    return frame


def main() -> None:
    pd.set_option("display.width", 250)
    lev = Leverage()
    rated = rated_pitchers()
    c = calls(lev, rated)

    print(f"{len(c)} pitching changes with a rated pitcher and a callable pool")
    print(f"league average RE24/BF = {AVERAGE:.2f} by construction; "
          f"{int((rated['re24'] > AVERAGE).sum())} of {len(rated)} rated arms are above it\n")

    print("=== what managers used vs what they had, by leverage ===")
    band = pd.cut(c["li"], [0, 0.75, 1.25, 99], labels=["low", "average", "high"])
    print(c.groupby(band, observed=True).agg(
        calls=("li", "size"),
        used=("used_re24", "mean"),
        best_available=("best_re24", "mean"),
        options=("options", "mean"),
        above_avg_options=("above_average_available", "mean")).round(3).to_string())

    high = c[c["high"]]
    print(f"\n\n=== the {len(high)} high-leverage calls (LI >= {HIGH_LEVERAGE}) ===")
    forced = high[high["used_below"] & high["best_below"]]
    chosen = high[high["used_below"] & ~high["best_below"]]
    good = high[~high["used_below"]]
    print(f"  went to an above-average arm            {len(good):3d}  "
          f"({len(good) / len(high) * 100:.0f}%)")
    print(f"  went to a below-average arm, forced     {len(forced):3d}  "
          f"({len(forced) / len(high) * 100:.0f}%)   nobody better was callable")
    print(f"  went to a below-average arm, by choice  {len(chosen):3d}  "
          f"({len(chosen) / len(high) * 100:.0f}%)   someone better was callable")

    print(f"\n  high-leverage calls with no above-average arm callable at all: "
          f"{int((high['above_average_available'] == 0).sum())} of {len(high)} "
          f"({(high['above_average_available'] == 0).mean() * 100:.0f}%)")

    print("\n\n=== by team: was there a good arm to reach for? ===")
    print(c.groupby("team").agg(
        calls=("li", "size"),
        high_lev=("high", "sum"),
        mean_best_available=("best_re24", "mean"),
        no_good_option=("above_average_available", lambda s: int((s == 0).sum())),
        mean_options=("options", "mean")).round(3).to_string())

    print("\n\n=== every high-leverage call, worst best-available first ===")
    detail = high.sort_values("best_re24")[
        ["team", "pitcher", "li", "used_re24", "best_re24", "options",
         "above_average_available", "mid_inning"]]
    print(detail.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
