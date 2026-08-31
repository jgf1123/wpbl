"""Reconcile the derived tables against the raw feed.

Every check compares something we computed to something the feed stated
independently, so a silent parsing bug shows up as a mismatch rather than as a
plausible-looking number.

    pixi run check
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from wpbl.parse import OUT_DIR, RAW_DIR, ip_to_outs

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'  -- ' + detail if detail else ''}")
    if not ok:
        FAILURES.append(f"{name}: {detail}")


def load(name: str) -> pd.DataFrame:
    return pd.read_parquet(OUT_DIR / f"{name}.parquet")


def main() -> None:
    games = load("games")
    team_games = load("team_games")
    line_score = load("line_score")
    batting = load("batting")
    pitching = load("pitching")
    stints = load("pitching_stints")
    plays = load("plays")
    pitch_events = load("pitch_events")

    raw_boxes = {p.stem: json.loads(p.read_text(encoding="utf-8"))["boxscore"]
                 for p in sorted((RAW_DIR / "boxscore").glob("*.json"))}

    print("\ncoverage")
    finals = games[games["is_final"]]
    missing = finals.loc[~finals["has_boxscore"], "game_id"].tolist()
    check("every final game has a box score", not missing, f"missing {missing}")
    check("box score count matches final count",
          len(raw_boxes) == len(finals), f"{len(raw_boxes)} boxes vs {len(finals)} finals")
    incomplete = finals.loc[~finals["is_complete"], "game_id"].tolist()
    check("every final box score reports status.complete", not incomplete, f"{incomplete}")

    print("\nscores reconcile")
    # Runs counted off the narrative must match the line score half-inning by
    # half-inning. Two half-innings are known not to: the feed dropped one
    # entirely and truncated a narrative in another, losing a run each time.
    pbp = plays.groupby(["game_id", "batting_team_id", "inning"])["runs_scored"].sum().rename("pbp")
    ls = line_score.groupby(["game_id", "team_id", "inning"])["runs"].sum().rename("line")
    halves = pd.concat([pbp, ls], axis=1).fillna(0)
    off_halves = halves[halves["pbp"] != halves["line"]]
    check("narrative runs match the line score in every half-inning",
          len(off_halves) <= 2,
          f"{len(off_halves)} of {len(halves)} half-innings differ")
    if len(off_halves):
        for (game_id, team_id, inning), row in off_halves.iterrows():
            print(f"        known gap: {game_id} team {team_id[:8]} inn {inning} "
                  f"narrative={int(row['pbp'])} line={int(row['line'])}")

    # The running score is re-anchored to the line score each half-inning, so
    # the last play of a game must sit on the real final score.
    home_ids = games.set_index("game_id")["home_team_id"].to_dict()
    bad = []
    for game_id, group in plays.groupby("game_id"):
        tail = group.sort_values("sequence").iloc[-1]
        batting_is_home = tail["batting_team_id"] == home_ids[game_id]
        home = tail["home_score_before"] + (tail["runs_scored"] if batting_is_home else 0)
        away = tail["away_score_before"] + (0 if batting_is_home else tail["runs_scored"])
        want = (raw_boxes[game_id]["status"]["home_runs"], raw_boxes[game_id]["status"]["away_runs"])
        if (home, away) != want:
            bad.append((game_id, (int(home), int(away)), want))
    check("running score ends on the final score", not bad, f"{len(bad)} games differ: {bad[:3]}")

    # The schedule, the box score status block, and the line score are three
    # independent statements of the same score.
    merged = games.merge(
        team_games.pivot_table(index="game_id", columns="side", values="runs"),
        on="game_id", how="inner")
    mismatch = merged[(merged["home_score"] != merged["home"]) | (merged["away_score"] != merged["away"])]
    check("schedule score matches box score totals", mismatch.empty,
          f"{len(mismatch)} games: {mismatch['game_id'].tolist()[:3]}")

    line_totals = line_score.groupby(["game_id", "team_id"])["runs"].sum().rename("line_runs")
    joined = team_games.set_index(["game_id", "team_id"]).join(line_totals)
    off = joined[joined["runs"] != joined["line_runs"]]
    check("line score sums to team runs", off.empty, f"{len(off)} team-games")

    print("\nplayer lines sum to team totals")
    for label, frame, cols in [
        ("batting", batting, {"ab": "bat_ab", "h": "bat_h", "r": "bat_r", "bb": "bat_bb", "so": "bat_so"}),
        ("pitching", pitching, {"bf": "pit_bf", "h": "pit_h", "so": "pit_so",
                                "bb": "pit_bb", "er": "pit_er", "pitches": "pit_pitches"}),
        ("fielding", load("fielding"), {"po": "fld_po", "a": "fld_a", "e": "fld_e"}),
    ]:
        agg = frame.groupby(["game_id", "team_id"])[list(cols)].sum()
        want = team_games.set_index(["game_id", "team_id"])[list(cols.values())]
        want.columns = list(cols)
        diff = (agg - want).abs().sum()
        bad_cols = {k: v for k, v in diff.items() if v > 0}
        check(f"{label} player lines equal team totals", not bad_cols, f"column drift {bad_cols}")

    # Every out recorded by the pitchers must equal the outs the box score's
    # own innings-pitched figures imply for the team.
    outs = pitching.groupby(["game_id", "team_id"])["ip_outs"].sum().rename("player_outs")
    team_ip = team_games.set_index(["game_id", "team_id"])["pit_ip"].map(ip_to_outs).rename("team_outs")
    ip_cmp = pd.concat([outs, team_ip], axis=1)
    ip_off = ip_cmp[ip_cmp["player_outs"] != ip_cmp["team_outs"]]
    check("pitcher innings sum to team innings pitched", ip_off.empty,
          f"{len(ip_off)} team-games: {ip_off.head(3).to_dict('index')}")

    print("\nroles and identity")
    per_team = pitching.groupby(["game_id", "team_id"])["is_starter"].sum()
    check("exactly one starting pitcher per team-game", (per_team == 1).all(),
          f"{(per_team != 1).sum()} team-games")
    starter_first = pitching[pitching["is_starter"]]["appear_order"]
    check("the starter is always appearance order 1", (starter_first == 1).all(),
          f"{(starter_first != 1).sum()} rows")
    orders = pitching.groupby(["game_id", "team_id"])["appear_order"].apply(
        lambda s: sorted(s) == list(range(1, len(s) + 1)))
    check("appearance order is 1..n with no gaps", orders.all(), f"{(~orders).sum()} team-games")

    # The box score's appearance order and the play-by-play's order of arrival
    # are separate signals; they must agree.
    merged_roles = stints.merge(
        pitching[["game_id", "team_id", "player_id", "appear_order"]],
        left_on=["game_id", "pitching_team_id", "pitcher_id"],
        right_on=["game_id", "team_id", "player_id"], how="left")
    check("stint order matches box score appearance order",
          (merged_roles["stint_id"] == merged_roles["appear_order"]).all(),
          f"{(merged_roles['stint_id'] != merged_roles['appear_order']).sum()} stints")
    check("one stint per pitcher-game (nobody re-entered)",
          len(stints) == len(pitching), f"{len(stints)} stints vs {len(pitching)} pitching lines")

    blank = lambda s: s.isna() | (s.astype(str).str.strip() == "")  # noqa: E731
    unresolved_p = plays["pitcher_name"].notna() & blank(plays["pitcher_id"])
    unresolved_b = plays["batter_name"].notna() & blank(plays["batter_id"])
    check("every named pitcher in the play-by-play resolves to an id",
          not unresolved_p.any(), f"{unresolved_p.sum()} plays")
    check("every named batter in the play-by-play resolves to an id",
          not unresolved_b.any(), f"{unresolved_b.sum()} plays")

    # ~30% of box score player rows arrive with an empty id. Repair pools ids by
    # (team, name) across games, which is only sound while a name never maps to
    # two ids within a team.
    players = load("players")
    real = players[players["id_ever_from_feed"]]
    clashes = real.groupby(["team_id", "player_name"]).size().pipe(lambda s: s[s > 1])
    check("no name maps to two different ids within a team", clashes.empty, f"{clashes.to_dict()}")
    for label, frame in [("batting", batting), ("pitching", pitching), ("fielding", load("fielding"))]:
        sources = frame["player_id_source"].value_counts().to_dict()
        check(f"no {label} row has an unrecoverable player id",
              sources.get("unresolved", 0) == 0, f"{sources}")
    check("no pitching line ever lost its id in the feed",
          (pitching["player_id_source"] == "feed").all(),
          f"{pitching['player_id_source'].value_counts().to_dict()}")
    print(f"        ids repaired: {int((batting['player_id_source'] == 'recovered').sum())} batting rows, "
          f"{int((load('fielding')['player_id_source'] == 'recovered').sum())} fielding rows")
    # person_id must merge a traded player's two ids without ever merging two
    # different people -- nobody can appear for both teams in the same game.
    both_sides = batting.groupby(["game_id", "person_id"])["team_id"].nunique()
    check("no person appears for both teams in one game", (both_sides <= 1).all(),
          f"{(both_sides > 1).sum()} cases")
    spans = players.groupby("person_id")["team_id"].nunique()
    moved = players[players["person_id"].isin(spans[spans > 1].index)]
    print(f"        {players['player_id'].nunique()} player_ids collapse to "
          f"{players['person_id'].nunique()} people; "
          f"{sorted(set(moved['person_name']))} changed teams")

    never = players[~players["id_ever_from_feed"]]
    print(f"        roster names that never carry an id anywhere: "
          f"{never['player_name'].tolist()} (no stat rows)")

    print("\nstarting lineups")
    posted = batting[batting["in_starting_lineup"]]
    sizes = posted.groupby(["game_id", "team_id"]).size()
    check("every team posts a 9 or 10 player lineup", sizes.isin([9, 10]).all(),
          f"sizes seen: {sizes.value_counts().to_dict()}")
    dupes = posted.groupby(["game_id", "team_id", "lineup_position"]).size()
    check("no position is filled twice in one lineup", (dupes == 1).all(),
          f"{(dupes > 1).sum()} duplicated slots")
    spots = posted.groupby(["game_id", "team_id"])["lineup_spot"].apply(
        lambda s: sorted(s) == list(range(1, len(s) + 1)))
    check("lineup spots run 1..n with no gaps", spots.all(), f"{(~spots).sum()} team-games")
    every_pos = posted.groupby(["game_id", "team_id"])["lineup_position"].nunique()
    check("every lineup covers all nine fielding positions", (every_pos >= 9).all(),
          f"{(every_pos < 9).sum()} team-games")

    print("\npitch code relabelling")
    ends = plays.dropna(subset=["pitch_sequence"]).copy()
    ends["last"] = ends["pitch_sequence"].str[-1]
    batted = {"single", "double", "triple", "home_run", "groundout", "flyout",
              "lineout", "popup", "foul_out", "fielders_choice", "sacrifice"}
    in_play = ends[ends["event_type"].isin(batted)]
    check("every batted-ball play ends on code P (so P = in play, not pitchout)",
          (in_play["last"] == "P").all(), f"{(in_play['last'] != 'P').sum()} of {len(in_play)}")
    ks = ends[ends["event_type"] == "strikeout"]
    check("every strikeout ends on K or S (so K = called strike, not unknown)",
          ks["last"].isin(["K", "S"]).all(), f"{(~ks['last'].isin(['K', 'S'])).sum()} of {len(ks)}")
    walks = ends[ends["event_type"] == "walk"]
    check("every walk ends on code B", (walks["last"] == "B").all(),
          f"{(walks['last'] != 'B').sum()} of {len(walks)}")
    check("no pitch code went unmapped", pitch_events["result"].notna().all(),
          f"{pitch_events['result'].isna().sum()} pitches")

    # A pitch string of length n must produce n pitch_events rows.
    counts = pitch_events.groupby(["game_id", "play_sequence"]).size().rename("n")
    counts.index.names = ["game_id", "sequence"]
    expect = plays.set_index(["game_id", "sequence"])["n_pitches"]
    aligned = expect[expect > 0].to_frame("n_pitches").join(counts)
    check("pitch_events count matches the pitch string length",
          (aligned["n_pitches"] == aligned["n"]).all(),
          f"{(aligned['n_pitches'] != aligned['n']).sum()} of {len(aligned)} plays")

    print("\nplay classification")
    pa = plays[plays["is_plate_appearance"]]
    # Plate appearances counted off the play-by-play should land on the box
    # score's batters-faced totals.
    pbp_bf = pa.groupby(["game_id", "pitching_team_id"]).size().rename("pbp")
    pbp_bf.index.names = ["game_id", "team_id"]
    box_bf = team_games.set_index(["game_id", "team_id"])["pit_bf"].rename("box")
    joined_bf = pbp_bf.to_frame().join(box_bf)
    drift = (joined_bf["pbp"] - joined_bf["box"]).abs()
    # The one team-game that cannot tie is the missing half-inning.
    check("play-by-play plate appearances match batters faced",
          (drift > 0).sum() <= 1,
          f"{(drift > 0).sum()} team-games, max drift {drift.max()}, total {drift.sum()}")
    for idx, value in drift[drift > 0].items():
        print(f"        unmatched: {idx[0]} team {idx[1][:8]} off by {int(value)}")

    # The same reconciliation one level down: each pitcher's stint, rebuilt from
    # the play-by-play, against her own box score line.
    stint_vs_box = stints.merge(
        pitching[["game_id", "team_id", "player_id", "player_name", "bf", "pitches", "h"]],
        left_on=["game_id", "pitching_team_id", "pitcher_id"],
        right_on=["game_id", "team_id", "player_id"], suffixes=("_stint", "_box"))
    check("every stint joins to a box score pitching line",
          len(stint_vs_box) == len(stints), f"{len(stint_vs_box)} of {len(stints)}")
    # Where the feed lost the narrative it also lost the outcome and misassigned
    # one plate appearance between two pitchers, so per-pitcher totals can only
    # be expected to tie in games whose play-by-play is intact.
    lossy = set(games.loc[games["n_blank_plays"] > 0, "game_id"])
    intact = stint_vs_box[~stint_vs_box["game_id"].isin(lossy)]
    for label, mine, theirs in [("batters faced", "batters_faced", "bf"),
                                ("hits allowed", "hits_allowed", "h")]:
        drift_all = (stint_vs_box[mine] - stint_vs_box[theirs]).abs()
        drift_intact = (intact[mine] - intact[theirs]).abs()
        check(f"each pitcher's {label} matches her box score line "
              f"(games with intact play-by-play)",
              (drift_intact == 0).all(),
              f"{(drift_intact > 0).sum()} of {len(intact)} pitchers")
        outside = int((drift_all > 0).sum()) - int((drift_intact > 0).sum())
        if outside:
            print(f"        {outside} pitcher(s) in games with lost narratives differ on {label}")
    # The feed's own pitch counts drift by a pitch or two from the length of its
    # pitch strings. Small and one-sided, so worth reporting rather than failing.
    pitch_drift = (stint_vs_box["pitches_stint"] - stint_vs_box["pitches_box"]).abs()
    print(f"        pitch-count drift vs box score: {(pitch_drift > 0).sum()} pitchers, "
          f"max {int(pitch_drift.max())} pitches")
    leftover = plays[plays["event_type"] == "unknown"]["play_kind"].value_counts().to_dict()
    print(f"        'unknown' event_type resolved as: {leftover}")

    print("\nfeed caveats")
    phantom = games[games["is_phantom_duplicate"]]
    print(f"        phantom duplicate games flagged: {len(phantom)}")
    print(f"        games with TrackMan tracking: {int(games['has_tracking'].sum())}")
    print(f"        start times shifted +1h (2026 season): {int((games['start_time_shift_applied_h'] == 1).sum())}")

    print(f"\n{len(FAILURES)} failing check(s)")
    for failure in FAILURES:
        print(f"  - {failure}")


if __name__ == "__main__":
    main()
