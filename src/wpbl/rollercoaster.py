"""Rollercoaster games and half-innings: how far win probability travelled.

    pixi run rollercoaster                 # whole games
    pixi run rollercoaster --halves        # single half-innings
    pixi run rollercoaster --pairs         # two consecutive half-innings
    pixi run rollercoaster --halves --pairs --top 15

Movement is the sum of |change in win probability| over every play, the same
steps the timeline chart draws (game_timeline.build, league-average model, every
completed game including the postseason). A game that went straight from 50% to
a win scores 50 points; one that swung hard and often scores far more. It is an
arbitrary, approximate measure of our own devising, not a mathematical
definition of a rollercoaster.

Movement alone is dominated by the half-inning in which the trailing team takes
the lead, especially late: one big hit moves a lot of win probability in a
single direction. So each stretch also gets a back-and-forth score,

    back-and-forth = movement - |win probability at the end - at the start|

the travel left over once the net change is taken out. It is zero for a stretch
that only ever moved one way, and it measures how much the two teams wrestled
the game back and forth inside it. For a whole game the net change is always 50
points (from 50% to a win), so back-and-forth ranks games exactly as movement
does and is only reported for half-innings.

A pair is two consecutive half-innings, so both teams bat -- the bottom of one
inning with the top of the next counts as well as the two halves of the same
inning. Its back-and-forth takes the net change across the whole pair.

Units are percentage points of win probability. A half-inning is only scored
when the play that ended it has a successor state: the last half of a game
called early for weather has none and is skipped.
"""

from __future__ import annotations

import sys

import pandas as pd

from wpbl.game_timeline import build, diff_label
from wpbl.parse import ALL_DIR
from wpbl.usage_chart import CODES
from wpbl.win_probability import Model

TOP = 10


def games_in_scope() -> pd.DataFrame:
    games = pd.read_parquet(ALL_DIR / "games.parquet")
    done = games[games["is_final"] & ~games["is_phantom_duplicate"]]
    return done.sort_values("game_date").set_index("game_id")


def half_innings(frame: pd.DataFrame, game_id: str, game) -> list[dict]:
    """One record per half-inning of one game, in order.

    The row after a half-inning's last play is the start of the next
    half-inning, or the synthetic Final row, so its win probability is where
    that half-inning ended. Rows with no successor (the Final row itself, or
    the last play of a called game) carry no swing and end nothing.
    """
    home = CODES.get(game["home_team_name"], game["home_team_name"][:3].upper())
    away = CODES.get(game["away_team_name"], game["away_team_name"][:3].upper())
    live = frame[frame["swing"].notna()]
    records = []
    for (inning, half), block in live.groupby(["inning", "half"], sort=False):
        last = block.index.max()
        records.append({
            "game_id": game_id,
            "date": str(game["game_date"])[5:],
            "matchup": f"{away}@{home}",
            "final": f"{int(game['away_score'])}-{int(game['home_score'])}",
            "winner": home if game["home_score"] > game["away_score"] else away,
            "label": f"{'T' if half == 'top' else 'B'}{inning}",
            "batting": away if half == "top" else home,
            "entering": diff_label(int(block.iloc[0]["diff"]), home, away),
            "runs": int(block["runs_scored"].sum()),
            "start": float(block.iloc[0]["wp"]),
            "end": float(frame.loc[last + 1, "wp"]),
            "movement": float(block["swing"].abs().sum()),
        })
    return records


def collect(model: Model) -> tuple[pd.DataFrame, pd.DataFrame]:
    games, halves = [], []
    for game_id, game in games_in_scope().iterrows():
        frame, _ = build(model, game_id)
        home = CODES.get(game["home_team_name"], "?")
        away = CODES.get(game["away_team_name"], "?")
        games.append({"date": str(game["game_date"])[5:], "matchup": f"{away}@{home}",
                      "final": f"{int(game['away_score'])}-{int(game['home_score'])}",
                      "innings": int(game["innings"]) if pd.notna(game["innings"]) else None,
                      "steps": int(frame["swing"].notna().sum()),
                      "movement": 100 * float(frame["swing"].abs().sum())})
        halves.extend(half_innings(frame, game_id, game))
    return pd.DataFrame(games), pd.DataFrame(halves)


def score(stretches: pd.DataFrame) -> pd.DataFrame:
    """Movement, net change and back-and-forth, in percentage points."""
    out = stretches.copy()
    out["net"] = (out["end"] - out["start"]).abs() * 100
    out["movement"] = out["movement"] * 100
    out["back_and_forth"] = out["movement"] - out["net"]
    out["winner WP"] = [f"{100 * s:.0f}->{100 * e:.0f}" for s, e in zip(out["start"], out["end"])]
    return out


def pairs(halves: pd.DataFrame) -> pd.DataFrame:
    """Every two consecutive half-innings of the same game."""
    rows = []
    for _, game in halves.groupby("game_id", sort=False):
        game = game.reset_index(drop=True)
        for i in range(len(game) - 1):
            a, b = game.iloc[i], game.iloc[i + 1]
            rows.append({
                "date": a["date"], "matchup": a["matchup"], "final": a["final"],
                "winner": a["winner"], "label": f"{a['label']}+{b['label']}",
                "entering": a["entering"],
                "runs": f"{a['batting']} {a['runs']}, {b['batting']} {b['runs']}",
                "start": a["start"], "end": b["end"],
                "movement": a["movement"] + b["movement"],
            })
    return pd.DataFrame(rows)


def show(title: str, table: pd.DataFrame, by: str, columns: list[str], top: int) -> None:
    ranked = table.sort_values(by, ascending=False).head(top).reset_index(drop=True)
    ranked.index += 1
    print(f"\n=== {title} ===")
    print(ranked[columns].to_string(float_format=lambda x: f"{x:.0f}"))
    print(f"  median {table[by].median():.0f}, max {table[by].max():.0f}, "
          f"over {len(table)}")


def main() -> None:
    pd.set_option("display.width", 220)
    args = sys.argv[1:]
    top = TOP
    if "--top" in args:
        at = args.index("--top")
        if at + 1 >= len(args) or not args[at + 1].isdigit():
            sys.exit("--top needs a number")
        top = int(args[at + 1])
        del args[at:at + 2]
    unknown = [a for a in args if a not in ("--halves", "--pairs")]
    if unknown:
        sys.exit(f"unknown option: {unknown[0]}")
    want_halves, want_pairs = "--halves" in args, "--pairs" in args

    games, halves = collect(Model())
    if not (want_halves or want_pairs):
        show("games, by movement (a straight line to a win scores 50)", games,
             "movement", ["date", "matchup", "final", "innings", "steps", "movement"], top)
        return

    cols = ["date", "matchup", "final", "winner", "label", "entering", "runs",
            "winner WP", "movement", "net", "back_and_forth"]
    if want_halves:
        scored = score(halves)
        show("half-innings, by movement", scored, "movement", cols, top)
        show("half-innings, by back-and-forth (movement minus net change)",
             scored, "back_and_forth", cols, top)
    if want_pairs:
        scored = score(pairs(halves))
        show("two consecutive half-innings, by movement", scored, "movement", cols, top)
        show("two consecutive half-innings, by back-and-forth (movement minus net change)",
             scored, "back_and_forth", cols, top)


if __name__ == "__main__":
    main()
