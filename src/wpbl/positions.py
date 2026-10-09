"""Where each player actually played, and how often.

    pixi run positions
    pixi run positions --min 5     # only players with at least 5 games

Positional versatility is a defining feature of this league rather than a
curiosity. Fifteen-player rosters mean position players pitch, catchers move to
the outfield, and a team's best starter may spend the rest of the week in
centre field. The command prints games at each position, regular season and
postseason side by side (9+2), and innings at each fielding position, the
same way (9.0+3.1).

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

import re
import sys
from collections import Counter, defaultdict

import pandas as pd

from wpbl.parse import ip_to_outs
from wpbl.usage_chart import CODES, ip_text

# The nine fielding positions plus the designated hitter, in scorecard order.
FIELDING = ["p", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf", "dh"]
NOT_FIELDING = {"ph", "pr"}


def _season_games(postseason: bool) -> set:
    from wpbl import tables

    games = tables.read("games", "all")
    return set(games.loc[games["is_postseason"] == postseason, "game_id"])


def games_by_position(postseason: bool = False) -> pd.DataFrame:
    """One row per player, one column per position, values are games played,
    in the regular season or the postseason."""
    from wpbl import tables

    keep = _season_games(postseason)
    batting = tables.read("batting", "all")
    pitching = tables.read("pitching", "all")
    batting = batting[batting["game_id"].isin(keep)]
    pitching = pitching[pitching["game_id"].isin(keep)]

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

    counted = ["games", "starts", *FIELDING, "ph/pr"]
    regular = games_by_position(postseason=False)
    post = games_by_position(postseason=True)
    both = regular.merge(post, on=["tm", "player"], how="outer", suffixes=("", "_post"))
    for col in counted:
        both[col] = both[col].fillna(0).astype(int)
        both[f"{col}_post"] = both[f"{col}_post"].fillna(0).astype(int)
    # Over both seasons: what the summaries below and the --min filter use.
    table = both[["tm", "player"]].copy()
    for col in counted:
        table[col] = both[col] + both[f"{col}_post"]
    table["spots"] = [sum(1 for p in FIELDING if row[p]) for row in table.to_dict("records")]
    table["primary"] = [max((p for p in FIELDING if row[p]), key=lambda p: row[p], default="-")
                        for row in table.to_dict("records")]
    keep = table["games"] >= minimum
    table, both = table[keep], both[keep]
    order = table.sort_values(["tm", "games", "player"], ascending=[True, False, True]).index
    table, both = table.loc[order], both.loc[order]

    def cell(row, col, width):
        reg, post_n = row[col], row[f"{col}_post"]
        text = f"{reg}+{post_n}" if post_n else (str(reg) if reg else "")
        return f"{text:>{width}}"

    print(f"games at each position, {len(table)} players"
          f"{f' with at least {minimum} games' if minimum > 1 else ''}")
    print("  regular season + postseason: 9+2 is 9 regular-season games and 2")
    print("  postseason games; a lone number is regular season only")
    print("  counts are games, not innings; a player at two positions in one game")
    print("  is counted at both, so a row can exceed her games played\n")

    header = (f"  {'':4s}{'player':22s}{'G':>6s}{'GS':>6s}"
              + "".join(f"{p:>6s}" for p in FIELDING)
              + f"{'ph/pr':>7s}{'spots':>7s}  primary")
    print(header)
    # itertuples mangles column names that start with a digit ("1b" becomes
    # "_6"), so iterate over plain dicts instead.
    for (_, block), (_, totals) in zip(both.groupby("tm", sort=True), table.groupby("tm", sort=True)):
        print()
        for row, total in zip(block.to_dict("records"), totals.to_dict("records")):
            cells = "".join(cell(row, p, 6) for p in FIELDING)
            print(f"  {row['tm']:4s}{row['player']:22s}{cell(row, 'games', 6)}{cell(row, 'starts', 6)}"
                  f"{cells}{cell(row, 'ph/pr', 7)}{total['spots']:7d}  {total['primary']}")

    # One row per player across both seasons: keyed on person_id, so a player
    # traded before the postseason is not split in two.
    innings = innings_by_position("all", False).merge(
        innings_by_position("all", True), on="pid", how="outer", suffixes=("", "_post"))
    innings["tm"] = innings["tm"].fillna(innings["tm_post"])
    innings["player"] = innings["player"].fillna(innings["player_post"])
    innings["total_outs"] = innings["total_outs"].fillna(0) + innings["total_outs_post"].fillna(0)
    if minimum > 1:
        innings = innings[innings["player"].isin(set(table["player"]))]
    _print_innings(innings.sort_values(["tm", "total_outs", "player"], ascending=[True, False, True]))

    print("\n\n=== how many positions each player covered (regular season + postseason) ===")
    spread = table["spots"].value_counts().sort_index()
    for spots, n in spread.items():
        print(f"  {spots} position{'s' if spots != 1 else ' '}: {n:2d} players")
    versatile = table[table["spots"] >= 3].sort_values("spots", ascending=False)
    print(f"\n  players at three or more positions: {len(versatile)}")
    for row in versatile.to_dict("records"):
        spots = ", ".join(f"{p} {row[p]}" for p in FIELDING if row[p])
        print(f"    {row['tm']} {row['player']:22s} {spots}")

    print("\n=== pitchers who also played the field (regular season + postseason) ===")
    both = table[(table["p"] > 0) & (table["spots"] >= 2)]
    print(f"  {len(both)} of {int((table['p'] > 0).sum())} pitchers")
    for row in both.sort_values("p", ascending=False).to_dict("records"):
        elsewhere = ", ".join(f"{p} {row[p]}" for p in FIELDING if p != "p" and row[p])
        print(f"    {row['tm']} {row['player']:22s} pitched {row['p']:2d}, also {elsewhere}")


# Positions a batter card may list, in scorecard order. DH is not one of them:
# the card says where she can be sent in the field. The same order breaks a tie
# when two positions have the same number of outs. None of the 2026 cards tie.
CARD_POS = ["p", "c", "1b", "2b", "3b", "ss", "lf", "cf", "rf"]
CARD_ABBR = {"p": "P", "c": "C", "1b": "1B", "2b": "2B", "3b": "3B",
             "ss": "SS", "lf": "LF", "cf": "CF", "rf": "RF"}
_TIE = {p: i for i, p in enumerate(CARD_POS)}

_MOVE = re.compile(
    r"^(.*?)\s+to\s+(p|c|1b|2b|3b|ss|lf|cf|rf|dh)(?:\s+for\s+(.*?))?\s*\.?\s*$",
    re.I,
)
_LEAVE = re.compile(r"^/\s+for\s+(.*?)\s*\.?\s*$")
_OUT_WORD = re.compile(r"\bout\b", re.I)
_DOUBLE_PLAY = re.compile(r"double play", re.I)
_OUT_EVENTS = {"groundout", "flyout", "strikeout", "popup", "lineout",
               "foul_out", "out", "sacrifice", "fielders_choice", "caught_stealing"}
_ROSTER = {"substitution", "pitching_change", "empty"}


def _narr(play) -> str:
    return play.narrative if isinstance(play.narrative, str) else ""


def _out_like(play) -> bool:
    return (play.event_type in _OUT_EVENTS
            or play.play_kind in ("pickoff", "baserunning_out")
            or bool(_OUT_WORD.search(_narr(play))))


def _outs_from_text(play) -> int:
    """How many outs a play records when the feed's out count is stuck at zero."""
    return 2 if _DOUBLE_PLAY.search(_narr(play)) else 1


