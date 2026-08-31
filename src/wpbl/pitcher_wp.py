"""Win probability a pitcher gained or lost while she was on the mound.

    pixi run pwp

The unit is a *segment*: one pitcher, one half-inning, one continuous stretch on
the mound. A pitcher who works a clean inning has one segment; a reliever who
enters with two on and nobody out has a segment that starts there. A segment is
scored by the change in her own team's win probability from the state she
inherited to the state she handed over -- the next segment's opening state, or
the settled result if the game ends on her.

That is the only attribution that stays honest across pitching changes: a
reliever is charged with the runners she lets score, not the ones she inherited,
because the inherited runners are already priced into the state she took over.

Two things this cannot separate, both flagged in the output:

* Fielding. Win probability does not care whose error let the run in, so a
  pitcher wears her defence.
* Leverage. A reliever pitching one inning in a tie swings far more win
  probability per out than a starter working the 1st with the game level, so
  relievers spread toward both extremes. The per-inning rate does not correct
  for this; it is a description of what happened, not a skill estimate.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.parse import OUT_DIR
from wpbl.win_probability import Model, REGULATION

MIN_INNINGS = 4.0    # below this the spread statistics are not worth printing


def segments(model: Model) -> pd.DataFrame:
    """One row per pitcher per continuous stretch on the mound."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    games = pd.read_parquet(OUT_DIR / "games.parquet").set_index("game_id")

    # Go through pitcher_id, not the name on the play: the feed spells one
    # pitcher two ways ("Maggie Fox" once, "Maggie Foxx" otherwise), and keying
    # on the raw name drops that appearance entirely.
    people = pd.read_parquet(OUT_DIR / "players.parquet").set_index("player_id")["person_name"]
    plays = plays.assign(pitcher_name=plays["pitcher_id"].map(people))

    live = plays[(plays["inning"] <= REGULATION)
                 # Roster moves logged after the third out sit in no live state.
                 & (plays["outs_before"] < 3)].dropna(
        subset=["batting_team_id", "pitcher_name"]).sort_values(["game_id", "sequence"])

    rows = []
    for game_id, game_plays in live.groupby("game_id"):
        game = games.loc[game_id]
        home_id = game["home_team_id"]
        home_won = game["home_score"] > game["away_score"]
        # Two games really did run to an 8th; a third is mislabelled "Final - 8
        # innings" but has no plays past the 7th.
        went_to_extras = game["innings"] > REGULATION and len(
            plays[(plays["game_id"] == game_id) & (plays["inning"] > REGULATION)]) > 0

        def team_wp(play, team_is_home: bool) -> float:
            """Win probability for one named team at the state before this play.

            It has to be pinned to a team rather than to whoever is fielding: a
            segment closes at the next half-inning, where the fielding side has
            swapped, and reading that state as "the fielder" would score the
            handover from the opponent's point of view.
            """
            bases = (("1" if pd.notna(play.first_base) else "_")
                     + ("2" if pd.notna(play.second_base) else "_")
                     + ("3" if pd.notna(play.third_base) else "_"))
            half = "bottom" if play.batting_team_id == home_id else "top"
            diff = int(play.home_score_before - play.away_score_before)
            wp_home = model.win_probability(play.inning, half, int(play.outs_before),
                                            bases, diff)
            return wp_home if team_is_home else 1 - wp_home

        ordered = list(game_plays.itertuples())
        # A segment breaks on a new half-inning or a new pitcher.
        marks = []
        for index, play in enumerate(ordered):
            key = (play.inning, play.half, play.pitcher_name)
            if not marks or marks[-1][0] != key:
                marks.append((key, index))

        for position, ((inning, half, pitcher), start) in enumerate(marks):
            stop = marks[position + 1][1] if position + 1 < len(marks) else len(ordered)
            first = ordered[start]
            # The fielding side in this half-inning is the one not batting.
            pitching_is_home = half == "top"
            pitcher_won = home_won == pitching_is_home

            wp_in = team_wp(first, pitching_is_home)
            if stop < len(ordered):
                following = ordered[stop]
                wp_out = team_wp(following, pitching_is_home)
                outs_out = (int(following.outs_before)
                            if (following.inning, following.half) == (inning, half) else 3)
            elif went_to_extras:
                # The 7th ended level and the tiebreaker inning is outside the
                # model, so she handed over a coin flip, not a result.
                wp_out = 0.5
                outs_out = 3
            else:
                # Nothing follows: the game is settled on this segment.
                wp_out = 1.0 if pitcher_won else 0.0
                outs_out = 3
            outs = max(outs_out - int(first.outs_before), 0)

            block = ordered[start:stop]
            # A pitching change is logged under the departing pitcher's name, so
            # a change at the very top of an inning leaves a segment holding
            # nothing but that announcement. It is not an appearance.
            if not any(play.is_plate_appearance for play in block):
                continue
            rows.append({
                "game_id": game_id,
                "date": game["game_date"],
                "pitcher": pitcher,
                "team": (game["away_team_name"] if half == "bottom"
                         else game["home_team_name"]),
                "inning": inning,
                "half": half,
                "entered_outs": int(first.outs_before),
                "outs": outs,
                "runs": sum(p.runs_scored for p in block),
                "wp_in": wp_in,
                "wp_out": wp_out,
                "wp_delta": wp_out - wp_in,
                "closed_game": stop >= len(ordered),
            })
    return pd.DataFrame(rows)


