"""Turn the raw WPBL JSON into tidy tables.

Reads only from data/raw/ and writes parquet to data/tables/, so this can be
rerun freely without touching the network.

    pixi run build

Tables
    games            one row per scheduled game
    team_games       one row per team per game, with the box score totals
    line_score       runs by inning
    batting          player-game hitting lines
    pitching         player-game pitching lines, starter/reliever tagged
    pitching_stints  one row per continuous run on the mound, with entry context
    fielding         player-game fielding lines
    players          player dimension
    plays            play-by-play, with running score and pitcher/batter ids
    pitch_events     one row per pitch
    tracking         TrackMan events (only a couple of games have any)
"""

from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"

# The build writes every table twice. ALL_DIR holds every game the feed has --
# regular season and postseason -- and is what validate.py checks against the
# raw JSON. REGULAR_DIR holds the regular season alone. Analyses read OUT_DIR,
# which is the regular season unless WPBL_GAMES=all is set: published work so
# far is regular-season only, and a playoff game must not slip into it just
# because a later scrape picked one up.
ALL_DIR = DATA_DIR / "tables"
REGULAR_DIR = ALL_DIR / "regular"
GAME_SCOPES = {"regular": REGULAR_DIR, "all": ALL_DIR}
GAMES = os.environ.get("WPBL_GAMES", "regular")
if GAMES not in GAME_SCOPES:
    raise SystemExit(f"WPBL_GAMES must be one of {', '.join(GAME_SCOPES)}, not {GAMES!r}")
OUT_DIR = GAME_SCOPES[GAMES]

LEAGUE_TZ = ZoneInfo("America/Chicago")

# The feed reports scheduled_start an hour before the real first pitch for the
# 2026 season. It is a flat shift -- the whole season is Central with no DST
# change. Revisit for any later season before trusting it.
# The 2026 regular season ran 1 August to 6 September: 30 games, every pair of
# teams meeting five times. The postseason followed from 9 September under its
# own season_id, and those games do carry game_type='postSeason' (the feed still
# ignores any game_type filter you send it). Analyses use both: all four teams
# made the playoffs, so a postseason game is the same league playing itself, not
# a subset selected for quality. The two flags keep them separable for anything
# that needs one alone, and validate.py fails loudly on a game that is neither.
REGULAR_SEASON_END = date(2026, 9, 6)

START_TIME_SHIFT = {2026: timedelta(hours=1)}

# The feed's pitch_events.type mislabels two codes: it calls "P" a pitchout and
# "K" unknown. Checked against outcomes across all 24 games -- every batted-ball
# play ends on P, and strikeouts end on S (swinging) or K (called). validate.py
# reasserts this on every build.
PITCH_CODES = {
    "B": ("ball", False, False),
    "K": ("called_strike", True, False),
    "S": ("swinging_strike", True, False),
    "F": ("foul", True, False),
    "P": ("in_play", True, True),
    "H": ("hit_by_pitch", False, False),
}

# Games whose pitch strings the feed recorded incompletely, so the pitch counts
# built from them are too low. validate.py keeps them out of the pitch-code rate;
# estimate_pitch_counts() fills in their cut-off plate appearances.
PITCH_STRING_GAPS = {"ucwyhv1ki318nni5"}    # SF-BOS semifinal G1, 9 Sep

# event_type "unknown" lumps real plate appearances in with roster moves and
# baserunning notes. These patterns split them back apart off the narrative.
NON_PA_PATTERNS = [
    ("pitching_change", re.compile(r"\bto p(?:\s+for\b|\.\s*$)")),
    # A fielding move names the position and then stops, or hands off with
    # "for". Requiring that keeps "infield fly to ss (0-0)" a plate appearance.
    ("substitution", re.compile(
        r"\bpinch (?:hit|ran)\b|\bto (?:1b|2b|3b|ss|lf|cf|rf|c|dh)(?:\s+for\b|\.\s*$)")),
    ("pickoff", re.compile(r"pickoff", re.I)),
    ("balk", re.compile(r"\bbalk\b", re.I)),
    ("placed_runner", re.compile(r"\bplaced on (?:first|second|third)\b")),
]

