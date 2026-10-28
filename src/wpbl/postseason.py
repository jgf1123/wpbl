"""Simulate the 2026 WPBL postseason with the manager AI (manager_spec.md).

    pixi run postseason [--until 0.01] [--max 20000] [--seed 1]
    pixi run postseason --log games/sim --seed 7

The bracket and calendar are 2026's (user, 2026-10-10):

  semifinal  SFF (1) v BOS (4), best of 3: 9 Sep at SFF, 11 Sep at BOS, 13 Sep at SFF
  semifinal  NYH (2) v LAQ (3), best of 3: 10 Sep at NYH, 12 Sep at LAQ, 14 Sep at NYH
  final      X = SFF/BOS winner v Y = NYH/LAQ winner, best of 5:
             16, 17 Sep at X; 19, 20 Sep at Y; 22 Sep at X

Pitch counts start from the user's chart for the morning of 9 Sep and recover
20 a day, every calendar day, for the whole league; "if needed" games are
skipped once a series is decided.

Both teams are managed by B2 (`manager.Planner`), with the postseason settings
the user chose: the lineup conventions; relief from the fallback ladder
(relievers, then starters not held for a start, then disfavored pitchers, then
anyone); starters held only for games sure to be played ("guaranteed": all
hands when facing elimination). The starter is the shared starter rule's.

--until: simulate postseasons in batches until every team's championship
probability has a standard error under the given value (default 0.01, one
percentage point), then report each team's chances.

--log: play one postseason and write each game as markdown, with a manager's
note before every pitching change, plus a .jsonl of the same game for
game_facts.py. Output only: `pixi run play` cannot replay
these, because the AI decides before every plate appearance.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np

from wpbl import engine, manager as M, play, usage

FATIGUE_0909 = {     # the user's chart: pitch counts on the morning of 9 Sep 2026
    "Ayami Sato": -30, "Kelsie Whitmore": -30, "Gigi Schiano": 3, "Michelle Roche": -30,
    "Liz Gilder": -30, "Niki Eckert": 8, "Rakyung Kim": -30, "Jamie Mackay": -30,
    "Kate Blunt": -30, "Alli Schroder": -30, "Claire OSullivan": -30, "Jill Albayati": -30,
    "Maika Dumais": -10, "Paloma Benach": -30, "Meggie Meidlinger": -30, "Jaida Lee": -30,
    "Peyton Coria": -30, "Ela Day Bedard": -30, "Emi Saiki": -10, "Jacqui Reynolds": -30,
    "London Studer": -30, "Ayuri Shimano": -30, "Isabella Villarreal": -30,
    "Raine Padgham": -30, "Claire Eccles": -30, "Olivia Bricker": -13,
    "Thaima Maximiliana": -30, "Amira Hondras": -30, "Keira Izumi": -30,
    "Rosi del Castillo": -30, "Alyssa Zettlemoyer": -30, "Addisyn Baird": -30,
    "Jua Park": -30, "Suzu Narasaki": -30, "Andreanne Leblanc": -30, "Maggie Foxx": -30,
    "Brittany Apgar": -30, "Adelaide Frank": -30,
}
START = dt.date(2026, 9, 9)
D = lambda day: dt.date(2026, 9, day)


class Series:
    def __init__(self, name, a, b, need, games):
        self.name, self.teams, self.need = name, (a, b), need
        self.games = games                  # [(date, home)]
        self.wins = {a: 0, b: 0}
        self.winner = None
        self.played = 0

    def due(self, date):
        if self.winner is not None or self.played >= len(self.games):
            return None
        d, home = self.games[self.played]
        return home if d == date else None

    def later(self):
        return [d for d, _ in self.games[self.played + 1:]]


def bracket():
    s1 = Series("Semifinal SFF-BOS", "SFF", "BOS", 2, [(D(9), "SFF"), (D(11), "BOS"), (D(13), "SFF")])
    s2 = Series("Semifinal NYH-LAQ", "NYH", "LAQ", 2, [(D(10), "NYH"), (D(12), "LAQ"), (D(14), "NYH")])
    return s1, s2


def final(x, y):
    return Series(f"Final {x}-{y}", x, y, 3,
                  [(D(16), x), (D(17), x), (D(19), y), (D(20), y), (D(22), x)])


def manager_for(model, team, series, date, fatigue, starter, explain):
    p = M.Planner(model, team)
    p.use_ladder, p.explain, p.reserve = True, explain, "guaranteed"
    other = next(t for t in series.teams if t != team)
    p.record, p.need = (series.wins[team], series.wins[other]), series.need
    later = [(d - date).days for d in series.later()]
    p.future = later
    sure = series.need - max(series.wins.values()) - 1      # games certain to be played after today
    p.protected = M.protected(model, team, fatigue, starter, later[:max(sure, 0)])
    return p


def play_game(model, series, date, home, fatigue, rng, explain=False):
    cards, wp = model.cards, model.wp
    away = next(t for t in series.teams if t != home)
    lineups, steps = {}, {}
    for t in (away, home):
        st, steps[t] = M.usage_starter_step(model, t, fatigue)
        lineups[t] = {"pitcher": st, "order": M.lineup_text(M.starting_nine(model, t, st))}
    setup = {"seed": int(rng.integers(1 << 31)), "date": date, "cards": cards.version,
             "away": away, "home": home, "lineup": lineups, "fatigue": dict(fatigue)}
    g = play.Game(setup, [], cards, wp)
    pols = {t: manager_for(model, t, series, date, fatigue, lineups[t]["pitcher"], explain)
            for t in (away, home)}
    g.manager = lambda g_, at, side: pols[side.team](g_, at, side)
    g.every_pa = True
    g.run()
    return g, lineups, steps


def postseason(model, seed, log_dir=None):
    """One postseason. Returns {"semis": (w1, w2), "champion": ..., "finalists": ...}."""
    rng = np.random.default_rng(seed)
    cards = model.cards
    fatigue = {n: FATIGUE_0909.get(n, engine.RESTED) for n in cards.pitcher}
    s1, s2 = bracket()
    fin = None
    day = START
    lines = [f"# Simulated 2026 postseason, seed {seed}", ""]
    while True:
        active = [s for s in (s1, s2, fin) if s is not None]
        for s in active:
            home = s.due(day)
            if home is None:
                continue
            before = dict(fatigue)
            g, lineups, steps = play_game(model, s, day, home, fatigue, rng, explain=log_dir is not None)
            for t in s.teams:                    # only this game's two staffs change
                for n in cards.team_pitchers(t):
                    fatigue[n] = g.fatigue[n]
            win = g.home.team if g.home.runs > g.away.runs else g.away.team
            gn = s.played + 1
            rec = dict(s.wins)
            s.wins[win] += 1
            s.played += 1
            if s.wins[win] == s.need:
                s.winner = win
            if log_dir is not None:
                write_game(model, log_dir, s, gn, rec, day, g, lineups, steps, before)
            lines.append(f"- {day:%d %b}: {s.name} game {gn}: {g.away.team} {g.away.runs}, "
                         f"{g.home.team} {g.home.runs}"
                         + (f" -- {s.winner} win the series {s.wins[s.winner]}-"
                            f"{min(s.wins.values())}" if s.winner else ""))
        if fin is None and s1.winner and s2.winner:
            fin = final(s1.winner, s2.winner)
        if fin is not None and fin.winner:
            break
        day += dt.timedelta(days=1)
        fatigue = {n: engine.recover(c, 1) for n, c in fatigue.items()}
        if day > D(22):
            raise AssertionError("postseason ran past 22 Sep")
    if log_dir is not None:
        lines += ["", f"**Champion: {fin.winner}**", ""]
        (Path(log_dir) / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"semis": (s1.winner, s2.winner), "finalists": fin.teams, "champion": fin.winner}


def write_game(model, log_dir, s, gn, rec, day, g, lineups, steps, before):
    cards = model.cards
    away, home = g.away.team, g.home.team
    roles = model.usage.starters
    out = [f"# {away} @ {home}, {day:%Y-%m-%d}: {s.name}, game {gn}",
           "",
           f"Series before the game: {', '.join(f'{t} {rec[t]}' for t in s.teams)}. "
           f"Simulated: both teams managed by B2 (manager_spec.md); output only, not "
           f"replayable by `pixi run play`.",
           ""]
    for t in (away, home):
        st = lineups[t]["pitcher"]
        out += [f"## {t}", "",
                f"Starter: {st}, pitch count {before[st]} (enters at {engine.enter(before[st])}, "
                f"stamina {cards.stamina(st)}; starter rule step {steps[t]})", "",
                "Lineup: " + ", ".join(lineups[t]["order"]), "",
                "Staff before the game (count, stamina, role):", ""]
        for n in cards.team_pitchers(t):
            role = ("starter" if n in roles[t] else "reliever") + (", disfavored" if n in M.DISFAVORED else "")
            out.append(f"- {n}: {before[n]}, {cards.stamina(n)}, {role}")
        out.append("")
    out += ["## Play by play", "", g.joined()]
    path = Path(log_dir) / f"{day:%Y-%m-%d}_{away}-at-{home}.md"
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    # the same game as data, for game_facts.py: a header line, then one line per event
    head = {"event": "game", "cards": cards.version, "date": day.isoformat(),
            "series": s.name, "game": gn,
            "need": s.need, "record_before": rec, "away": away, "home": home,
            "runs": {away: g.away.runs, home: g.home.runs},
            "line": {away: g.away.line, home: g.home.line},
            "lineup": {t: lineups[t]["order"] for t in (away, home)},
            "starter": {t: lineups[t]["pitcher"] for t in (away, home)},
            "staff": {t: [{"name": n, "count": before[n], "stamina": cards.stamina(n),
                           "starter": n in roles[t], "disfavored": n in M.DISFAVORED}
                          for n in cards.team_pitchers(t)] for t in (away, home)},
            "fatigue_after": {n: g.fatigue[n] for t in (away, home)
                              for n in cards.team_pitchers(t)}}
    with path.with_suffix(".jsonl").open("w", encoding="utf-8", newline="\n") as f:
        for row in [head] + g.events:
            f.write(json.dumps(row, default=str) + "\n")


def odds(model, until, cap, seed):
    teams = ["SFF", "NYH", "LAQ", "BOS"]
    semi, finals, champ, pairs = Counter(), Counter(), Counter(), Counter()
    n, t0 = 0, time.time()
    while n < cap:
        for _ in range(100):
            r = postseason(model, seed + n)
            n += 1
            for t in r["semis"]:
                semi[t] += 1
            champ[r["champion"]] += 1
            pairs[tuple(r["finalists"])] += 1
        se = max(np.sqrt(champ[t] / n * (1 - champ[t] / n) / n) for t in teams)
        print(f"  {n} postseasons, {time.time() - t0:.0f}s: largest standard error {100 * se:.2f} points",
              flush=True)
        if se < until and n >= 200:
            break
    print(f"\n{n} simulated postseasons (B2 managing both sides)\n")
    print("| team | reach the final | win the title |")
    print("|---|---|---|")
    for t in teams:
        f, c = semi[t] / n, champ[t] / n
        print(f"| {t} | {100 * f:.1f}% +/- {100 * np.sqrt(f * (1 - f) / n):.1f} | "
              f"{100 * c:.1f}% +/- {100 * np.sqrt(c * (1 - c) / n):.1f} |")
    print("\nfinals:")
    for (x, y), k in pairs.most_common():
        print(f"  {x} v {y}: {100 * k / n:.1f}%")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="postseason")
    ap.add_argument("--until", type=float, default=0.01,
                    help="stop when every team's title probability has this standard error")
    ap.add_argument("--max", type=int, default=20000, help="at most this many postseasons")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--log", default=None, help="play one postseason and write its games here")
    ap.add_argument("--out", nargs="*", default=[],
                    help="players unavailable for the whole postseason (injured): neither pitch nor bat")
    a = ap.parse_args(argv)
    cards, wp = play.shared()
    for name in a.out:                       # injured: gone from every lineup, rotation and bullpen
        if name not in cards.pitcher and name not in cards.batter:
            raise SystemExit(f"--out: no card for {name}")
        for table in (cards.pitcher, cards.batter, cards.pitch_faces, cards.bat_faces):
            table.pop(name, None)
        print(f"unavailable: {name}")
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    missing = [n for n in FATIGUE_0909 if n not in cards.pitcher and n not in a.out]
    if missing:
        raise SystemExit(f"fatigue chart names without a pitcher card: {missing}")
    if a.log:
        Path(a.log).mkdir(parents=True, exist_ok=True)
        r = postseason(model, a.seed, a.log)
        print(f"champion {r['champion']} (semifinal winners {r['semis'][0]}, {r['semis'][1]}); "
              f"games written to {a.log}")
    else:
        odds(model, a.until, a.max, a.seed)


if __name__ == "__main__":
    main()
