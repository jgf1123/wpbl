"""Where each player actually played, and how often.

    pixi run positions
    pixi run positions --min 5     # only players with at least 5 games

Positional versatility is a defining feature of this league rather than a
curiosity. Fifteen-player rosters mean position players pitch, catchers move to
the outfield, and a team's best starter may spend the rest of the week in
centre field. This counts games at each position so that pattern is visible
rather than anecdotal.

Two things this gets right that a naive count of the box score's `position`
field would not.

Pinch-hitting is not a fielding position. `ph` and `pr` appear in that field
alongside real positions; they are counted separately, because a player who
pinch-hit in eight games did not play eight games in the field.

The `position` field under-reports pitching. Six pitching lines in this season
have a batting row that omits "p" -- the feed simply leaves it out, which is
how a pitcher who threw two and a third innings can appear to have spent the
game at third base. Pitching appearances are therefore taken from
pitching.parquet, which is authoritative, and unioned in.

Identity is keyed on person_id, so a traded player's games sum across both
teams rather than splitting.
"""

from __future__ import annotations

import sys
from collections import Counter

import pandas as pd

from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

# The nine fielding positions plus the designated hitter, in scorecard order.
FIELDING = ["p", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]
NOT_FIELDING = {"ph", "pr"}


def games_by_position() -> pd.DataFrame:
    """One row per player, one column per position, values are games played."""
    batting = pd.read_parquet(OUT_DIR / "batting.parquet")
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")

    played: dict[tuple, Counter] = {}
    bench: dict[tuple, Counter] = {}
    appeared: dict[tuple, set] = {}
    started: dict[tuple, set] = {}

    for row in batting.itertuples():
        key = (row.person_id, row.person_name, row.team_name)
        tokens = {t for t in str(row.position or "").split("/") if t}
        appeared.setdefault(key, set()).add(row.game_id)
        if row.in_starting_lineup:
            started.setdefault(key, set()).add(row.game_id)
        for token in tokens:
            target = bench if token in NOT_FIELDING else played
            target.setdefault(key, Counter())[token] += 1

    # The box score's position field misses some pitching appearances, so take
    # those from the pitching table instead of trusting it.
    for row in pitching.itertuples():
        if row.bf <= 0:
            continue        # announced as starter, never faced a batter
        key = (row.person_id, row.person_name, row.team_name)
        appeared.setdefault(key, set()).add(row.game_id)
        counts = played.setdefault(key, Counter())
        counts["p"] = 0     # recount below, so the union is exact
    pitched = (pitching[pitching["bf"] > 0]
               .groupby(["person_id", "person_name", "team_name"])["game_id"].nunique())
    for key, n in pitched.items():
        played.setdefault(key, Counter())["p"] = int(n)

    rows = []
    for key in sorted(appeared, key=lambda k: k[1]):
        person_id, name, team = key
        counts = played.get(key, Counter())
        spots = bench.get(key, Counter())
        row = {"tm": CODES.get(team, "?"), "player": name,
               "games": len(appeared[key]), "starts": len(started.get(key, set()))}
        for position in FIELDING:
            row[position] = counts.get(position, 0)
        row["ph/pr"] = sum(spots.values())
        row["spots"] = sum(1 for p in FIELDING if counts.get(p, 0))
        field_games = [p for p in FIELDING if counts.get(p, 0)]
        row["primary"] = max(field_games, key=lambda p: counts[p]) if field_games else "-"
        rows.append(row)
    return pd.DataFrame(rows)


def main() -> None:
    pd.set_option("display.width", 260)
    minimum = 1
    for i, arg in enumerate(sys.argv):
        if arg == "--min" and i + 1 < len(sys.argv):
            minimum = int(sys.argv[i + 1])

    table = games_by_position()
    table = table[table["games"] >= minimum].sort_values(
        ["tm", "games", "player"], ascending=[True, False, True])

    print(f"games at each position, {len(table)} players"
          f"{f' with at least {minimum} games' if minimum > 1 else ''}")
    print("  counts are games, not innings; a player at two positions in one game")
    print("  is counted at both, so a row can exceed her games played\n")

    header = (f"  {'':4s}{'player':22s}{'G':>4s}{'GS':>4s}"
              + "".join(f"{p:>5s}" for p in FIELDING)
              + f"{'ph/pr':>7s}{'spots':>7s}  primary")
    print(header)
    # itertuples mangles column names that start with a digit ("1b" becomes
    # "_6"), so iterate over plain dicts instead.
    for _, block in table.groupby("tm"):
        print()
        for row in block.to_dict("records"):
            cells = "".join(f"{row[p] or '':>5}" for p in FIELDING)
            print(f"  {row['tm']:4s}{row['player']:22s}{row['games']:4d}{row['starts']:4d}"
                  f"{cells}{row['ph/pr'] or '':>7}{row['spots']:7d}  {row['primary']}")

    print("\n\n=== how many positions each player covered ===")
    spread = table["spots"].value_counts().sort_index()
    for spots, n in spread.items():
        print(f"  {spots} position{'s' if spots != 1 else ' '}: {n:2d} players")
    versatile = table[table["spots"] >= 3].sort_values("spots", ascending=False)
    print(f"\n  players at three or more positions: {len(versatile)}")
    for row in versatile.to_dict("records"):
        spots = ", ".join(f"{p} {row[p]}" for p in FIELDING if row[p])
        print(f"    {row['tm']} {row['player']:22s} {spots}")

    print("\n=== pitchers who also played the field ===")
    both = table[(table["p"] > 0) & (table["spots"] >= 2)]
    print(f"  {len(both)} of {int((table['p'] > 0).sum())} pitchers")
    for row in both.sort_values("p", ascending=False).to_dict("records"):
        elsewhere = ", ".join(f"{p} {row[p]}" for p in FIELDING if p != "p" and row[p])
        print(f"    {row['tm']} {row['player']:22s} pitched {row['p']:2d}, also {elsewhere}")


if __name__ == "__main__":
    main()
