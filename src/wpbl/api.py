"""Low-level client for the public WPBL stats feed.

Docs: https://sportydolphin.fun/wpbl/api
Base: https://stats.womensprobaseballleague.com/v1  (no key, no signup)

Two things about /games are not in those docs and both bite:

  * It is paginated, defaulting to 50 games. Asking for it plainly returns a
    first page that looks like a complete schedule and is not -- which is what
    hid four finished games in September 2026 until limit/offset paging was
    added here. Always page to exhaustion.
  * A game that has been played can appear under a game_id absent from an
    unpaged response entirely, while the scheduled placeholder stays frozen on
    "Not Started" with its team names blanked.

/games/{id} is likewise undocumented but real, and serves games the schedule
page does not surface; scrape.known_game_ids keeps a persistent union of ids
so discovery can never go backwards.

Stdlib only on purpose -- the scraper must run even in a bare environment.
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://stats.womensprobaseballleague.com/v1"
SITE_URL = "https://stats.womensprobaseballleague.com"
USER_AGENT = "wpbl-research/0.1 (personal analysis; contact jgf1123@gmail.com)"

# Game ids as they appear in the explorer page's own hyperlinks.
GAME_LINK = re.compile(r"/games/([a-z0-9]{16})\b")

# The feed is a small public service run by the league. Be a polite client.
REQUEST_DELAY_S = 0.5
MAX_RETRIES = 4


class ApiError(RuntimeError):
    pass


def get(path: str, params: dict | None = None, *, timeout: int = 60) -> dict:
    """GET a v1 endpoint and return the decoded JSON body.

    Retries on 5xx and transport errors with exponential backoff. A 404 raises
    immediately -- for this feed it means the game has no such resource, which
    callers treat as data ("no tracking for this game"), not as a failure.
    """
    url = f"{BASE_URL}{path}"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"

    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        if attempt:
            time.sleep(2**attempt)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read()
            time.sleep(REQUEST_DELAY_S)
            return json.loads(body)
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 400):
                raise ApiError(f"{exc.code} for {url}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc

    raise ApiError(f"failed after {MAX_RETRIES} attempts: {url}") from last_error


PAGE_SIZE = 200


def get_games() -> dict:
    """The whole schedule, paged to exhaustion.

    The endpoint caps a response well below the season's size, so a single
    unpaged call silently truncates. Paging until a short page comes back is
    the only way to be sure the list is complete.
    """
    games: list[dict] = []
    seen: set[str] = set()
    offset = 0
    while True:
        page = get("/games", {"limit": PAGE_SIZE, "offset": offset})
        rows = page.get("games") or []
        for row in rows:
            if row["game_id"] not in seen:
                seen.add(row["game_id"])
                games.append(row)
        if len(rows) < PAGE_SIZE:
            return {"count": len(games), "games": games}
        offset += PAGE_SIZE


def get_game(game_id: str) -> dict:
    """One game's schedule row, fetched directly rather than via /games.

    Undocumented, but it is what the league's own Game Center page uses, and
    it serves games /games never lists.
    """
    return get(f"/games/{game_id}")


def get_text(url: str, *, timeout: int = 60) -> str:
    """Fetch a page as text, with the same retry behaviour as get()."""
    last_error: Exception | None = None
    for attempt in range(MAX_RETRIES):
        if attempt:
            time.sleep(2**attempt)
        try:
            request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", "replace")
            time.sleep(REQUEST_DELAY_S)
            return body
        except urllib.error.HTTPError as exc:
            if exc.code in (404, 400):
                raise ApiError(f"{exc.code} for {url}") from exc
            last_error = exc
        except (urllib.error.URLError, TimeoutError) as exc:
            last_error = exc
    raise ApiError(f"failed after {MAX_RETRIES} attempts: {url}") from last_error


def get_explorer_game_ids() -> set[str]:
    """Game ids linked from the league's own schedule page.

    Server-rendered, so the ids are in the HTML -- no JavaScript needed. This
    is the only way to find a game that /v1/games has left out.
    """
    return set(GAME_LINK.findall(get_text(f"{SITE_URL}/explorer/games")))


def get_boxscore(game_id: str) -> dict:
    """One game in full: totals, line score, player lines, and play-by-play."""
    return get(f"/games/{game_id}/boxscore")


def get_activity(game_id: str, page_size: int = 1000) -> list[dict]:
    """All TrackMan events for a game, paging until a short page comes back.

    Most games have no tracking at all; that returns an empty list.
    """
    events: list[dict] = []
    offset = 0
    while True:
        page = get(
            f"/games/{game_id}/activity",
            {"limit": page_size, "offset": offset},
        )
        rows = page.get("activity") or []
        events.extend(rows)
        if len(rows) < page_size:
            return events
        offset += page_size