def _outs_per_play(rows, completed: bool) -> list[int]:
    """Outs to charge to each play of one half-inning.

    The next play's outs_before says what this play did. The last play has no
    next play, so a half that another half follows is closed out to 3, and the
    rest lands on the last play that was not a roster move. A half whose count
    never leaves zero lost plays; charge only the outs the narratives still
    show, rather than inventing a full inning on the last name.
    """
    n = len(rows)
    made = [0] * n
    if n == 0:
        return made
    for i in range(n - 1):
        delta = int(rows[i + 1].outs_before or 0) - int(rows[i].outs_before or 0)
        if 0 < delta <= 3:
            made[i] = delta
    stuck = max(int(r.outs_before or 0) for r in rows) == 0 and sum(made) == 0
    if stuck:
        for i, play in enumerate(rows):
            if _out_like(play):
                made[i] = _outs_from_text(play)
        return made
    target = n - 1
    while target > 0 and rows[target].play_kind in _ROSTER:
        target -= 1
    if completed or _out_like(rows[target]):
        rest = 3 - sum(made)
        if 0 < rest <= 3:
            made[target] = rest
    return made


def _drop(align, team, pid, keep=None):
    for pos, holder in list(align[team].items()):
        if holder == pid and pos != keep:
            del align[team][pos]


def _install(align, team, pos, pid):
    _drop(align, team, pid)
    align[team][pos] = pid


