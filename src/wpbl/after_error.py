"""Does the batting team hit better after the defence makes an error?

    pixi run python -m wpbl.after_error

The error itself puts a runner on or takes an out away, so runs after an error
are higher for a reason nobody disputes. The question is whether they are
higher than the base-out state the error left behind would predict -- a
rattled pitcher, a defence having a bad day.

Two windows, both on the training games, first error per half-inning only:

  rest of inning  runs scored after the error play to the end of the half,
                  against runs after a hit, walk or hit-by-pitch (no error on
                  the play, none earlier in the half) that left the same
                  base-out state. Within a state the run expectancy is one
                  number, so the matched difference is a difference in raw
                  runs; RE is subtracted only so the two columns read as
                  "runs above expected".
  next PA         the run value (RE24) of the next plate appearance, minus
                  that batter's own leave-one-out average, against the same
                  residual for the PA after a non-error hit, walk or HBP.

Intervals are bootstraps over games, since plays in one game share a pitcher,
a defence and a day.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.markov import re_of, run_expectancy
from wpbl.run_expectancy import HALF_KEY, LAST_INNING, damaged_halves

BOOTSTRAP = 2000
SEED = 20261016
ERROR = re.compile(r"\berror\b", re.I)
SAFE = {"single", "double", "triple", "walk", "hit_by_pitch"}


def _bases(frame: pd.DataFrame) -> pd.Series:
    return (frame["first_base"].notna().map({True: "1", False: "_"})
            + frame["second_base"].notna().map({True: "2", False: "_"})
            + frame["third_base"].notna().map({True: "3", False: "_"}))


def reached_on_error(narrative: str) -> bool:
    """The batter's own clause says she reached on the error."""
    head = str(narrative or "").split(";")[0].lower()
    return "reached" in head and "error" in head and "fielder's choice" not in head


def stopped_halves(plays: pd.DataFrame, games: pd.DataFrame) -> set[tuple]:
    """Regulation walk-offs and called games: the game's last half-inning, when
    play stopped before a third out. damaged_halves() already drops these in
    extra innings; the runs after a play in such a half are cut short, so they
    go here too."""
    stopped = set()
    for game_id, block in plays.groupby("game_id"):
        last = block.sort_values("sequence").iloc[-1]
        game = games.loc[game_id]
        called = "weather" in str(game.get("status", "")).lower()
        walked_off = (last["half"] == "bottom" and int(last["inning"]) >= LAST_INNING
                      and game["home_score"] > game["away_score"])
        if called or walked_off:
            stopped.add(tuple(last[HALF_KEY]))
    return stopped


def play_frame() -> pd.DataFrame:
    """One row per live play in a usable half-inning, with the state it left,
    runs still to come in the half, and whether an error preceded it."""
    plays = tables.read("plays", "training")
    line = tables.read("line_score", "training")
    games = tables.read("games", "training").set_index("game_id")
    players = tables.read("players", "training")
    person = players.set_index("player_id")["person_id"].to_dict()

    drop = damaged_halves(plays, line, games) | stopped_halves(plays, games)
    plays = plays.copy()
    plays["half_key"] = list(map(tuple, plays[HALF_KEY].values))
    plays = plays[~plays["half_key"].isin(drop) & (plays["outs_before"] < 3)]
    plays = plays.sort_values(["game_id", "sequence"])
    plays["bases"] = _bases(plays)
    plays["error"] = plays["narrative"].fillna("").str.contains(ERROR)
    plays["roe"] = plays["narrative"].map(reached_on_error) & plays["is_plate_appearance"]
    plays["batter"] = plays["batter_id"].map(person).fillna(plays["batter_id"])
    table = run_expectancy()

    out = []
    for _, half in plays.groupby("half_key", sort=False):
        half = half.reset_index(drop=True)
        n = len(half)
        nxt_bases = half["bases"].shift(-1)
        nxt_outs = half["outs_before"].shift(-1)
        runs = half["runs_scored"].to_numpy()
        after = runs[::-1].cumsum()[::-1] - runs          # runs on later plays
        half["after_bases"] = nxt_bases.fillna("end")
        half["after_outs"] = nxt_outs.fillna(3).astype(int)
        half["runs_after"] = after
        half["re_before"] = [re_of(table, b, int(o)) for b, o in zip(half["bases"], half["outs_before"])]
        half["re_after"] = [0.0 if b == "end" else re_of(table, b, o)
                            for b, o in zip(half["after_bases"], half["after_outs"])]
        half["run_value"] = half["re_after"] + half["runs_scored"] - half["re_before"]
        prior = half["error"].cumsum() - half["error"]
        half["errors_before"] = prior
        half["first_error"] = half["error"] & (prior == 0)
        half["play_index"] = np.arange(n)
        out.append(half)
    frame = pd.concat(out, ignore_index=True)
    frame.attrs["dropped_halves"] = len(drop)
    return frame


def _treated(frame: pd.DataFrame, kind: str) -> pd.Series:
    """The first error of each half-inning, or only those where the batter
    reached on it."""
    if kind == "roe":
        first_roe = frame["roe"] & (frame.groupby("half_key")["roe"].cumsum() == 1)
        return first_roe & (frame["errors_before"] == 0)
    return frame["first_error"]


def _controls(frame: pd.DataFrame) -> pd.Series:
    """A hit, walk or HBP with no error on the play or earlier in the half."""
    return (frame["event_type"].isin(SAFE) & ~frame["error"]
            & (frame["errors_before"] == 0))


