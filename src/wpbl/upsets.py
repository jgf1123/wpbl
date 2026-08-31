"""Games where a team was heavily favoured and lost.

    pixi run upsets

For every plate appearance the model scores the state and asks what the team
that eventually lost was worth at that moment. A game's upset size is the peak
that losing team ever reached: the higher it climbed before losing, the bigger
the collapse.

The model is team-agnostic on purpose -- both sides draw the same league-wide
run distribution -- so these are upsets against a neutral baseline, not against
any judgement about which team was better.
"""

from __future__ import annotations

import re

import pandas as pd

from wpbl.win_probability import Model, REGULATION

# Errors and misplays as the narrative writes them.
ERROR = re.compile(r"\berror\b|muffed|\bE\d\b", re.I)

# Only games where the losing side genuinely had the game in hand.
COLLAPSE_THRESHOLD = 0.65


def timeline(model: Model) -> pd.DataFrame:
    """Win probability for the eventual loser, at every plate appearance."""
    plays = pd.read_parquet("data/tables/plays.parquet")
    games = pd.read_parquet("data/tables/games.parquet").set_index("game_id")

    rows = []
    # Every play, not only plate appearances: a wild pitch or a stolen base
    # moves the game too, and scoring only at plate appearances would credit
    # its effect to whichever batter happened to follow.
    live = plays[(plays["inning"] <= REGULATION)
                 # Roster moves are sometimes logged after the third out, when
                 # the half-inning is already over and there is no live state.
                 & (plays["outs_before"] < 3)].dropna(
        subset=["batting_team_id"]).sort_values(["game_id", "sequence"])
    for play in live.itertuples():
        game = games.loc[play.game_id]
        home_won = game["home_score"] > game["away_score"]
        bases = (("1" if pd.notna(play.first_base) else "_")
                 + ("2" if pd.notna(play.second_base) else "_")
                 + ("3" if pd.notna(play.third_base) else "_"))
        half = "bottom" if play.batting_team_id == game["home_team_id"] else "top"
        diff = int(play.home_score_before - play.away_score_before)
        wp_home = model.win_probability(play.inning, half, int(play.outs_before), bases, diff)
        rows.append({
            "game_id": play.game_id,
            "sequence": play.sequence,
            "inning": play.inning,
            "half": half,
            "outs": int(play.outs_before),
            "bases": bases,
            "diff": diff,
            "batting_is_home": half == "bottom",
            "loser_is_home": not home_won,
            # The eventual loser's win probability at this moment.
            "loser_wp": wp_home if not home_won else 1 - wp_home,
            "winner": game["home_team_name"] if home_won else game["away_team_name"],
            "loser": game["away_team_name"] if home_won else game["home_team_name"],
            "final": f'{int(game["away_score"])}-{int(game["home_score"])}',
            "date": game["game_date"],
            "batter": play.batter_name,
            "pitcher": play.pitcher_name,
            "runs": play.runs_scored,
            # The losing side's own miscues, so a collapse is not laid entirely
            # at the pitcher's feet.
            "error": bool(ERROR.search(str(play.narrative or ""))),
            "play_kind": play.play_kind,
            "narrative": play.narrative,
        })
    frame = pd.DataFrame(rows)
    # The swing a play caused is the move from the state before it to the state
    # before the next play. The last play of a game runs to the settled result,
    # which for the losing team is zero.
    following = frame.groupby("game_id")["loser_wp"].shift(-1)
    frame["swing"] = following.fillna(0.0) - frame["loser_wp"]
    return frame


BASE_LABEL = {"___": "empty", "1__": "1st", "_2_": "2nd", "__3": "3rd",
              "12_": "1st & 2nd", "1_3": "1st & 3rd", "_23": "2nd & 3rd", "123": "loaded"}
ORDINAL = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th", 5: "5th", 6: "6th", 7: "7th"}


def describe(row) -> str:
    """The peak moment from the losing team's side, most important first.

    The lead is what matters, then whether they were batting or in the field --
    a lead held while batting still has your own half-inning to add to it, a
    lead held in the field only has outs left to get.
    """
    lead = row["diff"] if row["loser_is_home"] else -row["diff"]
    margin = f"up {lead}" if lead > 0 else ("tied" if lead == 0 else f"down {-lead}")
    batting = (row["half"] == "bottom") == bool(row["loser_is_home"])
    side = "bot" if row["half"] == "bottom" else "top"
    return (f'{margin}, {"batting" if batting else "fielding"} '
            f'{side} {ORDINAL[row["inning"]]}, {row["outs"]} out, '
            f'{BASE_LABEL[row["bases"]]}')


