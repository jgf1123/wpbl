"""Win probability for one game state, from the command line.

    pixi run wpq --after "bottom 2" --away 1 --home 8
    pixi run wpq --before "top 5" --away 4 --home 4
    pixi run wpq --during "top 5" --outs 1 --bases 13 --away 4 --home 4
    pixi run wpq --after "top 3" --away 2 --home 0 --away-team LA --home-team NY
    pixi run wpq --pregame --away-team Boston --home-team SF
    pixi run wpq --during "top 5" --outs 1 --bases 2 --away 4 --home 0 \
        --away-team LA --home-team NY --cutoff j4uofrn55sr4wnlt:42

    from outside the repo:  pixi run --manifest-path wpbl/pixi.toml wpq ...

The same questions wpbl_win_prob.py answered, but from win_probability.py's
model, which reads the scraped tables and so is as current as the last
`pixi run refresh`. Two other differences: the answer is solved exactly rather
than simulated, and a half-inning can be joined in progress with --outs and
--bases.

Name both teams and a team-adjusted answer is printed beside the league one,
with a 90% interval from team_strength.py's posterior. That interval covers
uncertainty about how good the teams are, not about the league run
distribution underneath.
"""

from __future__ import annotations

import argparse
import re

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.team_strength import TeamStrength, expected_runs
from wpbl.win_probability import REGULATION, Model

BASE_WORDS = {"empty": "___", "none": "___", "loaded": "123", "corners": "1_3"}
BASE_NAMES = {"1": "1st", "2": "2nd", "3": "3rd"}


def parse_half(text: str) -> tuple[int, str]:
    t = text.lower()
    m = re.search(r"(top|bottom|bot)", t)
    n = re.search(r"(\d+)", t)
    if not m or not n:
        raise SystemExit(f'Could not read an inning from {text!r} (try "bottom 2")')
    return int(n.group(1)), "top" if m.group(1) == "top" else "bottom"


def parse_bases(text: str) -> str:
    t = text.lower().strip()
    if t in BASE_WORDS:
        return BASE_WORDS[t]
    if not t or set(t) - set("0123_-,. "):
        raise SystemExit(f"Could not read bases from {text!r} (try 13, 1_3, empty, loaded)")
    return "".join(b if b in t else "_" for b in "123")


def ordinal(n: int) -> str:
    return f"{n}{'st' if n == 1 else 'nd' if n == 2 else 'rd' if n == 3 else 'th'}"


def describe(inning: int, half: str, outs: int, bases: str, start: bool) -> str:
    runners = [BASE_NAMES[b] for b in bases if b != "_"]
    if not runners:
        on = "bases empty"
    elif len(runners) == 3:
        on = "bases loaded"
    else:
        on = f"runner{'s' if len(runners) > 1 else ''} on {' and '.join(runners)}"
    if start:
        return f"start of the {half} of the {ordinal(inning)}, {on}"
    return f"{half} of the {ordinal(inning)}, {outs} out, {on}"


def game_over(inning: int, half: str, diff: int, start: bool) -> str | None:
    """Who has already won, if the state given is past the end of the game."""
    if half == "bottom" and inning >= REGULATION and diff > 0:
        return "home"          # never needed to bat, or already walked off
    if half == "top" and inning > REGULATION and start and diff != 0:
        return "home" if diff > 0 else "away"
    return None


def data_note() -> str:
    games = tables.read("games", "training")
    done = games[games["is_final"] & ~games["is_phantom_duplicate"]]
    note = (f"{len(done)} completed games ({int(done['is_regular_season'].sum())} regular season) "
            f"through {done['game_date'].max()}, excluding {len(tables.TRAINING_EXCLUDED)} "
            f"(tables.TRAINING_EXCLUDED)")
    cut = tables.cutoff_play()
    if cut is None:
        return note
    game = tables.read("games", "all").set_index("game_id").loc[cut["game_id"]]
    return (f"{note}, plus {game['away_team_name']} at {game['home_team_name']} on "
            f"{cut['game_date']} up to the {cut['half']} of the {ordinal(int(cut['inning']))}.\n"
            f"       Cutoff is before play {cut['sequence']}: {cut['narrative']!r}; "
            f"that half-inning is left out")