# Checked only after the plate-appearance test, since a real plate appearance
# often ends by describing the runners it moved.
BASERUNNING_ONLY = re.compile(r"\b(advanced to|scored)\b")

BASERUNNING_EVENTS = {"stolen_base", "caught_stealing", "wild_pitch", "passed_ball"}

# Only a completed trip to the plate carries a ball-strike count. That is what
# separates "Sarah Edwards out at third p to 3b, picked off." from a real out,
# and it is what makes the play-by-play tie to batters faced in all 48
# team-games.
COUNT_IN_NARRATIVE = re.compile(r"\(\d-\d")

# Plate appearances the feed leaves as "unknown": reaching on an error or on
# interference, and infield flies.
PA_IN_UNKNOWN = re.compile(r"\breached\b|\binfield fly\b")

RATE_FIELDS = {"obp", "ops", "slg", "whip", "era"}
DECISION_FIELDS = {"win", "loss", "save"}
TEXT_FIELDS = {"ip"} | RATE_FIELDS | DECISION_FIELDS


# Misspellings confirmed by hand, fixed in every raw string -- roster names,
# base runners, narratives -- before anything reads the box score, so no table
# or column can disagree with another. New York's O'Sullivan is "Catherine"
# throughout semifinal G2 and "Claire" everywhere else. Her name is Claire.
RAW_NAME_FIXES = {
    "Catherine O'Sullivan": "Claire O'Sullivan",
}


def _fix_names(value):
    if isinstance(value, str):
        for wrong, right in RAW_NAME_FIXES.items():
            value = value.replace(wrong, right)
        return value
    if isinstance(value, list):
        return [_fix_names(v) for v in value]
    if isinstance(value, dict):
        return {k: _fix_names(v) for k, v in value.items()}
    return value


def modal_name(series: pd.Series):
    """The most-used spelling of a name.

    The feed spells at least one player two ways under a single id ("Maggie Fox"
    once, "Maggie Foxx" twelve times), so the canonical name is the one it uses
    most rather than whichever happens to sort first.
    """
    counts = series.dropna().value_counts()
    return counts.index[0] if len(counts) else None


def _num(value):
    """Box score stats arrive as strings and are omitted entirely when zero."""
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _stat_columns(block: dict, prefix: str, schema: list[str]) -> dict:
    """Flatten one stat dict against a fixed schema.

    A missing key means zero for counting stats -- the feed omits them rather
    than sending 0 -- but stays null for rates and decisions, where absent
    genuinely means "not applicable".
    """
    out = {}
    for key in schema:
        raw = block.get(key)
        if key in TEXT_FIELDS:
            out[f"{prefix}{key}"] = raw or None
        else:
            out[f"{prefix}{key}"] = _num(raw) if raw is not None else 0.0
    return out


def ip_to_outs(ip: str | None) -> int | None:
    """'5.2' means five and two-thirds innings, not five point two."""
    if not ip:
        return None
    try:
        whole, _, frac = str(ip).partition(".")
        outs = int(whole) * 3
        if frac:
            outs += int(frac[0])
        return outs
    except ValueError:
        return None


def _schema(boxes: list[dict], section: str, source: str) -> list[str]:
    """Union of keys seen anywhere, so sparse fields still get a column."""
    keys: set[str] = set()
    for box in boxes:
        for team in box["teams"]:
            if source == "player":
                for player in team["players"]:
                    if player.get(section):
                        keys.update(player[section])
            else:
                keys.update(team["totals"][section])
    return sorted(keys)


def build_id_index(boxes: dict) -> dict[tuple[str, str], str]:
    """Map (team_id, player name) -> player id, pooled across every game.

    About 30% of box score player rows come back with an empty id, and which
    rows lose it varies game to game. Names are unique within a team and no name
    ever resolves to two different ids, so a player who has an id in any game
    can be repaired in the games where she doesn't. Pitching lines are never
    affected -- only hitters and bench players lose ids.
    """
    index: dict[tuple[str, str], str] = {}
    for box in boxes.values():
        for team in box["teams"]:
            for player in team["players"]:
                if player["id"]:
                    index[(team["id"], player["name"])] = player["id"]
    return index


