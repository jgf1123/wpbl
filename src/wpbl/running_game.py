"""The running game: how often runners tried, how often they made it, what it was worth.

    pixi run running

Split by the fielding team, with New York set against everyone else, because
New York is the one team whose catcher changed the running game: Denae Benites
caught every game and threw out runners at several times the league rate.

An OPPORTUNITY is a plate appearance with a runner who has an open base ahead
of her -- a runner on first with second empty, or a runner on second with third
empty. Steals of home are counted as attempts but not given opportunities of
their own; there were almost none. Two details matter:

  * The base state is read at the start of the plate appearance, before any
    steal during it. The feed records a steal as its own play ahead of the plate
    appearance, so reading the state off the plate appearance row itself shows
    the runner already on second, and the opportunity she used disappears --
    which would inflate the attempt rate of exactly the teams that steal most.
  * One plate appearance is one opportunity however many runners could go,
    matching the usual stolen-base-opportunity convention.

Runs come off the run-expectancy table: a steal or caught stealing is worth the
change in expected runs across the play, plus any run that scored on it.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.markov import re_of, run_expectancy
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

FOCUS = "NYH"


def plays_with_state() -> pd.DataFrame:
    plays = pd.read_parquet(OUT_DIR / "plays.parquet").sort_values(["game_id", "sequence"])
    teams = (pd.read_parquet(OUT_DIR / "team_games.parquet")
             .drop_duplicates("team_id").set_index("team_id")["team_name"])
    plays["fielding"] = plays["pitching_team_id"].map(teams).map(CODES)
    plays["bases"] = (plays["first_base"].notna().map({True: "1", False: "_"})
                      + plays["second_base"].notna().map({True: "2", False: "_"})
                      + plays["third_base"].notna().map({True: "3", False: "_"}))
    return plays[plays["outs_before"] < 3].copy()


def opportunities(plays: pd.DataFrame) -> pd.DataFrame:
    """One row per plate appearance, with the base state it began in."""
    frame = plays.copy()
    half = ["game_id", "inning", "half"]
    # Every play up to and including a plate appearance belongs to it: shift the
    # running count of plate appearances so the plays before one share its id.
    frame["pa_group"] = (frame.groupby(half)["is_plate_appearance"]
                         .transform(lambda s: s.astype(int).cumsum().shift(fill_value=0)))
    first = frame.groupby(half + ["pa_group"]).first()
    has_pa = frame.groupby(half + ["pa_group"])["is_plate_appearance"].any()
    first = first[has_pa]
    first["to_second"] = first["bases"].str[0].eq("1") & first["bases"].str[1].eq("_")
    first["to_third"] = first["bases"].str[1].eq("2") & first["bases"].str[2].eq("_")
    first["any"] = first["to_second"] | first["to_third"]
    return first.reset_index()[["fielding", "to_second", "to_third", "any"]]


def attempts(plays: pd.DataFrame) -> pd.DataFrame:
    table = run_expectancy()
    rows = []
    for _, half in plays.groupby(["game_id", "inning", "half"], sort=False):
        records = list(half.itertuples())
        for i, play in enumerate(records):
            if play.event_type not in ("stolen_base", "caught_stealing"):
                continue
            nxt = records[i + 1] if i + 1 < len(records) else None
            after = re_of(table, nxt.bases, int(nxt.outs_before)) if nxt is not None else 0.0
            text = str(play.narrative).lower()
            rows.append({"fielding": play.fielding, "stole": play.event_type == "stolen_base",
                         "base": "third" if "third" in text else "home" if "home" in text else "second",
                         "runs": after + play.runs_scored
                         - re_of(table, play.bases, int(play.outs_before))})
    return pd.DataFrame(rows)


def summarise(opp: pd.DataFrame, att: pd.DataFrame, games: int) -> dict:
    stole = int(att["stole"].sum())
    return {"games": games, "opportunities": int(opp["any"].sum()), "attempts": len(att),
            "attempt_rate": len(att) / opp["any"].sum(), "per_game": len(att) / games,
            "stolen": stole, "caught": len(att) - stole, "caught_pct": (len(att) - stole) / len(att),
            "runs": att["runs"].sum(),
            "opp_2nd": int(opp["to_second"].sum()), "att_2nd": int((att["base"] == "second").sum()),
            "opp_3rd": int(opp["to_third"].sum()), "att_3rd": int((att["base"] == "third").sum())}


def main() -> None:
    pd.set_option("display.width", 220)
    plays = plays_with_state()
    opp = opportunities(plays)
    att = attempts(plays)
    team_games = plays.groupby("fielding")["game_id"].nunique()

    groups = {
        f"Against {FOCUS}": [FOCUS],
        "Against everyone else": [t for t in team_games.index if t != FOCUS],
        "League": list(team_games.index),
    }
    rows = {label: summarise(opp[opp["fielding"].isin(teams)], att[att["fielding"].isin(teams)],
                             int(team_games[teams].sum()))
            for label, teams in groups.items()}
    rows.update({f"  {t}": summarise(opp[opp["fielding"] == t], att[att["fielding"] == t],
                                     int(team_games[t])) for t in team_games.index})
    table = pd.DataFrame(rows).T
    table["rate_2nd"] = table["att_2nd"] / table["opp_2nd"]
    table["rate_3rd"] = table["att_3rd"] / table["opp_3rd"]

    print("opportunity = plate appearance with a runner on 1st and 2nd open, or on 2nd and 3rd open,")
    print("read before any steal during it; games are fielding-team games\n")
    cols = ["games", "opportunities", "attempts", "attempt_rate", "per_game", "stolen", "caught",
            "caught_pct", "runs", "opp_2nd", "att_2nd", "rate_2nd", "opp_3rd", "att_3rd", "rate_3rd"]
    shown = table[cols].copy()
    for c in ("attempt_rate", "caught_pct", "rate_2nd", "rate_3rd"):
        shown[c] = (shown[c].astype(float) * 100).round(1)
    for c in ("per_game", "runs"):
        shown[c] = shown[c].astype(float).round(2)
    print(shown.to_string())

    print("\n=== markdown for the post ===\n")
    print("|  | Opportunities | Attempts | Attempt rate | Stolen | Caught | Caught % | Net runs |")
    print("|---|---|---|---|---|---|---|---|")
    for label in groups:
        if label == "League":
            continue
        r = table.loc[label]
        print(f"| {label} | {int(r.opportunities)} | {int(r.attempts)} | {float(r.attempt_rate):.1%} | "
              f"{int(r.stolen)} | {int(r.caught)} | {float(r.caught_pct):.0%} | "
              f"{float(r.runs):+.1f} |".replace("-", "−").replace("|+", "| +"))


if __name__ == "__main__":
    main()
