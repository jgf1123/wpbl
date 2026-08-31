"""Who pitched, for whom, in what role.

    pixi run rosters

Everything groups on person_id, not player_id: the feed mints a new player_id
when a player changes teams, so grouping on player_id would silently split a
traded pitcher into two.
"""

from __future__ import annotations

import pandas as pd

from wpbl.parse import OUT_DIR

# A pitcher who bats on days she does not pitch is playing the field, not
# resting. Four such games is the line between a regular and an occasional bat.
TWO_WAY_GAMES = 4


def load():
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet").sort_values("game_date")
    pitching["ip"] = pitching["ip_outs"] / 3
    batting = pd.read_parquet(OUT_DIR / "batting.parquet")
    team_games = pd.read_parquet(OUT_DIR / "team_games.parquet")
    return pitching, batting, team_games


def build(pitching: pd.DataFrame, batting: pd.DataFrame, team_games: pd.DataFrame) -> pd.DataFrame:
    pitched = set(zip(pitching["person_id"], pitching["game_id"]))
    batting = batting.assign(also_pitched=[
        (person, game) in pitched for person, game in zip(batting["person_id"], batting["game_id"])])

    # Grouped per person *and* team, so a pitcher who threw for two clubs gets a
    # row for each rather than collapsing into one and hiding the move.
    rows = []
    for (person_id, team_id), group in pitching.groupby(["person_id", "team_id"]):
        last = group["game_date"].max()
        # Chances the team had to use her again after her final appearance --
        # the difference between "tried once and dropped" and "debuted late".
        later = team_games[(team_games["team_id"] == team_id) & (team_games["game_date"] > last)]
        field_only = batting[(batting["person_id"] == person_id) & ~batting["also_pitched"]]
        starts, relief = int(group["is_starter"].sum()), int((~group["is_starter"]).sum())
        innings = group["ip"].sum()
        rows.append({
            "person_id": person_id,
            "name": group["person_name"].iloc[0],
            "team": group["team_name"].iloc[-1],
            "teams_pitched_for": int(pitching.loc[pitching["person_id"] == person_id,
                                                  "team_id"].nunique()),
            "role": "SP only" if not relief else ("RP only" if not starts else "swing"),
            "app": len(group),
            "GS": starts,
            "GR": relief,
            "ip": round(innings, 1),
            "bf": int(group["bf"].sum()),
            "era": round(group["er"].sum() * 9 / innings, 2) if innings else None,
            "so": int(group["so"].sum()),
            "bb": int(group["bb"].sum()),
            "first": group["game_date"].min(),
            "last": last,
            # Appearance order as it happened: "RSRS" relieved, started, ...
            "sequence": "".join("S" if s else "R" for s in group["is_starter"]),
            "team_games_after_last": len(later),
            "games_batted_not_pitching": len(field_only),
            "field_positions": "/".join(sorted({p for p in field_only["position"].dropna() if p})[:5]),
        })

    frame = pd.DataFrame(rows)
    frame["two_way"] = frame["games_batted_not_pitching"] >= TWO_WAY_GAMES
    frame["one_off"] = frame["app"] == 1
    return frame.sort_values(["team", "GS", "ip"], ascending=[True, False, False])


def main() -> None:
    pd.set_option("display.width", 200)
    pitching, batting, team_games = load()
    frame = build(pitching, batting, team_games)
    played = team_games.groupby("team_name").size()

    cols = ["name", "role", "app", "GS", "GR", "ip", "bf", "era", "sequence", "first", "last"]
    for team in sorted(frame["team"].unique()):
        block = frame[frame["team"] == team].copy()
        block["name"] = [f"{r['name']}{' *' if r['two_way'] else ''}" for _, r in block.iterrows()]
        print(f"\n===== {team} — {played[team]} games, {len(block)} pitchers used")
        print(block[cols].to_string(index=False))
    print("\n  * also plays the field on days she does not pitch")

    print("\n\n===== used once and never again")
    one = frame[frame["one_off"]].sort_values("team_games_after_last", ascending=False)
    print(one[["name", "team", "first", "GS", "GR", "ip", "bf",
               "team_games_after_last", "games_batted_not_pitching"]].to_string(index=False))

    print("\n\n===== moved between starting and relieving")
    swing = frame[frame["role"] == "swing"].sort_values("app", ascending=False)
    print(swing[["name", "team", "app", "GS", "GR", "ip", "sequence", "first", "last"]].to_string(index=False))

    print("\n\n===== pitched for more than one team")
    moved = frame[frame["teams_pitched_for"] > 1]
    print(moved[cols].to_string(index=False) if len(moved)
          else "  no pitcher threw for two teams (three position players did change teams)")

    print(f"\n\n{len(frame)} distinct pitchers used league-wide; "
          f"{int(frame['two_way'].sum())} of them play the field, "
          f"{int(frame['one_off'].sum())} appeared exactly once.")


if __name__ == "__main__":
    main()