def build_person_index(boxes: dict, id_index: dict) -> dict[str, str]:
    """Map every player_id to a stable person_id that survives a trade.

    Neither key alone identifies a person. The feed mints a *new* player_id when
    a player changes teams (three players so far), and it has spelled one
    player's name two ways under a single id. So union player_ids that share an
    id and player_ids that share a name, and take the lexicographically smallest
    id in each component as the person_id -- stable across rebuilds.
    """
    parent: dict[str, str] = {}

    def find(x: str) -> str:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    by_name: dict[str, list[str]] = {}
    for box in boxes.values():
        for team in box["teams"]:
            for player in team["players"]:
                player_id, _ = _resolve_id(id_index, team["id"], player["name"], player["id"])
                find(player_id)
                by_name.setdefault(player["name"], []).append(player_id)
    for ids in by_name.values():
        for other in ids[1:]:
            union(ids[0], other)
    return {player_id: find(player_id) for player_id in parent}


def _resolve_id(index: dict, team_id: str, name: str, raw_id: str | None):
    """Return (player_id, source). Never invents an id for a real player."""
    if raw_id:
        return raw_id, "feed"
    recovered = index.get((team_id, name))
    if recovered:
        return recovered, "recovered"
    # Only ever the handful of rostered players who never took the field, so
    # they carry no stats -- a stable synthetic key keeps grouping honest.
    return f"unknown:{team_id}:{name}", "unresolved"


def _classify_play(play: dict) -> str:
    """Sort a play row into a plate appearance or one of the other things the
    feed files under the same list: roster moves, pickoffs, balks, and outs made
    on the bases."""
    event = play.get("event_type") or "unknown"
    narrative = (play.get("narrative") or "").strip()
    if not narrative:
        # One game lost the narrative and batter name on 14 plays but kept the
        # pitch sequences. They are real trips to the plate with an unrecorded
        # outcome, and counting them is what makes that game's batters-faced
        # tie. A blank row that still names its batter is a stray, not a PA.
        return "empty" if play.get("batter_name") else "plate_appearance_unknown"
    has_count = bool(COUNT_IN_NARRATIVE.search(narrative))

    if event != "unknown":
        if event in BASERUNNING_EVENTS:
            return "baserunning"
        # An out with no count was made on the bases, not at the plate.
        return "plate_appearance" if has_count else "baserunning_out"

    # A substitution row whose incoming player's name is missing entirely.
    if narrative.startswith("/"):
        return "substitution"
    for label, pattern in NON_PA_PATTERNS:
        if pattern.search(narrative):
            return label
    if has_count and PA_IN_UNKNOWN.search(narrative.split(";")[0]):
        return "plate_appearance"
    if BASERUNNING_ONLY.search(narrative):
        return "baserunning"
    return "other"


def load_raw():
    games = json.loads((RAW_DIR / "games.json").read_text(encoding="utf-8"))["games"]
    boxes, tracking = {}, {}
    for path in sorted((RAW_DIR / "boxscore").glob("*.json")):
        boxes[path.stem] = _fix_names(json.loads(path.read_text(encoding="utf-8"))["boxscore"])
    for path in sorted((RAW_DIR / "activity").glob("*.json")):
        events = json.loads(path.read_text(encoding="utf-8"))["activity"]
        if events:
            tracking[path.stem] = events
    return games, boxes, tracking