def innings_by_position(scope: str = "default", postseason: bool | None = None) -> pd.DataFrame:
    """Innings at each field position, one row per player; `postseason`, if
    given, keeps only the regular season (False) or the postseason (True).

    Cells are scorebook innings: 5.2 means five innings and two outs, the same
    reading as a pitching line. A blank cell is zero. Pitching comes from the
    pitching line; the other eight positions come from field_outs. A player who
    changed teams is one row, with both clubs in the team cell. DH is absent,
    because those outs are not time in the field.
    """
    from wpbl import tables

    counted = field_outs(scope, postseason)
    bat = tables.read("batting", scope)
    pit = tables.read("pitching", scope)
    if postseason is not None:
        keep = _season_games(postseason)
        bat = bat[bat["game_id"].isin(keep)]
        pit = pit[pit["game_id"].isin(keep)]
    pitched = 0
    for row in pit.itertuples(index=False):
        if row.bf and row.bf > 0:
            pitched += ip_to_outs(row.ip) or 0
    # Every pitching out has to land in the P column. A miss here means the
    # lineup walk and the pitching line have come apart.
    assert sum(counts["p"] for counts in counted.values()) == pitched

    names = (bat.drop_duplicates("person_id").set_index("person_id")["person_name"])
    clubs = bat.groupby("person_id")["team_name"].agg(lambda s: tuple(sorted(set(s))))
    # A pitcher can be missing from the batting table. Her name and club then
    # come from the pitching line, which is where her innings came from.
    pit_names = pit.drop_duplicates("person_id").set_index("person_id")
    rows = []
    for pid, counts in counted.items():
        total = sum(counts.get(pos, 0) for pos in CARD_POS)
        if total == 0:
            continue
        if pid in names.index:
            name = names.loc[pid]
            team_list = clubs.loc[pid]
        else:
            name = pit_names.loc[pid, "person_name"]
            team_list = (pit_names.loc[pid, "team_name"],)
        row = {
            "pid": pid,
            "tm": "/".join(CODES.get(team, "?") for team in team_list),
            "player": name,
            "total_outs": total,
        }
        for pos in CARD_POS:
            n = counts.get(pos, 0)
            assert ip_to_outs(ip_text(n)) == n
            row[CARD_ABBR[pos]] = ip_text(n) if n else ""
        rows.append(row)
    shown = sum(ip_to_outs(row["P"]) or 0 for row in rows)
    assert shown == pitched
    frame = pd.DataFrame(rows)
    return frame.sort_values(["tm", "total_outs", "player"], ascending=[True, False, True])


def _print_innings(frame: pd.DataFrame) -> None:
    """`frame`: innings_by_position for the regular season merged with the
    postseason's (columns suffixed _post)."""
    cols = [CARD_ABBR[pos] for pos in CARD_POS]

    def cell(row, col):
        reg = row[col] if isinstance(row[col], str) else ""
        post = row[f"{col}_post"] if isinstance(row[f"{col}_post"], str) else ""
        text = f"{reg or '0'}+{post}" if post else reg
        return f"{text:>10s}"

    print(f"\n\ninnings at each position, {len(frame)} players")
    print("  regular season + postseason: 9.0+3.1 is 9.0 regular-season innings and")
    print("  3.1 postseason innings; a lone number is regular season only")
    print("  5.2 means 5 innings and 2 outs; a blank cell is zero")
    print("  pitching innings come from the pitching line, the rest from who")
    print("  was standing at that position while the outs were recorded\n")
    print(f"  {'':8s}{'player':22s}" + "".join(f"{col:>10s}" for col in cols))
    for _, block in frame.groupby("tm", sort=True):
        print()
        for row in block.to_dict("records"):
            cells = "".join(cell(row, col) for col in cols)
            print(f"  {row['tm']:8s}{row['player']:22s}{cells}")


