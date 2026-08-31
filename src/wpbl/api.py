"""Low-level client for the public WPBL stats feed.

Docs: https://sportydolphin.fun/wpbl/api
Base: https://stats.womensprobaseballleague.com/v1  (no key, no signup)

Stdlib only on purpose -- the scraper must run even in a bare environment.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = "https://stats.womensprobaseballleague.com/v1"
USER_AGENT = "wpbl-research/0.1 (personal analysis; contact jgf1123@gmail.com)"

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


def get_games() -> dict:
    """The whole schedule with results."""
    return get("/games")


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