def main() -> None:
    p = argparse.ArgumentParser(description="WPBL win probability for one game state")
    when = p.add_mutually_exclusive_group(required=True)
    when.add_argument("--after", help='half-inning just completed, e.g. "bottom 2"')
    when.add_argument("--before", help='half-inning about to start, e.g. "top 3"')
    when.add_argument("--during", help='half-inning in progress, e.g. "top 5"')
    when.add_argument("--pregame", action="store_true", help="before first pitch")
    p.add_argument("--away", type=int, help="away team runs")
    p.add_argument("--home", type=int, help="home team runs")
    p.add_argument("--outs", type=int, help="outs so far this half-inning (0-2)")
    p.add_argument("--bases", help="occupied bases: 13, 1_3, 123, empty, loaded, ...")
    p.add_argument("--away-team", help='away team, loosely: "LA", "Queens", "boston"')
    p.add_argument("--home-team", help="home team, same")
    p.add_argument("--cutoff", metavar="GAME_ID:SEQUENCE",
                   help="fit on what had happened before this play, postseason included")
    args = p.parse_args()
    tables.set_cutoff(args.cutoff)

    if args.pregame:
        inning, half, away, home = 1, "top", 0, 0
    else:
        if args.away is None or args.home is None:
            raise SystemExit("Need both --away and --home.")
        away, home = args.away, args.home
        inning, half = parse_half(args.after or args.before or args.during)
        if args.after:
            inning, half = (inning, "bottom") if half == "top" else (inning + 1, "top")
    start = args.during is None and args.outs is None and args.bases is None
    outs = args.outs or 0
    # An extra half-inning starts with a runner placed on second.
    bases = parse_bases(args.bases) if args.bases else ("_2_" if inning > REGULATION else "___")
    if not 0 <= outs <= 2:
        raise SystemExit("--outs must be 0, 1 or 2.")
    if (args.away_team is None) != (args.home_team is None):
        raise SystemExit("Name both --away-team and --home-team, or neither.")
    diff = home - away

    print(f"Model: {data_note()} (`pixi run refresh` to update)")
    print(f"State: {describe(inning, half, outs, bases, start)}; away {away} - home {home}")
    winner = game_over(inning, half, diff, start)
    if winner:
        print(f"  Game over: the {winner} team has won.")
        return

    model = Model()
    hp = model.win_probability(inning, half, outs, bases, diff)
    print("\nLeague model (every team average):")
    print(f"  Away wins: {1 - hp:6.1%}")
    print(f"  Home wins: {hp:6.1%}")
    if args.away_team is None:
        return

    ts = TeamStrength(model)
    a, h = ts.find(args.away_team), ts.find(args.home_team)
    if a == h:
        raise SystemExit("Away and home are the same team.")
    wp = ts.win_probability(a, h, inning, half, outs, bases, diff)
    lo, hi = np.percentile(wp, [5, 95])
    print(f"\nTeam-adjusted, {ts.names[a]} at {ts.names[h]}:")
    print(f"  Away wins: {1 - wp.mean():6.1%}   90% interval [{1 - hi:.1%}, {1 - lo:.1%}]")
    print(f"  Home wins: {wp.mean():6.1%}   90% interval [{lo:.1%}, {hi:.1%}]")
    runs_a = expected_runs(ts.base, ts.tilt_for(a, h)).mean()
    runs_h = expected_runs(ts.base, ts.tilt_for(h, a)).mean()
    league = expected_runs(ts.base, ts.samples[:, 0]).mean()
    print(f"  Expected runs per half-inning: {ts.short(a)} {runs_a:.2f}, "
          f"{ts.short(h)} {runs_h:.2f} (league {league:.2f})")
    print(f"  ({len(ts.samples)} posterior draws of team strength; `pixi run teams` "
          f"for the ratings)")


if __name__ == "__main__":
    main()