def build_games(games: list[dict], boxes: dict, tracking: dict) -> pd.DataFrame:
    rows = []
    for game in games:
        game_id = game["game_id"]
        box = boxes.get(game_id)
        start = pd.Timestamp(game["scheduled_start"])
        shift = START_TIME_SHIFT.get(start.year, timedelta(0))
        first_pitch = start + shift
        score = (game.get("presto_data") or {}).get("score") or {}
        rows.append({
            "game_id": game_id,
            "season_id": game.get("season_id"),
            "game_type": game.get("game_type"),
            "status": game.get("status"),
            "is_final": str(game.get("status", "")).startswith("Final"),
            "is_complete": bool(box and box.get("status", {}).get("complete")),
            "counts_in_standings": game.get("counts_in_standings"),
            "venue": game.get("venue") or None,
            "scheduled_start_raw_utc": start,
            "first_pitch_utc": first_pitch,
            "first_pitch_local": first_pitch.tz_convert(LEAGUE_TZ),
            "game_date": first_pitch.tz_convert(LEAGUE_TZ).date(),
            "start_time_shift_applied_h": shift.total_seconds() / 3600,
            "home_team_id": game.get("home_team_id"),
            "home_team_name": game.get("home_team_name"),
            "away_team_id": game.get("away_team_id"),
            "away_team_name": game.get("away_team_name"),
            "home_score": _num(score.get("home")),
            "away_score": _num(score.get("away")),
            "innings": max((len(t["line"]) for t in box["teams"]), default=None) if box else None,
            "n_plays": len(box["plays"]) if box else 0,
            "has_boxscore": box is not None,
            "has_tracking": game_id in tracking,
            "completed_at": pd.Timestamp(game["completed_at"]) if game.get("completed_at") else pd.NaT,
            "source_updated_at": pd.Timestamp(game["updated_at"]) if game.get("updated_at") else pd.NaT,
        })
    df = pd.DataFrame(rows)

    # Phantom duplicates: a stale never-played copy sitting beside the real game.
    matchup = ["game_date", "home_team_id", "away_team_id"]
    dupes = df.duplicated(matchup, keep=False)
    df["is_phantom_duplicate"] = dupes & ~df["is_final"]
    df["is_regular_season"] = (
        (df["game_type"] == "regular")
        & (pd.to_datetime(df["game_date"]).dt.date <= REGULAR_SEASON_END))
    df["is_postseason"] = (
        (df["game_type"] == "postSeason")
        & (pd.to_datetime(df["game_date"]).dt.date > REGULAR_SEASON_END))
    return df.sort_values("first_pitch_utc").reset_index(drop=True)


