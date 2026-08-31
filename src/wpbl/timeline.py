"""How each team's use of its players changed over the season.

    pixi run timeline

The league fields 15-player rosters and few players have trained as pitchers, so
position players pitching and pitchers moving between starting and relief are
the normal state, not anomalies. The question this asks is narrower: did teams
*converge* on an arrangement as the season went on, and where?

Everything is indexed by team game number rather than date, since the four teams
played 11-13 games on different schedules.
"""

from __future__ import annotations

import pandas as pd

from wpbl.parse import OUT_DIR

# Enough of a swing in starts between halves to be a decision rather than noise.
USAGE_SHIFT = 3


def load():
    team_games = pd.read_parquet(OUT_DIR / "team_games.parquet").sort_values("game_date")
    team_games["gm"] = team_games.groupby("team_name").cumcount() + 1
    index = team_games.set_index(["team_name", "game_id"])["gm"].to_dict()
    final = team_games.groupby("team_name")["gm"].max().to_dict()

    def stamp(frame):
        frame = frame.copy()
        frame["gm"] = [index.get((t, g)) for t, g in zip(frame["team_name"], frame["game_id"])]
        # Halves are per team, since schedules differ in length.
        frame["half"] = ["1st" if g <= final[t] / 2 else "2nd"
                         for t, g in zip(frame["team_name"], frame["gm"])]
        return frame

    pitching = stamp(pd.read_parquet(OUT_DIR / "pitching.parquet"))
    pitching["ip"] = pitching["ip_outs"] / 3
    batting = stamp(pd.read_parquet(OUT_DIR / "batting.parquet"))
    team_games["half"] = ["1st" if g <= final[t] / 2 else "2nd"
                          for t, g in zip(team_games["team_name"], team_games["gm"])]
    return team_games, pitching, batting


def pitcher_timeline(team_games: pd.DataFrame, pitching: pd.DataFrame) -> None:
    meta = team_games.set_index(["team_name", "game_id"])
    for team in sorted(pitching["team_name"].unique()):
        print(f"\n===== {team}")
        seen: set[str] = set()
        rows = pitching[pitching["team_name"] == team].sort_values(["gm", "appear_order"])
        for game_id, group in rows.groupby("game_id", sort=False):
            row = meta.loc[(team, game_id)]
            used = []
            for _, pitcher in group.iterrows():
                debut = "" if pitcher["person_id"] in seen else "*"
                seen.add(pitcher["person_id"])
                used.append(f"{pitcher['person_name']}{debut} ({pitcher['ip']:.1f})")
            result = "W" if row["won"] else "L"
            print(f"  g{int(row['gm']):2d} {row['game_date']} "
                  f"{'vs' if row['is_home'] else '@ '} {row['opponent_team_name'][:14]:14s} "
                  f"{result} {int(row['runs']):2d}-{int(row['opponent_runs']):<2d} " + " -> ".join(used))
    print("\n  * first appearance of the season")


def convergence(pitching: pd.DataFrame) -> pd.DataFrame:
    """Per team-game: staff size, how long the starter went, how many pitchers
    were seeing their first action, and whether the starter had started before."""
    rows = []
    for team, group in pitching.sort_values(["gm", "appear_order"]).groupby("team_name"):
        starters: set[str] = set()
        used: set[str] = set()
        for gm, game in group.groupby("gm"):
            starter = game.iloc[0]
            rows.append({
                "team_name": team, "gm": gm, "half": game["half"].iloc[0],
                "n_pitchers": len(game),
                "starter_ip": starter["ip"],
                "n_debuts": sum(1 for p in game["person_id"] if p not in used),
                "repeat_starter": starter["person_id"] in starters,
            })
            starters.add(starter["person_id"])
            used |= set(game["person_id"])
    return pd.DataFrame(rows)