def box_innings() -> pd.Series:
    """Innings pitched per pitcher-game, from the box score.

    The denominator comes from the box score rather than from the segments: a
    called game ends a half-inning short of three outs, so counting outs off the
    play-by-play would credit innings that were never finished.
    """
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    outs = pitching.set_index(["game_id", "person_name"])["ip_outs"]
    outs.index.names = ["game_id", "pitcher"]
    return outs


def innings_in_scope(frame: pd.DataFrame) -> pd.Series:
    """Innings pitched inside innings 1-7, per pitcher-game.

    This is the denominator that matches the numerator: win probability is only
    scored through the 7th, so a pitcher who also worked an 8th must not be
    charged those innings. Derived outs are capped at the box score, which is
    what settles the one game called early with a half-inning unfinished.
    """
    derived = frame.groupby(["game_id", "pitcher"])["outs"].sum()
    box = box_innings()
    return pd.concat([derived.rename("derived"), box.rename("box")], axis=1).dropna().min(axis=1)


def reconcile(frame: pd.DataFrame) -> None:
    """Outs taken off the play-by-play must equal the box score wherever both
    cover the same innings."""
    derived = frame.groupby(["game_id", "pitcher"])["outs"].sum().rename("derived")
    joined = pd.concat([derived, box_innings().rename("box")], axis=1).dropna()
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    extras = set(plays.loc[plays["inning"] > REGULATION, "game_id"])
    covered = joined.index.get_level_values("game_id").nunique()
    print(f"segments cover {len(joined)} pitcher-games across {covered} games")

    plain = joined[~joined.index.get_level_values("game_id").isin(extras)]
    off = plain[plain["derived"] != plain["box"]]
    print(f"  games decided in seven: outs match in {len(plain) - len(off)} of {len(plain)}")
    if len(off):
        print("    the exception is the game called early, a half-inning short of three outs:")
        print(off.to_string())

    past = joined[joined.index.get_level_values("game_id").isin(extras)]
    if len(past):
        short = (past["box"] - past["derived"])
        eighth = (plays[plays["inning"] > REGULATION]
                  .groupby(["game_id", "pitcher_name"]).size())
        print(f"  games that ran to an 8th: {len(past)} pitcher-games, "
              f"{int(short.sum())} outs held back as out of scope "
              f"({len(eighth)} pitchers worked the 8th)")


def telescopes(frame: pd.DataFrame) -> None:
    """A team's pitching segments and the batting gaps between them must add up
    to the whole game: from the state at first pitch to the settled result. If
    any segment were scored from the wrong side, this would not close."""
    games = pd.read_parquet(OUT_DIR / "games.parquet").set_index("game_id")
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    extras = set(plays.loc[plays["inning"] > REGULATION, "game_id"])
    failures = 0
    groups = 0
    for (game_id, team), sub in frame.groupby(["game_id", "team"]):
        groups += 1
        sub = sub.sort_values(["inning", "half"])
        game = games.loc[game_id]
        won = (game["home_score"] > game["away_score"]) == (team == game["home_team_name"])
        # A game that ran past the 7th is level at the point this scoring stops.
        final = 0.5 if game["innings"] > REGULATION and game_id in extras else (
            1.0 if won else 0.0)

        batting, previous = 0.0, None
        for row in sub.itertuples():
            if previous is not None:
                batting += row.wp_in - previous
            previous = row.wp_out
        batting += final - previous

        if abs(sub["wp_delta"].sum() + batting - (final - sub.iloc[0]["wp_in"])) > 1e-9:
            failures += 1
    print(f"  pitching and batting telescope to the result in "
          f"{groups - failures} of {groups} team-games "
          f"({'PASS' if not failures else 'FAIL'})")