def build_team_and_player_tables(boxes: dict, games_df: pd.DataFrame, id_index: dict):
    box_list = list(boxes.values())
    schemas = {
        "hitting": _schema(box_list, "hitting", "player"),
        "pitching": _schema(box_list, "pitching", "player"),
        "fielding": _schema(box_list, "fielding", "player"),
        "batting_tot": _schema(box_list, "batting", "totals"),
        "pitching_tot": _schema(box_list, "pitching", "totals"),
        "fielding_tot": _schema(box_list, "fielding", "totals"),
    }
    game_meta = games_df.set_index("game_id")[["game_date"]].to_dict("index")

    team_rows, line_rows, bat_rows, pit_rows, fld_rows, player_rows = [], [], [], [], [], []

    for game_id, box in boxes.items():
        game_date = game_meta.get(game_id, {}).get("game_date")
        sides = {t["side"]: t for t in box["teams"]}
        for side, team in sides.items():
            opp = sides["home" if side == "away" else "away"]
            base = {
                "game_id": game_id,
                "game_date": game_date,
                "team_id": team["id"],
                "team_name": team["name"],
                "side": side,
                "is_home": side == "home",
                "opponent_team_id": opp["id"],
                "opponent_team_name": opp["name"],
            }
            totals = team["totals"]
            team_rows.append({
                **base,
                "runs": totals.get("runs"),
                "hits": totals.get("hits"),
                "errors": totals.get("errors"),
                "left_on_base": totals.get("left_on_base"),
                "opponent_runs": opp["totals"].get("runs"),
                "won": totals.get("runs", 0) > opp["totals"].get("runs", 0),
                "record": team.get("record"),
                **_stat_columns(totals["batting"], "bat_", schemas["batting_tot"]),
                **_stat_columns(totals["pitching"], "pit_", schemas["pitching_tot"]),
                **_stat_columns(totals["fielding"], "fld_", schemas["fielding_tot"]),
            })

            for entry in team["line"]:
                line_rows.append({**base, "inning": entry["inning"], "runs": entry["runs"]})

            # Match the starting lineup on name alone. A player's own position
            # field lists every position she played that game ("lf/p"), so
            # matching on it would miss anyone who moved mid-game. The feed's
            # starters list is the lineup as posted: 9, or 10 when a DH is used
            # and the pitcher is carried at spot 10.
            lineup = {s["name"]: s for s in team.get("starters") or []}
            for player in team["players"]:
                player_id, id_source = _resolve_id(id_index, team["id"], player["name"], player["id"])
                ident = {
                    **base,
                    "player_id": player_id,
                    "player_id_source": id_source,
                    "player_name": player["name"],
                    "uniform": player.get("uniform") or None,
                    "position": player.get("position") or None,
                    "spot": _num(player.get("spot")),
                    "bats": player.get("bats") or None,
                    "throws": player.get("throws") or None,
                }
                player_rows.append({
                    "player_id": player_id,
                    "player_id_source": id_source,
                    "player_name": player["name"],
                    "short_name": player.get("short_name"),
                    "team_id": team["id"],
                    "team_name": team["name"],
                    "bats": player.get("bats") or None,
                    "throws": player.get("throws") or None,
                    "profile_url": player.get("profile_url") or None,
                    "game_id": game_id,
                })
                if player.get("hitting"):
                    posted = lineup.get(player["name"])
                    bat_rows.append({
                        **ident,
                        "in_starting_lineup": posted is not None,
                        "lineup_spot": _num(posted["spot"]) if posted else None,
                        "lineup_position": posted["position"] if posted else None,
                        **_stat_columns(player["hitting"], "", schemas["hitting"]),
                    })
                if player.get("fielding"):
                    fld_rows.append({**ident, **_stat_columns(player["fielding"], "", schemas["fielding"])})
                if player.get("pitching"):
                    pitching = player["pitching"]
                    appear = _num(pitching.get("appear"))
                    is_starter = bool(pitching.get("gs"))
                    pit_rows.append({
                        **ident,
                        "appear_order": int(appear) if appear else None,
                        "is_starter": is_starter,
                        "role": "SP" if is_starter else "RP",
                        "ip_outs": ip_to_outs(pitching.get("ip")),
                        "got_win": bool(pitching.get("win")),
                        "got_loss": bool(pitching.get("loss")),
                        "got_save": bool(pitching.get("save")),
                        **_stat_columns(pitching, "", schemas["pitching"]),
                    })

    def first_known(series: pd.Series):
        known = series.dropna()
        return known.iloc[0] if len(known) else None

    players = (pd.DataFrame(player_rows)
               .sort_values("game_id")
               .groupby("player_id", as_index=False)
               .agg(player_name=("player_name", modal_name),
                    short_name=("short_name", first_known),
                    team_id=("team_id", "last"), team_name=("team_name", "last"),
                    # The feed contradicts itself on handedness for 10 of 80
                    # players (Jordan Eyster is R/R in some games and L/L in
                    # others), so take the most-used value rather than the
                    # first game's, exactly as for a misspelled name.
                    bats=("bats", modal_name), throws=("throws", modal_name),
                    profile_url=("profile_url", first_known),
                    id_ever_from_feed=("player_id_source", lambda s: (s == "feed").any()),
                    games=("game_id", "nunique")))

    return (pd.DataFrame(team_rows), pd.DataFrame(line_rows), pd.DataFrame(bat_rows),
            pd.DataFrame(pit_rows), pd.DataFrame(fld_rows), players)


def _runs_on_play(play: dict) -> int:
    """Runs that actually crossed the plate on this play.

    The feed's runs_scored counts only runners other than the batter, so a solo
    home run comes back as 0. Adding the batter's own run on a home run
    reconciles 338 of the 340 half-innings against the line score; the two
    exceptions are a lost half-inning and a truncated narrative, which the
    half-inning anchoring below absorbs.
    """
    runs = play.get("runs_scored") or 0
    if play.get("event_type") == "home_run":
        runs += 1
    return runs


def _line_score_by_inning(box: dict) -> dict[tuple[str, int], int]:
    return {(team["id"], entry["inning"]): entry["runs"]
            for team in box["teams"] for entry in team["line"]}