def lineup_stability(batting: pd.DataFrame) -> pd.DataFrame:
    """Game-over-game: what share of the posted lineup is unchanged from the
    previous game, by personnel, by fielding position, and by batting-order spot."""
    posted = batting[batting["in_starting_lineup"]]
    rows = []
    for team, group in posted.groupby("team_name"):
        previous = None
        for gm, game in group.groupby("gm"):
            by_pos = dict(zip(game["lineup_position"], game["person_id"]))
            by_spot = dict(zip(game["lineup_spot"], game["person_id"]))
            who = set(game["person_id"])
            if previous:
                old_pos, old_spot, old_who = previous
                rows.append({
                    "team_name": team, "gm": gm, "half": game["half"].iloc[0],
                    "same_players": 100 * len(who & old_who) / len(who),
                    "same_position": 100 * sum(1 for k, v in by_pos.items()
                                               if old_pos.get(k) == v) / len(by_pos),
                    "same_spot": 100 * sum(1 for k, v in by_spot.items()
                                           if old_spot.get(k) == v) / len(by_spot),
                })
            previous = (by_pos, by_spot, who)
    return pd.DataFrame(rows)


def usage_shifts(batting: pd.DataFrame) -> pd.DataFrame:
    """Players whose starts moved sharply between the halves -- a team deciding
    someone is or is not a regular."""
    posted = batting[batting["in_starting_lineup"]]
    grouped = (posted.groupby(["team_name", "person_name", "half"])
               .agg(starts=("gm", "size"), spot=("lineup_spot", "mean")).reset_index())
    wide = grouped.pivot_table(index=["team_name", "person_name"], columns="half",
                               values=["starts", "spot"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.reindex(columns=["starts_1st", "starts_2nd", "spot_1st", "spot_2nd"])
    wide[["starts_1st", "starts_2nd"]] = wide[["starts_1st", "starts_2nd"]].fillna(0)
    wide["change"] = wide["starts_2nd"] - wide["starts_1st"]
    return wide[wide["change"].abs() >= USAGE_SHIFT].sort_values("change")


def main() -> None:
    pd.set_option("display.width", 220)
    team_games, pitching, batting = load()

    print("===== who pitched, game by game")
    pitcher_timeline(team_games, pitching)

    print("\n\n===== cumulative distinct pitchers used, by team game number")
    curve = {}
    for team, group in pitching.groupby("team_name"):
        seen, running = set(), []
        for gm in range(1, int(group["gm"].max()) + 1):
            seen |= set(group.loc[group["gm"] == gm, "person_id"])
            running.append(len(seen))
        curve[team] = pd.Series(running, index=range(1, len(running) + 1))
    print(pd.DataFrame(curve).to_string())

    conv = convergence(pitching)
    print("\n\n===== staff usage, first half vs second half of each team's schedule")
    summary = conv.groupby(["team_name", "half"]).agg(
        games=("gm", "size"), pitchers_per_game=("n_pitchers", "mean"),
        starter_ip=("starter_ip", "mean"), debuts=("n_debuts", "sum"),
        repeat_starter_pct=("repeat_starter", lambda s: 100 * s.mean())).round(2)
    print(summary.to_string())
    print("\n  league:")
    print(conv.groupby("half").agg(
        games=("gm", "size"), pitchers_per_game=("n_pitchers", "mean"),
        starter_ip=("starter_ip", "mean"), debuts=("n_debuts", "sum"),
        repeat_starter_pct=("repeat_starter", lambda s: 100 * s.mean())).round(2).to_string())

    stab = lineup_stability(batting)
    print("\n\n===== lineup stability, % unchanged from the previous game")
    print(stab.groupby(["team_name", "half"])[
        ["same_players", "same_position", "same_spot"]].mean().round(1).to_string())
    print("\n  league:")
    print(stab.groupby("half")[
        ["same_players", "same_position", "same_spot"]].mean().round(1).to_string())

    print("\n\n===== players whose role changed most between halves")
    print(usage_shifts(batting).round(1).to_string())


if __name__ == "__main__":
    main()
