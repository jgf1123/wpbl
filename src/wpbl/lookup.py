"""A plain lookup table for game_id: date, teams, final score.

    pixi run games              # print the table
                                 # also writes data/games_lookup.csv

Built from the parsed games table, not the raw JSON directly: the raw feed's
own rows for an unplayed game carry blank team names, and every played game
has a stale, never-played phantom duplicate sitting next to it (see the
README) -- both are useless for looking a game up and are dropped here.

The printed table uses team codes and a short status code so a line fits a
normal terminal width; the CSV keeps the full team names and status string,
since a spreadsheet doesn't have that constraint.
"""

from __future__ import annotations

import pandas as pd

from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

OUT_CSV = OUT_DIR.parent / "games_lookup.csv"


def status_code(status: str) -> str:
    """'Final - 6 innings - Weather Delay' -> 'F6*'; 'Not Started' -> '-'."""
    if status == "Not Started":
        return "-"
    if status == "Final":
        return "F"
    if status.startswith("Final - "):
        parts = status[len("Final - "):].split(" - ")
        innings = parts[0].split()[0]
        return f"F{innings}" + ("*" if len(parts) > 1 else "")
    return status


def build() -> pd.DataFrame:
    games = pd.read_parquet(OUT_DIR / "games.parquet")
    real = (games[~games["is_phantom_duplicate"]]
            .sort_values(["game_date", "first_pitch_utc"]).copy())

    def score(row) -> str:
        return (f'{int(row["away_score"])}-{int(row["home_score"])}'
                if row["is_final"] else "-")

    real["away_name"] = real["away_team_name"].fillna("").replace("", "TBD")
    real["home_name"] = real["home_team_name"].fillna("").replace("", "TBD")
    real["matchup"] = real["away_name"] + " @ " + real["home_name"]
    real["away_code"] = real["away_team_name"].map(CODES).fillna("TBD")
    real["home_code"] = real["home_team_name"].map(CODES).fillna("TBD")
    real["score"] = real.apply(score, axis=1)
    real["status_code"] = real["status"].map(status_code)

    return real[["game_id", "game_date", "matchup", "away_code", "home_code",
                "score", "status", "status_code"]].reset_index(drop=True)


def main() -> None:
    table = build()
    table.drop(columns="status_code").to_csv(OUT_CSV, index=False)

    printable = pd.DataFrame({
        "date": table["game_date"].astype(str).str.slice(5),  # MM-DD
        "game": table["away_code"] + "@" + table["home_code"],
        "score": table["score"],
        "st": table["status_code"],
        "game_id": table["game_id"],
    })
    pd.set_option("display.width", 200)
    print(printable.to_string(index=False))
    print("\n  st: F = final (7 inn)  F8 = final, 8 inn  F6* = final, 6 inn, "
          "weather-shortened  - = not yet played")
    print(f"\n{len(table)} games -> {OUT_CSV}")
    print(f"  ({int((table['status'] == 'Not Started').sum())} not yet played)")


if __name__ == "__main__":
    main()