def build_plays(boxes: dict, games_df: pd.DataFrame, id_index: dict):
    game_meta = games_df.set_index("game_id")["game_date"].to_dict()
    play_rows, pitch_rows = [], []

    def resolve(team_id, name):
        # Play rows name people but never id them. Go through the league-wide
        # index so a blank id in this game's roster still resolves.
        if not name:
            return None
        return id_index.get((team_id, name))

    for game_id, box in boxes.items():
        sides = {t["side"]: t for t in box["teams"]}
        home_id, away_id = sides["home"]["id"], sides["away"]["id"]

        # The line score is the authoritative run total per half-inning, so the
        # running score is re-anchored to it at every half-inning boundary and
        # only ever moves on the feed's own per-play counts within one.
        line = _line_score_by_inning(box)
        completed = {home_id: 0, away_id: 0}
        current_half: tuple | None = None
        in_half = 0

        for play in box["plays"]:
            batting_id = play.get("team_id") or ""
            pitching_id = away_id if batting_id == home_id else home_id
            kind = _classify_play(play)
            sequence = play.get("pitch_sequence") or ""
            runs = _runs_on_play(play)

            half = (play.get("inning"), play.get("half"), batting_id)
            if half != current_half:
                if current_half is not None:
                    prev_inning, _, prev_batting = current_half
                    completed[prev_batting] = (completed.get(prev_batting, 0)
                                               + line.get((prev_batting, prev_inning), 0))
                current_half, in_half = half, 0
            fielding_score = completed.get(pitching_id, 0)
            batting_score = completed.get(batting_id, 0) + in_half
            in_half += runs

            row = {
                "game_id": game_id,
                "game_date": game_meta.get(game_id),
                "sequence": play.get("sequence"),
                "inning": play.get("inning"),
                "half": play.get("half"),
                "batting_team_id": batting_id or None,
                "pitching_team_id": pitching_id if batting_id else None,
                "batter_name": play.get("batter_name") or None,
                "batter_id": resolve(batting_id, play.get("batter_name")),
                "pitcher_name": play.get("pitcher_name") or None,
                "pitcher_id": resolve(pitching_id, play.get("pitcher_name")),
                "outs_before": play.get("outs"),
                "first_base": play.get("first_base") or None,
                "second_base": play.get("second_base") or None,
                "third_base": play.get("third_base") or None,
                "runners_on": len(play.get("bases_occupied") or []),
                "bases_loaded": play.get("bases_loaded"),
                "event_type": play.get("event_type"),
                "play_kind": kind,
                # Includes the plays whose outcome the feed lost, so this ties
                # to batters faced; filter on play_kind to exclude them.
                "is_plate_appearance": kind.startswith("plate_appearance"),
                "is_hit": play.get("is_hit"),
                "is_scoring_play": play.get("is_scoring_play"),
                "runs_scored": runs,
                "runs_scored_feed": play.get("runs_scored") or 0,
                "narrative": play.get("narrative") or None,
                "pitch_sequence": sequence or None,
                "n_pitches": len(sequence),
                "balls": play.get("balls"),
                "strikes": play.get("strikes"),
                "fouls": play.get("fouls"),
                "batting_team_score_before": batting_score,
                "pitching_team_score_before": fielding_score,
                "home_score_before": batting_score if batting_id == home_id else fielding_score,
                "away_score_before": batting_score if batting_id == away_id else fielding_score,
            }
            play_rows.append(row)

            for pitch in play.get("pitch_events") or []:
                code = pitch.get("code")
                label, is_strike, in_play = PITCH_CODES.get(code, (None, None, None))
                pitch_rows.append({
                    "game_id": game_id,
                    "play_sequence": play.get("sequence"),
                    "pitch_number": pitch.get("sequence"),
                    "inning": play.get("inning"),
                    "half": play.get("half"),
                    "pitcher_name": play.get("pitcher_name") or None,
                    "pitcher_id": resolve(pitching_id, play.get("pitcher_name")),
                    "batter_name": play.get("batter_name") or None,
                    "batter_id": resolve(batting_id, play.get("batter_name")),
                    "code": code,
                    "result": label,
                    "is_strike": is_strike,
                    "in_play": in_play,
                    "feed_type": pitch.get("type"),
                    "feed_description": pitch.get("description"),
                })

    return pd.DataFrame(play_rows), pd.DataFrame(pitch_rows)