def field_outs(scope: str = "training", postseason: bool | None = None) -> dict:
    """Outs each player spent at each field position, over the card games
    (only the regular season or the postseason, if `postseason` is given).

    Pitching innings come from the pitching line (the box score's position
    string leaves "p" off). The other eight come from the starting lineup plus
    substitutions: a move by the team in the field happens at once, and a move
    by the team at bat (a pinch hitter staying in the game) waits until that
    team takes the field. DH, pinch-hitting and pinch-running are not positions.
    """
    from wpbl import tables

    bat = tables.read("batting", scope)
    plays = tables.read("plays", scope).sort_values(["game_id", "sequence"])
    pit = tables.read("pitching", scope)
    players = tables.read("players", scope)
    if postseason is not None:
        keep = _season_games(postseason)
        bat = bat[bat["game_id"].isin(keep)]
        plays = plays[plays["game_id"].isin(keep)]
        pit = pit[pit["game_id"].isin(keep)]
    player_to_person = players.set_index("player_id")["person_id"].to_dict()

    name_of = {}
    team_of = {}
    for row in bat.itertuples(index=False):
        name_of[(row.game_id, row.person_name)] = row.person_id
        name_of[(row.game_id, row.player_name)] = row.person_id
        team_of[(row.game_id, row.person_id)] = row.team_id

    def resolve(game, name):
        if not name:
            return None
        return name_of.get((game, name.strip().rstrip(".")))

    season = defaultdict(Counter)
    for game_id, gplays in plays.groupby("game_id", sort=False):
        align = defaultdict(dict)
        pending = defaultdict(dict)
        starters = bat[(bat["game_id"] == game_id) & bat["in_starting_lineup"]]
        for row in starters.itertuples(index=False):
            pos = (row.lineup_position or "").lower()
            if pos in CARD_ABBR and pos != "p":
                align[row.team_id][pos] = row.person_id
            elif pos == "p":
                align[row.team_id]["p"] = row.person_id
        rows = list(gplays.sort_values("sequence").itertuples(index=False))
        # Outs are a property of the half, so number them before walking it.
        charged = {}
        i = 0
        while i < len(rows):
            j = i + 1
            while j < len(rows) and (rows[j].inning, rows[j].half) == (rows[i].inning, rows[i].half):
                j += 1
            later = j < len(rows)
            for k, n_out in enumerate(_outs_per_play(rows[i:j], later)):
                charged[i + k] = n_out
            i = j

        seen_half = None
        for i, play in enumerate(rows):
            field = play.pitching_team_id
            half_key = (play.inning, play.half)
            if field and half_key != seen_half:
                for pos, pid in pending.pop(field, {}).items():
                    _install(align, field, pos, pid)
                seen_half = half_key
            narr = _narr(play).strip()
            if play.play_kind in ("substitution", "pitching_change"):
                leave = _LEAVE.match(narr)
                move = _MOVE.match(narr)
                if leave:
                    pid = resolve(game_id, leave.group(1))
                    if pid and field:
                        _drop(align, field, pid)
                elif move:
                    pid = resolve(game_id, move.group(1))
                    pos = move.group(2).lower()
                    if pid and pos == "dh":
                        for team in list(align):
                            _drop(align, team, pid)
                    elif pid and pos != "p":
                        # p is taken from the pitching line, not from this text.
                        side = team_of.get((game_id, pid))
                        if side == field:
                            _install(align, field, pos, pid)
                        elif side is not None:
                            # Batting now, fielding next half: a pinch hitter
                            # staying in the game.
                            pending[side][pos] = pid
                    elif pid and pos == "p":
                        side = team_of.get((game_id, pid))
                        if side == field:
                            _drop(align, field, pid)
            made = charged.get(i, 0)
            if made and field:
                for pos, pid in align[field].items():
                    if pos != "p":
                        season[pid][pos] += made

    for row in pit.itertuples(index=False):
        if not row.bf or row.bf <= 0:
            continue
        season[row.person_id]["p"] += ip_to_outs(row.ip) or 0
    return season


def position_labels(scope: str = "training") -> dict[str, str]:
    """Card text: positions she played, most innings first, DH excluded.

    An equal number of outs is broken by scorecard order (P, C, 1B, 2B, 3B,
    SS, LF, CF, RF). A player who only DH'd, pinch-hit or pinch-ran gets "".
    """
    labels = {}
    for pid, counts in field_outs(scope).items():
        ranked = sorted(((p, n) for p, n in counts.items() if n > 0 and p in CARD_ABBR),
                        key=lambda item: (-item[1], _TIE[item[0]]))
        labels[pid] = "/".join(CARD_ABBR[p] for p, _ in ranked)
    return labels


def check_position_labels(labels: dict[str, str] | None = None) -> None:
    """The list matches the pitching line, and a few positions read off the feed by hand."""
    from wpbl import tables

    labels = position_labels() if labels is None else labels
    bat = tables.read("batting", "training")
    pit = tables.read("pitching", "training")
    allowed = set(CARD_ABBR.values())
    pitched = set(pit.loc[pit["bf"] > 0, "person_id"])
    for label in labels.values():
        parts = label.split("/") if label else []
        assert parts == [p for p in parts if p in allowed]
        assert len(parts) == len(set(parts))
    for pid, label in labels.items():
        parts = label.split("/") if label else []
        assert ("P" in parts) == (pid in pitched)
    assert pitched <= set(labels)
    by_name = bat.drop_duplicates("person_id").set_index("person_name")["person_id"]
    # Denver's pitching line is 2.1 IP in a game whose play-by-play lost the
    # outs, so P has to come from the pitching table. Jordan was announced at
    # P and faced nobody. Alli moved to RF in a game whose box score omits it.
    assert "P" in labels[by_name["Denver Bryant"]].split("/")
    assert "P" not in labels[by_name["Jordan Eyster"]].split("/")
    assert "RF" in labels[by_name["Alli Schroder"]].split("/")
    assert labels[by_name["Ayami Sato"]].startswith("P")


if __name__ == "__main__":
    main()