def rest_of_inning(frame: pd.DataFrame, kind: str = "all") -> pd.DataFrame:
    """Treated and control plays leaving a live state, with runs above that
    state's expectation. Error states with no control are dropped."""
    live = frame[frame["after_bases"] != "end"].copy()
    live["excess"] = live["runs_after"] - live["re_after"]
    live["state"] = live["after_bases"] + live["after_outs"].astype(str)
    live["group"] = np.where(_treated(live, kind), "error",
                             np.where(_controls(live), "control", None))
    live = live[live["group"].notna()]
    have = set(live.loc[live["group"] == "control", "state"])
    return live[live["state"].isin(have)]


def matched_difference(live: pd.DataFrame) -> float:
    """Mean over error plays of (runs after - control mean in the same state)."""
    control = live[live["group"] == "control"].groupby("state")["runs_after"].mean()
    err = live[live["group"] == "error"]
    return float((err["runs_after"] - err["state"].map(control)).mean())


def next_pa(frame: pd.DataFrame, kind: str = "all") -> pd.DataFrame:
    """The first plate appearance after each treated or control play in the same
    half, with its RE24 minus the batter's leave-one-out RE24 per PA."""
    pa = frame[frame["is_plate_appearance"] & frame["batter"].notna()].copy()
    total = pa.groupby("batter")["run_value"].transform("sum")
    count = pa.groupby("batter")["run_value"].transform("count")
    pa["loo"] = (total - pa["run_value"]) / (count - 1)
    pa = pa[count > 1]
    pa["residual"] = pa["run_value"] - pa["loo"]

    frame = frame.copy()
    frame["group"] = np.where(_treated(frame, kind), "error",
                              np.where(_controls(frame), "control", None))
    sources = frame[frame["group"].notna()]
    pa_by_half = {k: g for k, g in pa.groupby("half_key", sort=False)}
    rows = []
    for src in sources.itertuples():
        later = pa_by_half.get(src.half_key)
        if later is None:
            continue
        later = later[later["play_index"] > src.play_index]
        if later.empty:
            continue
        hit = later.iloc[0]
        rows.append({"group": src.group, "game_id": src.game_id,
                     "half_key": src.half_key, "inning": src.inning,
                     "run_value": hit["run_value"], "loo": hit["loo"],
                     "residual": hit["residual"],
                     "on_base": hit["event_type"] in SAFE or "error" in str(hit["narrative"]).lower(),
                     "event": hit["event_type"]})
    out = pd.DataFrame(rows)
    out.attrs["all_pa_residual"] = float(pa["residual"].mean())
    return out


def bootstrap(stat, frame: pd.DataFrame, rng) -> tuple[float, float]:
    """95% interval of stat(frame) resampling whole games."""
    games = frame["game_id"].unique()
    blocks = {g: b for g, b in frame.groupby("game_id")}
    draws = []
    for _ in range(BOOTSTRAP):
        pick = rng.choice(games, size=len(games))
        sample = pd.concat([blocks[g] for g in pick], ignore_index=True)
        try:
            draws.append(stat(sample))
        except (ValueError, ZeroDivisionError):
            continue
    draws = np.array([d for d in draws if np.isfinite(d)])
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _pa_diff(sample: pd.DataFrame) -> float:
    g = sample.groupby("group")["residual"].mean()
    return float(g["error"] - g["control"])


def main() -> None:
    rng = np.random.default_rng(SEED)
    frame = play_frame()
    print(f"{frame['half_key'].nunique()} half-innings, "
          f"{frame.attrs['dropped_halves']} dropped (damaged, walk-off or called)")
    print(f"{int(frame['error'].sum())} error plays, "
          f"{int(frame['first_error'].sum())} first-of-half, "
          f"{int(frame['roe'].sum())} reached on error\n")

    for kind, label in (("all", "every error"), ("roe", "reached on error only")):
        live = rest_of_inning(frame, kind)
        err, ctl = live[live["group"] == "error"], live[live["group"] == "control"]
        diff = matched_difference(live)
        lo, hi = bootstrap(matched_difference, live, rng)
        print(f"== {label}: rest of inning ==")
        print(f"  error plays {len(err)}, controls {len(ctl)} across {live['state'].nunique()} states")
        print(f"  runs after the play:   error {err['runs_after'].mean():.3f}   "
              f"control {ctl['runs_after'].mean():.3f}")
        print(f"  above expectation:     error {err['excess'].mean():+.3f}   "
              f"control {ctl['excess'].mean():+.3f}")
        print(f"  matched difference (error - control, same state): {diff:+.3f} runs "
              f"[{lo:+.3f}, {hi:+.3f}]")

        nxt = next_pa(frame, kind)
        g = nxt.groupby("group")
        diff = _pa_diff(nxt)
        lo, hi = bootstrap(_pa_diff, nxt, rng)
        print(f"== {label}: next PA ==")
        print(f"  PAs: error {g.size()['error']}, control {g.size()['control']}")
        print(f"  RE24:                  error {g['run_value'].mean()['error']:+.3f}   "
              f"control {g['run_value'].mean()['control']:+.3f}")
        print(f"  batter's own average:  error {g['loo'].mean()['error']:+.3f}   "
              f"control {g['loo'].mean()['control']:+.3f}")
        print(f"  RE24 above batter avg: error {g['residual'].mean()['error']:+.3f}   "
              f"control {g['residual'].mean()['control']:+.3f}   "
              f"(all PAs {nxt.attrs['all_pa_residual']:+.3f})")
        print(f"  reached base:          error {g['on_base'].mean()['error']:.3f}   "
              f"control {g['on_base'].mean()['control']:.3f}")
        print(f"  difference (error - control): {diff:+.3f} runs [{lo:+.3f}, {hi:+.3f}]\n")


if __name__ == "__main__":
    main()