def main() -> None:
    pd.set_option("display.width", 250)
    model = Model()
    frame = segments(model)

    print(f"{len(frame)} segments across {frame['game_id'].nunique()} games\n")
    reconcile(frame)
    telescopes(frame)

    # Innings come from the box score; win probability comes from the segments.
    innings = innings_in_scope(frame)
    per_game = frame.groupby(["team", "pitcher", "game_id"]).size().reset_index()
    per_game["ip"] = [innings.get((g, p), 0) / 3 for g, p in
                      zip(per_game["game_id"], per_game["pitcher"])]
    ip_total = per_game.groupby(["team", "pitcher"])["ip"].sum()

    tally = frame.groupby(["team", "pitcher"]).agg(
        seg=("wp_delta", "size"),
        runs=("runs", "sum"),
        total_wp=("wp_delta", "sum"),
        sd=("wp_delta", "std"),
        best=("wp_delta", "max"),
        worst=("wp_delta", "min"),
    )
    tally["ip"] = ip_total
    tally["wp_per_inn"] = tally["total_wp"] / tally["ip"].replace(0, np.nan)
    tally = tally[["seg", "ip", "runs", "total_wp", "wp_per_inn", "sd", "best", "worst"]]

    ranked = tally.sort_values("total_wp", ascending=False).round(3)
    print("\n\n=== win probability added while pitching, "
          "innings 1-7 of all 24 games ===")
    print("    positive means she handed over a better position than she inherited;")
    print("    the two 8th innings that were played are outside the model's scope\n")
    print(ranked.to_string())

    print("\n\n=== per inning, pitchers with at least "
          f"{MIN_INNINGS:.0f} innings ===")
    qualified = tally[tally["ip"] >= MIN_INNINGS].sort_values("wp_per_inn", ascending=False)
    print(qualified.round(3).to_string())

    print("\n\n=== spread by role ===")
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    role = pitching.set_index(["game_id", "person_name"])["role"].to_dict()
    frame = frame.assign(role=[role.get((g, p)) for g, p in
                               zip(frame["game_id"], frame["pitcher"])])

    print("  per segment:")
    for label in ("SP", "RP"):
        subset = frame[frame["role"] == label]
        print(f"    {'started that game' if label == 'SP' else 'relieved that game':22s} "
              f"n={len(subset):4d}  mean {subset['wp_delta'].mean():+.4f}  "
              f"sd {subset['wp_delta'].std():.4f}  "
              f"min {subset['wp_delta'].min():+.3f}  max {subset['wp_delta'].max():+.3f}")
    mid = frame[frame["entered_outs"] > 0]
    print(f"    {'entered mid-inning':22s} n={len(mid):4d}  "
          f"mean {mid['wp_delta'].mean():+.4f}  sd {mid['wp_delta'].std():.4f}  "
          f"min {mid['wp_delta'].min():+.3f}  max {mid['wp_delta'].max():+.3f}")

    # The spread that matters is across pitchers, not across segments: a reliever
    # throwing four innings all season lands far from zero on either side.
    print("\n  per pitcher, rate per inning:")
    rates = []
    for label in ("SP", "RP"):
        subset = frame[frame["role"] == label]
        wp = subset.groupby("pitcher")["wp_delta"].sum()
        ip = pd.Series({p: sum(innings.get((g, p), 0) for g in
                               subset.loc[subset["pitcher"] == p, "game_id"].unique()) / 3
                        for p in wp.index})
        rate = (wp / ip.replace(0, np.nan)).dropna()
        rates.append((label, rate))
        print(f"    {'as a starter' if label == 'SP' else 'as a reliever':22s} "
              f"n={len(rate):3d} pitchers  sd {rate.std():.4f}  "
              f"min {rate.min():+.3f}  max {rate.max():+.3f}")
    print("\n  Relief work is the higher-leverage job and comes in far smaller doses, so")
    print("  those rates sit further from zero on both sides. That is leverage and sample")
    print("  size, not evidence that relievers are better or worse.")


if __name__ == "__main__":
    main()