def build_stints(plays: pd.DataFrame, pitching: pd.DataFrame) -> pd.DataFrame:
    """One row per continuous run on the mound, with the game state at entry.

    Derived from the play-by-play rather than the box score, so it captures when
    a reliever came in and what they walked into.
    """
    work = plays.dropna(subset=["pitcher_name"]).sort_values(["game_id", "sequence"]).copy()
    key = ["game_id", "pitching_team_id"]
    changed = work.groupby(key)["pitcher_name"].transform(lambda s: s.ne(s.shift()))
    work["stint_id"] = changed.groupby([work[k] for k in key]).cumsum()

    stints = work.groupby(key + ["stint_id", "pitcher_name", "pitcher_id"], dropna=False).agg(
        first_sequence=("sequence", "min"),
        last_sequence=("sequence", "max"),
        entered_inning=("inning", "first"),
        entered_half=("half", "first"),
        exited_inning=("inning", "last"),
        entered_outs=("outs_before", "first"),
        entered_runners_on=("runners_on", "first"),
        plays=("sequence", "count"),
        batters_faced=("is_plate_appearance", "sum"),
        pitches=("n_pitches", "sum"),
        pitches_est=("n_pitches_est", "sum"),
        runs_allowed=("runs_scored", "sum"),
        hits_allowed=("is_hit", "sum"),
        entry_pitching_score=("pitching_team_score_before", "first"),
        entry_batting_score=("batting_team_score_before", "first"),
    ).reset_index()

    stints["entry_score_diff"] = stints["entry_pitching_score"] - stints["entry_batting_score"]
    stints["is_starter"] = stints["stint_id"] == 1
    roles = pitching.set_index(["game_id", "player_id"])["role"].to_dict()
    stints["box_role"] = [roles.get((g, p)) for g, p in zip(stints["game_id"], stints["pitcher_id"])]
    return stints.sort_values(["game_id", "pitching_team_id", "stint_id"]).reset_index(drop=True)


def _pitch_string_complete(sequence: str, event_type: str) -> bool:
    """Whether a plate appearance's pitch string can have produced its result:
    a walk needs four balls ending on one, a strikeout a third strike, a hit
    batter an H, and anything else a ball put in play (P)."""
    if not sequence:
        return False
    if event_type == "walk":
        return sequence.count("B") == 4 and sequence[-1] == "B"
    if event_type == "strikeout":
        strikes = 0
        for code in sequence:
            if code in "KS" or (code == "F" and strikes < 2):
                strikes += 1
        return sequence[-1] in "KS" and strikes >= 3
    if event_type == "hit_by_pitch":
        return sequence[-1] == "H"
    return sequence[-1] == "P"


def estimate_pitch_counts(plays: pd.DataFrame, pitching: pd.DataFrame) -> None:
    """Add estimated pitch counts beside the feed's, in place.

    In PITCH_STRING_GAPS games the feed cut pitch strings short, so a string's
    length is only a floor on the pitches thrown. A plate appearance whose
    string cannot have produced its result is taken as cut off, and its count
    is estimated as the mean length of complete strings elsewhere with the same
    kind of result (walk, strikeout, hit batter, in play) and at least as many
    pitches as were recorded. Every other plate appearance keeps its own count.

    plays.n_pitches_est / n_pitches_estimated and pitching.pitches_est hold the
    result (build_stints sums n_pitches_est into pitching_stints.pitches_est);
    n_pitches and pitches stay as the feed sent them, which is what validate.py
    checks.
    """
    kind = plays["event_type"].where(
        plays["event_type"].isin(["walk", "strikeout", "hit_by_pitch"]), "in_play")
    sequence = plays["pitch_sequence"].fillna("")
    real_pa = plays["play_kind"] == "plate_appearance"
    complete = pd.Series([_pitch_string_complete(s, e) for s, e in
                          zip(sequence, plays["event_type"])], index=plays.index)
    reference = pd.DataFrame({"kind": kind, "n": plays["n_pitches"]})[
        real_pa & complete & ~plays["game_id"].isin(PITCH_STRING_GAPS)]

    cut_off = real_pa & ~complete & plays["game_id"].isin(PITCH_STRING_GAPS)
    estimate = plays["n_pitches"].astype(float)
    for i in plays.index[cut_off]:
        pool = reference.loc[(reference["kind"] == kind[i])
                             & (reference["n"] >= max(plays.at[i, "n_pitches"], 1)), "n"]
        if len(pool):
            estimate[i] = pool.mean()
    plays["n_pitches_est"] = estimate
    plays["n_pitches_estimated"] = cut_off

    added = (plays.assign(extra=estimate - plays["n_pitches"])
             .groupby(["game_id", "pitcher_id"])["extra"].sum())
    pitching["pitches_est"] = (pitching["pitches"] + [
        added.get((g, p), 0.0) for g, p in zip(pitching["game_id"], pitching["player_id"])]
    ).round()


