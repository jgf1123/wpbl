"""Read the tidy tables in the scope an analysis asks for.

    from wpbl import tables
    plays = tables.read("plays")

By default the scope is WPBL_GAMES, as everywhere else (parse.OUT_DIR): the
regular season unless WPBL_GAMES=all. Model fits ask for scope="training"
instead -- every game, postseason included, except TRAINING_EXCLUDED -- and
pitcher workload asks for scope="all". A cutoff narrows any of them:

    tables.set_cutoff("j4uofrn55sr4wnlt:2710")

keeps only what had happened before that play -- every earlier game, regular
season or postseason, plus the half-innings of the cutoff game that were
already over. The half-inning in progress is dropped, because every model that
reads these tables counts runs to the end of a half-inning. Only plays,
pitch_events and line_score are split that way; every other per-game table
(box score lines, stints) leaves the cutoff game out, and its final score is
blanked in games.

The postseason gave every team a second team_id. Whenever postseason games are
in scope, each *team_id column is mapped back to the team's regular-season id,
so a team is one team to anything that groups on it.
"""

from __future__ import annotations

import pandas as pd

from wpbl.parse import ALL_DIR, OUT_DIR

HALF_ORDER = {"top": 0, "bottom": 1}
SCOPES = ("default", "all", "training")

# Games kept out of every model fit, with the reason. They stay in the "all"
# scope, so pitcher workload and fatigue still count the pitches thrown in them.
TRAINING_EXCLUDED = {
    # LAQ at NYH, semifinal G3, 14 Sep (15-11). Both bullpens were exhausted --
    # hence the high on-base rate and run total -- so it would skew league and
    # team averages. Excluded by the user's decision (15 Sep). For the same
    # reason it is useful data on how fatigued pitchers perform, so fatigue
    # work reads it through scope="all".
    "r1slo258zh4c0mwg": "semifinal G3, 14 Sep: both bullpens exhausted",
}

_cutoff: tuple[str, int] | None = None


def set_cutoff(spec: str | None) -> None:
    """"GAME_ID:SEQUENCE" -- use only what happened before that play. None clears it."""
    global _cutoff
    if spec is None:
        _cutoff = None
        return
    game_id, _, sequence = spec.partition(":")
    if not game_id or not sequence.isdigit():
        raise SystemExit(f"A cutoff is GAME_ID:SEQUENCE, not {spec!r}")
    _cutoff = (game_id, int(sequence))


def cutoff_play() -> pd.Series | None:
    """The play the cutoff falls before, or None when no cutoff is set."""
    if _cutoff is None:
        return None
    game_id, sequence = _cutoff
    plays = pd.read_parquet(ALL_DIR / "plays.parquet")
    hit = plays[(plays["game_id"] == game_id) & (plays["sequence"] == sequence)]
    if hit.empty:
        raise SystemExit(f"No play {sequence} in game {game_id}")
    return hit.iloc[0]


def _canonical_team_ids(frame: pd.DataFrame) -> pd.DataFrame:
    games = pd.read_parquet(ALL_DIR / "games.parquet")
    names = pd.concat([
        games[["home_team_id", "home_team_name", "is_regular_season"]].set_axis(["id", "name", "reg"], axis=1),
        games[["away_team_id", "away_team_name", "is_regular_season"]].set_axis(["id", "name", "reg"], axis=1)])
    regular_id = names[names["reg"]].drop_duplicates("name").set_index("name")["id"]
    to_regular = names.drop_duplicates("id").set_index("id")["name"].map(regular_id).dropna()
    frame = frame.copy()
    for col in frame.columns:
        if col.endswith("team_id"):
            frame[col] = frame[col].map(to_regular).fillna(frame[col])
    return frame


def read(name: str, scope: str = "default") -> pd.DataFrame:
    """A table in one of three scopes:

    default   WPBL_GAMES (regular season unless set to all) -- descriptive tables
    all       every game, postseason included -- pitcher workload and fatigue
    training  every game except TRAINING_EXCLUDED -- anything estimated from the
              data (run expectancy, the Markov chain, win probability, team
              strength)

    A cutoff, when set, applies on top of any scope.
    """
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}, not {scope!r}")
    frame = _read_unfiltered(name, scope)
    if scope == "training" and "game_id" in frame.columns:
        frame = frame[~frame["game_id"].isin(TRAINING_EXCLUDED)]
    return frame


def _read_unfiltered(name: str, scope: str) -> pd.DataFrame:
    if _cutoff is None:
        source = OUT_DIR if scope == "default" else ALL_DIR
        frame = pd.read_parquet(source / f"{name}.parquet")
        return _canonical_team_ids(frame) if source == ALL_DIR else frame

    frame = pd.read_parquet(ALL_DIR / f"{name}.parquet")
    if "game_id" not in frame.columns:
        return frame
    game_id, _ = _cutoff
    cut = cutoff_play()
    games = pd.read_parquet(ALL_DIR / "games.parquet")
    starts = games.set_index("game_id")["first_pitch_utc"]
    earlier = set(games.loc[games["first_pitch_utc"] < starts[game_id], "game_id"])
    frame = frame[frame["game_id"].isin(earlier | {game_id})].copy()
    in_game = frame["game_id"] == game_id
    # Half-innings in order: top 1 = 2, bottom 1 = 3, top 2 = 4, ...
    now = 2 * int(cut["inning"]) + HALF_ORDER[cut["half"]]

    if name == "games":
        frame.loc[in_game, ["home_score", "away_score"]] = float("nan")
        frame.loc[in_game, "is_final"] = False
    elif name in ("plays", "pitch_events"):
        order = 2 * frame["inning"] + frame["half"].map(HALF_ORDER)
        frame = frame[~in_game | (order < now)]
    elif name == "line_score":
        home = games.set_index("game_id").loc[game_id, "home_team_id"]
        order = 2 * frame["inning"] + (frame["team_id"] == home).astype(int)
        frame = frame[~in_game | (order < now)]
    else:
        frame = frame[~in_game]
    return _canonical_team_ids(frame)
