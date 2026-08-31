"""Pull the WPBL feed to disk.

Raw JSON under data/raw/ is the source of truth: everything downstream is
derived from it, so a reparse never needs a refetch. Runs are incremental --
a game is refetched only when the feed says it changed, or when the copy we
hold is of a game that had not finished yet.

    pixi run scrape              # schedule + boxscores (default)
    pixi run scrape --activity   # also pull TrackMan tracking
    pixi run scrape --force      # refetch everything
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from wpbl import api

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
RAW_DIR = DATA_DIR / "raw"
BOXSCORE_DIR = RAW_DIR / "boxscore"
ACTIVITY_DIR = RAW_DIR / "activity"
MANIFEST_PATH = RAW_DIR / "manifest.json"

# The schedule's status is not a reliable "this game happened" signal: it can sit
# on "Not Started" for hours after a game has actually finished, because the
# upstream provider has not refreshed. So a game whose first pitch has already
# passed gets probed anyway, for this long afterwards.
RECHECK_WINDOW = timedelta(hours=72)

# scheduled_start runs an hour early for the 2026 season (see parse.START_TIME_SHIFT).
START_TIME_SHIFT_H = 1


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: object) -> None:
    """Write atomically so an interrupted run never leaves a half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    tmp.replace(path)


def _load_manifest() -> dict:
    if MANIFEST_PATH.exists():
        return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    return {"boxscore": {}, "activity": {}}


def _is_final(game: dict) -> bool:
    """A schedule row's status is unreliable near first pitch, but 'Final...'
    only ever appears once a game is actually over."""
    return str(game.get("status", "")).startswith("Final")


def _first_pitch(game: dict) -> datetime | None:
    raw = game.get("scheduled_start")
    if not raw:
        return None
    try:
        return (datetime.fromisoformat(raw.replace("Z", "+00:00"))
                + timedelta(hours=START_TIME_SHIFT_H))
    except ValueError:
        return None


def _worth_probing(game: dict) -> bool:
    """Should we ask for this game's box score at all?

    Anything the schedule no longer calls "Not Started" is worth a look. So is a
    game whose first pitch has recently passed, however the schedule labels it --
    that is the case a stale status would otherwise hide.
    """
    if game.get("status") != "Not Started":
        return True
    start = _first_pitch(game)
    if start is None:
        return False
    return timedelta(0) <= datetime.now(timezone.utc) - start <= RECHECK_WINDOW


def _needs_refetch(game: dict, record: dict | None, force: bool) -> bool:
    if force or record is None:
        return True
    # The feed stamps every game with updated_at; a bump means refetch.
    if record.get("source_updated_at") != game.get("updated_at"):
        return True
    # We only ever stop refetching a game once we hold a completed copy.
    return not record.get("complete", False)


def scrape_games() -> list[dict]:
    payload = api.get_games()
    _write_json(RAW_DIR / "games.json", payload)
    games = payload["games"]
    print(f"schedule: {len(games)} games -> {RAW_DIR / 'games.json'}")
    return games


def scrape_boxscores(games: list[dict], manifest: dict, force: bool) -> None:
    records = manifest.setdefault("boxscore", {})
    fetched = skipped = failed = empty = 0

    for game in games:
        game_id = game["game_id"]
        if not _needs_refetch(game, records.get(game_id), force):
            skipped += 1
            continue
        if not _worth_probing(game):
            skipped += 1
            continue

        try:
            payload = api.get_boxscore(game_id)
        except api.ApiError as exc:
            print(f"  ! {game_id} boxscore: {exc}", file=sys.stderr)
            failed += 1
            continue

        box = payload.get("boxscore", {})
        if not (box.get("plays") or box.get("teams", [{}])[0].get("players")):
            # Probed a game the feed has not posted yet: nothing to store.
            print(f"  . {game_id} no data yet (feed says {box.get('game_status')!r},"
                  f" last refreshed {box.get('source_updated_at')})")
            empty += 1
            continue

        _write_json(BOXSCORE_DIR / f"{game_id}.json", payload)
        records[game_id] = {
            "fetched_at": _now(),
            "source_updated_at": game.get("updated_at"),
            # status.complete is the reliable "this game is over" signal.
            "complete": bool(box.get("status", {}).get("complete")),
            "plays": len(box.get("plays") or []),
        }
        fetched += 1
        print(f"  + {game_id} {game['away_team_name']} @ {game['home_team_name']}"
              f" ({records[game_id]['plays']} plays)")

    print(f"boxscores: {fetched} fetched, {skipped} skipped, "
          f"{empty} probed-but-empty, {failed} failed")


def scrape_activity(games: list[dict], manifest: dict, force: bool) -> None:
    records = manifest.setdefault("activity", {})
    fetched = skipped = 0

    for game in games:
        game_id = game["game_id"]
        if not _is_final(game):
            continue
        record = records.get(game_id)
        # Tracking exists for only a couple of games and is never backfilled
        # for a game already final, so a completed pull is final too.
        if record and not force and record.get("complete"):
            skipped += 1
            continue

        try:
            events = api.get_activity(game_id)
        except api.ApiError as exc:
            print(f"  ! {game_id} activity: {exc}", file=sys.stderr)
            continue

        _write_json(ACTIVITY_DIR / f"{game_id}.json", {"activity": events})
        records[game_id] = {"fetched_at": _now(), "events": len(events), "complete": True}
        fetched += 1
        if events:
            print(f"  + {game_id} {len(events)} tracking events")

    print(f"activity: {fetched} fetched, {skipped} skipped")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activity", action="store_true",
                        help="also pull TrackMan tracking (sparse; off by default)")
    parser.add_argument("--force", action="store_true",
                        help="refetch even when the feed says nothing changed")
    args = parser.parse_args()

    manifest = _load_manifest()
    games = scrape_games()
    scrape_boxscores(games, manifest, args.force)
    if args.activity:
        scrape_activity(games, manifest, args.force)

    manifest["updated_at"] = _now()
    _write_json(MANIFEST_PATH, manifest)


if __name__ == "__main__":
    main()