def collapses(frame: pd.DataFrame, peak: pd.DataFrame) -> None:
    """Who was on the mound while each lead was surrendered.

    The window runs from the losing team's peak to the end of the game. Win
    probability lost there splits into what happened while they were in the
    field, which the pitcher of record is part of, and what happened while they
    were batting, which she is not. Errors behind her are counted separately,
    because pitching is one player out of nine.

    This selects on the collapse having happened, so it describes who was
    pitching, not who pitches worst.
    """
    hard = peak[peak["loser_wp"] >= COLLAPSE_THRESHOLD]
    print(f"\n\n=== who was pitching while the lead went "
          f"({len(hard)} games with a peak of {COLLAPSE_THRESHOLD:.2f} or better) ===\n")

    per_pitcher = []
    for game in hard.itertuples():
        window = frame[(frame["game_id"] == game.game_id)
                       & (frame["sequence"] >= game.sequence)]
        fielding = window[window["batting_is_home"] != game.loser_is_home]
        batting = window[window["batting_is_home"] == game.loser_is_home]

        print(f"{game.date}  {game.loser} lost to {game.winner}  "
              f"(peak {game.loser_wp:.3f}: {describe(game._asdict())})")
        print(f"    win probability lost in the field {fielding['swing'].sum():+.3f}, "
              f"at the plate {batting['swing'].sum():+.3f}")

        faced = (fielding[fielding["play_kind"] == "plate_appearance"]
                 .groupby("pitcher", dropna=True)
                 .agg(bf=("sequence", "size"), runs=("runs", "sum"),
                      errors=("error", "sum")))
        # Charge every play she was on the mound for, not only plate appearances.
        faced["wp"] = fielding.groupby("pitcher", dropna=True)["swing"].sum()
        for name, row in faced.sort_values("wp").iterrows():
            tail = (f"   ({int(row['errors'])} error"
                    f"{'s' if row['errors'] != 1 else ''} behind her)"
                    if row["errors"] else "")
            print(f"      {name:22s} {int(row['bf']):2d} BF  {int(row['runs']):2d} R  "
                  f"win prob {row['wp']:+.3f}{tail}")
            per_pitcher.append({"pitcher": name, "team": game.loser, "game": game.game_id,
                                "bf": row["bf"], "runs": row["runs"], "wp": row["wp"],
                                "errors": row["errors"]})
        print()

    tally = (pd.DataFrame(per_pitcher).groupby(["team", "pitcher"])
             .agg(games=("game", "nunique"), bf=("bf", "sum"), runs=("runs", "sum"),
                  wp_lost=("wp", "sum"), errors=("errors", "sum"))
             .sort_values("wp_lost"))
    for column in ("bf", "runs", "errors"):
        tally[column] = tally[column].astype(int)
    print("=== totals across those collapses ===")
    print(tally.round(3).to_string())


def main() -> None:
    pd.set_option("display.width", 250)
    model = Model()
    frame = timeline(model)

    # A game's peak is often shared by consecutive rows holding the same state.
    # Take the earliest, preferring a plate appearance so the narrative names a
    # real event rather than a substitution logged at the same score.
    picks = []
    for _, group in frame.groupby("game_id"):
        best = group[group["loser_wp"] == group["loser_wp"].max()]
        live = best[best["play_kind"] == "plate_appearance"]
        picks.append((live if len(live) else best).iloc[0])
    peak = pd.DataFrame(picks).sort_values("loser_wp", ascending=False)

    table = pd.DataFrame({
        "peak": peak["loser_wp"].round(3),
        "date": peak["date"].astype(str),
        "lost": peak["loser"],
        "beaten by": peak["winner"],
        "final": peak["final"],
        "peak game state": peak.apply(describe, axis=1),
    }).reset_index(drop=True)
    table.index += 1

    print("=== biggest upsets: peak win probability reached by the team that lost ===")
    print("    final is away-home; the game state is from the losing team's side\n")
    print(table.head(12).to_string())

    print("\n=== the play at each peak ===\n")
    for rank, row in enumerate(peak.head(5).itertuples(), 1):
        print(f"{rank}. {row.loser} at {row.loser_wp:.3f} -- {describe(row._asdict())}")
        print(f"   {str(row.narrative)[:110]}")
    print()

    print("=== how often a lead was surrendered ===")
    for threshold in (0.75, 0.85, 0.90, 0.95):
        n = int((peak["loser_wp"] >= threshold).sum())
        print(f"  reached {threshold:.2f} and still lost: {n} of {len(peak)} games")

    biggest = frame.reindex(frame["swing"].abs().sort_values(ascending=False).index).head(8)
    collapses(frame, peak)

    print("\n=== largest single-play swings ===\n")
    for row in biggest.itertuples():
        direction = "toward" if row.swing > 0 else "away from"
        print(f"  {abs(row.swing):.3f} {direction} the eventual loser  {row.date}  "
              f"{row.loser} vs {row.winner}, "
              f"{'bot' if row.half == 'bottom' else 'top'} {row.inning}")
        print(f"         {str(row.narrative)[:100]}")


if __name__ == "__main__":
    main()