def build_tracking(tracking: dict) -> pd.DataFrame:
    rows = [event for events in tracking.values() for event in events]
    return pd.json_normalize(rows) if rows else pd.DataFrame()


def main() -> None:
    games, boxes, tracking = load_raw()

    id_index = build_id_index(boxes)
    person_index = build_person_index(boxes, id_index)
    games_df = build_games(games, boxes, tracking)
    team_games, line_score, batting, pitching, fielding, players = \
        build_team_and_player_tables(boxes, games_df, id_index)
    plays, pitch_events = build_plays(boxes, games_df, id_index)
    estimate_pitch_counts(plays, pitching)
    stints = build_stints(plays, pitching)

    # player_id is per-team: a trade mints a new one. person_id is the stable
    # key for "the same human", so season-long aggregates must group on it.
    for frame in (batting, pitching, fielding, players):
        frame.insert(0, "person_id", frame["player_id"].map(person_index))
    canonical = players.groupby("person_id")["player_name"].agg(modal_name)
    for frame in (batting, pitching, fielding, players):
        frame.insert(1, "person_name", frame["person_id"].map(canonical))

    # Handedness belongs to the person, not to the per-team player_id, so a
    # traded player carries one value across both of her ids. Every per-game
    # row is stamped with it as well, so a matchup can be read off batting or
    # pitching alone.
    for column in ("bats", "throws"):
        hand = players.groupby("person_id")[column].agg(modal_name)
        for frame in (batting, pitching, fielding, players):
            frame[column] = frame["person_id"].map(hand)

    # A handful of play rows come through with no narrative and no event at all
    # -- one game is missing a whole half-inning. Flag it rather than hide it.
    blanks = (plays[plays["play_kind"].isin(["empty", "plate_appearance_unknown"])]
              .groupby("game_id").size())
    games_df["n_blank_plays"] = games_df["game_id"].map(blanks).fillna(0).astype(int)

    tables = {
        "games": games_df,
        "team_games": team_games,
        "line_score": line_score,
        "batting": batting,
        "pitching": pitching,
        "pitching_stints": stints,
        "fielding": fielding,
        "players": players,
        "plays": plays,
        "pitch_events": pitch_events,
        "tracking": build_tracking(tracking),
    }
    regular = set(games_df.loc[games_df["is_regular_season"], "game_id"])
    for directory, keep in ((ALL_DIR, None), (REGULAR_DIR, regular)):
        directory.mkdir(parents=True, exist_ok=True)
        print(f"\n  data/{directory.relative_to(DATA_DIR).as_posix()}/")
        for name, frame in tables.items():
            # Tables without a game_id -- the player registry -- are the same
            # in both copies; everything per-game is cut to the scope.
            if keep is not None and "game_id" in frame.columns:
                frame = frame[frame["game_id"].isin(keep)]
            if frame.empty:
                print(f"  {name:16s} (empty, skipped)")
                continue
            frame.to_parquet(directory / f"{name}.parquet", index=False)
            print(f"  {name:16s} {len(frame):6d} rows x {len(frame.columns):3d} cols")


if __name__ == "__main__":
    main()
