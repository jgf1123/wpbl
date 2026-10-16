"""Fact sheet for a simulated postseason game: the raw material for a write-up.

    pixi run facts games/postseason_000003                  # every game in the folder
    pixi run facts games/postseason_000003/2026-09-16_LAQ-at-SFF.jsonl

Reads the .jsonl that `postseason --log` writes beside each game's markdown and
writes <game>.facts.md next to it. Nothing here is prose: it is the list of
facts a write-up may draw on, so every claim in the write-up can be traced to a
row.

- Pitchers: when each entered and left, and why (the manager's note); innings
  pitched against the innings her count allowed on entering (the manager's own
  projection, `Planner.stint`: fresh column to 20, then fading, until gassed),
  so an early or late exit shows up as a difference. The dice game charges
  each batter the average pitches for the outcome, so the difference comes
  from facing more or fewer batters than usual, not from long at-bats.
- Half-innings: batters, runs, pitch count spent; "long" (LONG_BF+ batters)
  and "quick" (three up, three down); the leverage index at the start (dice
  model, average half-inning start 1.00); movement = sum of |change in win
  probability| over the half and back-and-forth = movement - |net change|,
  as in rollercoaster.py.
- Pitching decisions: the reason, the choice, the runner-up, and what the
  manager projected the choice saved (runs to the end of regulation, warm-ups)
  -- definitions in manager_spec.md, "B2: runs to the end, warm-ups priced".
- The biggest swings in the winner's win probability, lead changes and ties,
  the winner's low point, every scoring play (lead changes and ties marked;
  runs on running plays told apart from the batted ball's), and pitch counts
  after the game.
- Players: win probability added (WPA) and RE24 (runs added from the base-out
  state, as in game_timeline.py), batting and pitching together; the MVP has
  the best MVP score, a weighted sum of WPA and RE24 (RE24 converted to win
  probability at the value of a run at an average half-inning start, about
  0.062): WPA rewards timing, RE24 the run production itself, which keeps an
  early big inning in a blowout from counting for almost nothing. Co-MVPs
  score at least CO_MVP of the best.

Win probability is the dice game's (play.WinProbability), the same number the
log prints. Runs are charged as in baseball, to the pitcher who let the runner
on -- not earned runs.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

from wpbl import engine, manager as M, play

LONG_BF = 8          # batters in a half-inning to call it long (real 2026: 90th percentile)
N_SWINGS = 6
CLOSE_CALL = 0.5     # thousandths of series win probability: runner-up within this is a coin flip
CLEAR_CALL = 2.0     # and beyond this a clear choice
EXIT_OUTS = 3        # outs short of or beyond the expected exit to call it early or late
WPA_WEIGHT = 0.5     # MVP score = WPA_WEIGHT x win probability added
RE_WEIGHT = 0.5      #           + RE_WEIGHT x RE24 x the win probability of a run at an average half-inning start
CO_MVP = 0.9         # co-MVPs: at least this share of the best player's MVP score
HITS = ("1B", "2B", "3B", "HR")


def state(text):
    """'1 out _2_' -> (1, (False, True, False)); '3 out' -> (3, (False,) * 3)."""
    outs, _, rest = text.partition(" out")
    bases = rest.strip()
    return int(outs), tuple(c != "_" for c in bases) if bases else (False,) * 3


def ip(outs):
    return f"{outs // 3}.{outs % 3}"


def read(path):
    rows = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    return rows[0], rows[1:]


def exit_vs(outs, expected):
    """'4.1, -2' or '3.2, +3 late': expected IP, then outs pitched beyond it."""
    d = outs - round(3 * expected)
    tag = " early" if d <= -EXIT_OUTS else " late" if d >= EXIT_OUTS else ""
    return f"{ip(round(3 * expected))}, {d:+d}{tag}"


def half_flag(pas):
    """'long', 'quick' (three up, three down) or ''."""
    if len(pas) >= LONG_BF:
        return "long"
    return "quick" if len(pas) == 3 and all(e["line"] in ("OUT", "K") for e in pas) else ""


def wp_steps(head, events):
    """Events that move win probability, each with home WP before and after.
    A walk-off's after is a home win."""
    out = []
    for e in events:
        if e["event"] == "pa" or (e["event"] == "steal" and e.get("result") in ("safe", "out")):
            after = e.get("wp_home")
            if after is None:
                after = 1.0
            out.append((e, e["wp_before"], after))
    return out


def facts(head, events, model):
    away, home = head["away"], head["home"]
    runs = head["runs"]
    winner = home if runs[home] > runs[away] else away
    w = lambda p: p if winner == home else 1 - p          # winner's WP from home WP
    stam = {p["name"]: p["stamina"] for t in (away, home) for p in head["staff"][t]}
    steps = wp_steps(head, events)
    L = []

    # -- header ------------------------------------------------------------------------
    rec = head["record_before"]
    after = dict(rec)
    after[winner] += 1
    teams = list(rec)
    L += [f"# Facts: {away} {runs[away]} @ {home} {runs[home]}, {head['date']}",
          "",
          f"{head['series']}, game {head['game']}. Series before: "
          + ", ".join(f"{t} {rec[t]}" for t in teams) + "; after: "
          + ", ".join(f"{t} {after[t]}" for t in teams)
          + (f" -- {winner} win the series" if after[winner] == head["need"] else "") + ".",
          ""]
    n = max(len(v) for v in head["line"].values())
    L += ["| | " + " | ".join(str(i + 1) for i in range(n)) + " | R |",
          "|---" * (n + 2) + "|"]
    for t in (away, home):
        cells = [str(x) for x in head["line"][t]] + ["x"] * (n - len(head["line"][t]))
        L.append(f"| {t} | " + " | ".join(cells) + f" | {runs[t]} |")
    total = sum(abs(a - b) for _, b, a in steps)
    low = min(((w(a), e) for e, _, a in steps), key=lambda x: x[0])
    L += ["",
          f"Movement (sum of |change in win probability|): {100 * total:.0f} points. "
          f"{winner}'s low point: {100 * low[0]:.0f}%, after {low[1].get('batter', low[1].get('runner'))}'s "
          f"{low[1].get('line', 'steal')} ({low[1]['half']} {low[1]['inning']}; {away} {low[1]['away_runs']}, "
          f"{home} {low[1]['home_runs']}).", ""]

    # -- pitchers ----------------------------------------------------------------------
    current = dict(head["starter"])
    stints, order = {}, []

    def stint(name, team):
        if name not in stints:
            stints[name] = {"team": team, "pa": [], "outs": 0, "runs": 0, "wpa": 0.0,
                            "fading": None, "gassed": None, "exit": "finished the game",
                            "decision": None}
            order.append(name)
        return stints[name]

    last_decision, responsible, on_base, half_key = {}, {}, set(), None
    for e in events:
        k = e["event"]
        if k == "decision":
            last_decision[e["fielding"]] = e
        elif k == "change" and e["pitcher"] != e["replaced"]:
            d = last_decision.get(e["fielding"])
            s = stint(e["replaced"], e["fielding"])
            why = d["why"] if d and d["pitcher"] == e["replaced"] else "replaced"
            s["exit"] = f"{why}: {e['half']} {e['inning']}, {d['outs_before'] if d else ''}".rstrip(", ")
            s["decision"] = d
            current[e["fielding"]] = e["pitcher"]
        elif k == "pa":
            s = stint(e["pitcher"], e["fielding"])
            s["pa"].append(e)
            o0, _ = state(e["outs_before"])
            o1, _ = state(e["outs_after"]) if e.get("outs_after") else (o0, None)
            s["outs"] += o1 - o0
            if (e["inning"], e["half"]) != half_key:
                half_key, on_base, responsible = (e["inning"], e["half"]), set(), {}
            for r in e["scorers"]:                 # charged to whoever let her on; the batter: this pitcher
                stints[responsible[r] if r in on_base else e["pitcher"]]["runs"] += 1
            now = {r for r in e["runners"] if r}
            forced = [r for r in on_base - now if r not in e["scorers"]]
            for r in now - on_base:                # reached in this plate appearance: hers,
                # unless she reached as another runner was forced out: then that runner's
                # pitcher stays responsible (fielder's choice, as in baseball scoring)
                responsible[r] = responsible[forced.pop()] if forced and r == e["batter"] else e["pitcher"]
            on_base = now
            for col in ("fading", "gassed"):
                if e["column"] == col and s[col] is None:
                    s[col] = ("on entering" if len(s["pa"]) == 1 else
                              f"{e['half'][0].upper()}{e['inning']}, {state(e['outs_before'])[0]} out, "
                              f"before {e['batter']}") + f" (count {e['count_before']})"
        elif k == "steal" and e.get("result") == "out":
            stint(current[e["fielding"]], e["fielding"])["outs"] += 1
    for e, b, a in steps:
        if e["event"] == "pa":
            stints[e["pitcher"]]["wpa"] += (a - b) * (1 if e["fielding"] == home else -1)
    halves = defaultdict(list)
    for e, b, a in steps:
        halves[(e["inning"], e["half"])].append((e, b, a))
    flags = {k: half_flag([e for e, _, _ in rows if e["event"] == "pa"]) for k, rows in halves.items()}

    L += ["## Pitchers", "",
          "Expected IP (only for a pitcher who left gassed): innings until gassed from her count "
          "on entering, as the manager projects them, to the nearest out; then outs pitched beyond "
          f"it, early or late at {EXIT_OUTS}+ outs either way (most starters land about 2 outs "
          "short, so less is not a story). Runs: charged as in "
          "baseball, to the pitcher who let the runner on (not earned runs). Long and quick: "
          "the half-innings she pitched in that were.", "",
          "| team | pitcher | entered | count in → out (stamina) | fading / gassed from | BF | IP | expected IP, outs beyond | long / quick | runs | WPA | left |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for name in order:
        s = stints[name]
        if not s["pa"]:
            continue
        f = s["pa"][0]
        mine = f["away_runs"] if s["team"] == away else f["home_runs"]
        theirs = (f["home_runs"] if s["team"] == away else f["away_runs"]) - f["scored"]  # before her first PA
        exp_inn, _ = M.Planner(model, s["team"]).stint(name, f["count_before"], 99)
        mine_halves = list(dict.fromkeys((e["inning"], e["half"]) for e in s["pa"]))
        lq = [", ".join(f"{h[0].upper()}{i}" for i, h in mine_halves if flags.get((i, h)) == fl) or "-"
              for fl in ("long", "quick")]
        L.append(f"| {s['team']} | {name} | {f['half'][0].upper()}{f['inning']}, {f['outs_before']}, "
                 f"{'up' if mine > theirs else 'down' if mine < theirs else 'tied'} {mine}-{theirs} | "
                 f"{f['count_before']} → {s['pa'][-1]['pitch_count']} ({stam[name]}) | "
                 f"{s['fading'] or '-'} / {s['gassed'] or '-'} | {len(s['pa'])} | {ip(s['outs'])} | "
                 f"{exit_vs(s['outs'], exp_inn) if s['exit'].startswith('gassed') else '-'} | {lq[0]} / {lq[1]} | {s['runs']} | {100 * s['wpa']:+.0f} | {s['exit']} |")
    L.append("")

    # -- half-innings ------------------------------------------------------------------
    L += ["## Half-innings", "",
          f"Long: {LONG_BF}+ batters. Quick: three up, three down. Leverage: at the start "
          "(average 1.00). Movement and back-and-forth in win-probability points.", "",
          "| half | batting | pitcher(s) | BF | runs | count spent | flag | leverage | batting WP start → end | movement | back-and-forth |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for (inn, half), rows in sorted(halves.items(), key=lambda x: (x[0][0], x[0][1] == "bottom")):
        pas = [e for e, _, _ in rows if e["event"] == "pa"]
        bat = rows[0][0]["batting"]
        bwp = (lambda p: p) if bat == home else (lambda p: 1 - p)
        start, end = bwp(rows[0][1]), bwp(rows[-1][2])
        move = sum(abs(a - b) for _, b, a in rows)
        first = rows[0][0]
        diff = first["home_runs"] - first["away_runs"]
        lev = model.leverage(inn, half == "top", 0, (False, inn > engine.INNINGS, False), diff)
        pitchers = list(dict.fromkeys(e["pitcher"] for e in pas))
        spent = sum(e["pitch_count"] - e["count_before"] for e in pas)
        bf, flag = len(pas), flags[(inn, half)]
        L.append(f"| {half[0].upper()}{inn} | {bat} | {', '.join(pitchers)} | {bf} | "
                 f"{sum(e['scored'] for e in pas)} | {spent} | {flag} | {lev:.2f} | "
                 f"{100 * start:.0f}% → {100 * end:.0f}% | {100 * move:.0f} | "
                 f"{100 * (move - abs(end - start)):.0f} |")
    L.append("")

    # -- decisions ---------------------------------------------------------------------
    decs = [e for e in events if e["event"] == "decision"]
    L += ["## Pitching decisions", "",
          "Runs saved and warm-ups: the choice against the runner-up, in the manager's "
          "projection. Margin: the runner-up's score, thousandths of series win probability "
          f"(coin flip under {CLOSE_CALL}, clear over {CLEAR_CALL}).", ""]
    for d in decs:
        opts = d["options"]
        chosen = next(o for o in opts if (("keep " + o["name"]) if o["keep"] else o["name"]) == d["chosen"])
        rest = [o for o in opts if o is not chosen]
        team = d["fielding"]
        mine = d["away_runs"] if team == away else d["home_runs"]
        theirs = d["home_runs"] if team == away else d["away_runs"]
        line = (f"- {d['half'][0].upper()}{d['inning']}, {d['outs_before']}, {team} "
                f"{'up' if mine > theirs else 'down' if mine < theirs else 'tied'} {mine}-{theirs}: "
                f"{d['pitcher']} ({d['count']}) -- {d['why']}, run value {d['run_value']:.2f}. "
                f"{team} chose {d['chosen']} (enters at {chosen['count']}, {chosen['column']}).")
        if rest:
            r = rest[0]
            m = -r["score"]
            call = "coin flip" if m < CLOSE_CALL else "clear" if m > CLEAR_CALL else "close"
            line += (f" Runner-up {'keep ' if r['keep'] else ''}{r['name']} ({r['count']}, {r['column']}): "
                     f"{r['runs_to_end'] - chosen['runs_to_end']:+.2f} runs saved, "
                     f"{r['warmups'] - chosen['warmups']:+.1f} warm-ups saved, margin {m:.2f} ({call}).")
            k = next((o for o in rest[1:] if o["keep"]), None)
            if k:                                  # why she came out, when keeping her was allowed
                line += (f" Keeping {k['name']} ({k['count']}, {k['column']}): "
                         f"{k['runs_to_end'] - chosen['runs_to_end']:+.2f} runs saved, "
                         f"{k['warmups'] - chosen['warmups']:+.1f} warm-ups saved, margin {-k['score']:.2f}.")
        L.append(line)
    # what each change did to the lineup
    lineup = {t: [x.rsplit(" ", 1) for x in head["lineup"][t]] for t in (away, home)}
    for e in events:
        if e["event"] != "change":
            continue
        t = e["fielding"]
        new = [x.rsplit(" ", 1) for x in e["lineup"].split(" | ")]
        old_pos = dict(lineup[t])
        notes = []
        if e["pitcher"] in old_pos and old_pos[e["pitcher"]] != "P":
            notes.append(f"{e['pitcher']} moves {old_pos[e['pitcher']]} → P")
        notes += [f"{nm} enters at {pos}" for nm, pos in new if nm not in old_pos and pos != "P"]
        if any(p == "DH" for _, p in lineup[t]) and not any(p == "DH" for _, p in new):
            notes.append(f"{t} lose the DH")
        if notes:
            L.append(f"- Lineup ({t}, {e['half'][0].upper()}{e['inning']}): " + "; ".join(notes) + ".")
        lineup[t] = new
    L.append("")

    # -- swings, leads -----------------------------------------------------------------
    L += ["## Biggest swings", "", f"Winner's ({winner}) win probability before → after.", ""]
    big = sorted(steps, key=lambda x: -abs(x[2] - x[1]))[:N_SWINGS]
    for e, b, a in sorted(big, key=lambda x: events.index(x[0])):
        who = (f"{e['batter']} {e['line']} off {e['pitcher']}" if e["event"] == "pa"
               else f"{e['runner']} steal {e['result']}")
        sc = f", {e['scored']} scored" if e.get("scored") else ""
        L.append(f"- {e['half'][0].upper()}{e['inning']}{', ' + e['outs_before'] if 'outs_before' in e else ''}: {who}{sc}; "
                 f"{away} {e['away_runs']}, {home} {e['home_runs']} after. "
                 f"{100 * w(b):.0f}% → {100 * w(a):.0f}% ({100 * (w(a) - w(b)):+.0f}).")
    L += ["", "## Scoring plays", "",
          "Every plate appearance on which a run scored. A running play is the dice game's wild "
          "pitch or passed ball, rolled before the batted ball: its runs are not RBIs.", ""]
    lead = 0
    for e in events:
        if e["event"] != "pa" or not e["scored"]:
            continue
        rp = e.get("run_play_scored", 0)
        how = [f"{rp} on a running play"] if rp else []
        if e["scored"] > rp:
            how.append(f"{e['scored'] - rp} on the {e['line']}")
        diff = e["home_runs"] - e["away_runs"]
        now = (diff > 0) - (diff < 0)
        mark = ""
        if now != lead:
            mark = " **Tie.**" if now == 0 else f" **{home if now > 0 else away} lead.**"
            lead = now
        L.append(f"- {e['half'][0].upper()}{e['inning']}, {e['outs_before']}: {e['batter']} {e['line']} "
                 f"off {e['pitcher']}; {', '.join(how)}. {away} {e['away_runs']}, {home} {e['home_runs']}.{mark}")
    L.append("")

    # -- players: batting and pitching together --------------------------------------
    def re(text):
        o, bases = state(text)
        return 0.0 if o >= 3 else float(model.wp.dist(o, bases) @ np.arange(len(model.wp.dist(o, bases))))

    ppl = defaultdict(lambda: {"team": None, "pa": 0, "lines": [], "rbi": 0, "bat_wpa": 0.0,
                               "bat_re": 0.0, "pit_wpa": 0.0, "pit_re": 0.0})
    for e, b, a in steps:
        bat_gain = (a - b) * (1 if e["batting"] == home else -1)
        if e["event"] == "steal":
            ppl[e["runner"]]["team"] = e["batting"]
            ppl[e["runner"]]["bat_wpa"] += bat_gain
            continue
        runs_added = e["scored"] + (re(e["outs_after"]) if e.get("outs_after") else 0.0) - re(e["outs_before"])
        r = ppl[e["batter"]]
        r["team"] = e["batting"]
        r["pa"] += 1
        r["lines"].append(e["line"])
        r["rbi"] += e["scored"] - e.get("run_play_scored", 0)
        r["bat_wpa"] += bat_gain
        r["bat_re"] += runs_added
        q = ppl[e["pitcher"]]
        q["team"] = e["fielding"]
        q["pit_wpa"] -= bat_gain
        q["pit_re"] -= runs_added
    total = lambda r: r["bat_wpa"] + r["pit_wpa"]
    model.run_value(1, True, 0, (False,) * 3, 0)           # sets run_scale
    score = lambda r: WPA_WEIGHT * total(r) + RE_WEIGHT * model.run_scale * (r["bat_re"] + r["pit_re"])
    ranked = sorted(ppl.items(), key=lambda x: -score(x[1]))
    best = score(ranked[0][1])
    mvps = [n for n, r in ranked if score(r) >= CO_MVP * best]
    L += ["## Players", "",
          f"MVP: {' and '.join(f'{n} ({ppl[n]['team']}, {100 * score(ppl[n]):+.0f})' for n in mvps)}. "
          f"MVP score = {WPA_WEIGHT} x WPA + {RE_WEIGHT} x RE24 x {model.run_scale:.3f} (a run's win "
          f"probability at an average half-inning start), batting and pitching together, in points; "
          f"co-MVPs {100 * CO_MVP:.0f}% of the best or more. Listed: MVP score or WPA 5+ points either "
          "way, a home run, or 3+ hits. RE24 in runs (batting: runs added; pitching: runs saved) from "
          "the base-out state, ignoring score and inning. RBI: runs scored on her batted ball or walk, not on running plays.", "",
          "| team | player | PA | results | RBI | WPA bat | WPA pitch | WPA total | RE24 bat | RE24 pitch | MVP score |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    pitched = set(stints)
    for name, r in ranked:
        hits = sum(x in HITS for x in r["lines"])
        if (max(abs(total(r)), abs(score(r))) < 0.05 and "HR" not in r["lines"] and hits < 3):
            continue
        shown = [x for x in r["lines"] if x != "OUT"]
        L.append(f"| {r['team']} | {name} | {r['pa'] or '-'} | {' '.join(shown) or '-'} | "
                 f"{r['rbi'] if r['pa'] else '-'} | "
                 + (f"{100 * r['bat_wpa']:+.0f}" if r["pa"] else "-") + " | "
                 + (f"{100 * r['pit_wpa']:+.0f}" if name in pitched else "-") + f" | "
                 f"{100 * total(r):+.0f} | " + (f"{r['bat_re']:+.1f}" if r["pa"] else "-") + " | "
                 + (f"{r['pit_re']:+.1f}" if name in pitched else "-") + f" | {100 * score(r):+.0f} |")
    L.append("")

    # -- carry-over --------------------------------------------------------------------
    L += ["## Pitch counts after the game", "",
          "Recovery is 20 a day; entering adds 30; gassed at her stamina.", ""]
    for name in order:
        if stints[name]["pa"]:
            L.append(f"- {stints[name]['team']} {name}: {head['fatigue_after'][name]} "
                     f"(stamina {stam[name]})")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(prog="facts")
    ap.add_argument("path", help="a game's .jsonl, or a folder of them")
    a = ap.parse_args(argv)
    p = Path(a.path)
    files = sorted(p.glob("*.jsonl")) if p.is_dir() else [p]
    if not files:
        raise SystemExit(f"no .jsonl under {p}: rerun postseason --log to write them")
    models = {}
    for f in files:
        head, events = read(f)
        v = head.get("cards")
        if v not in models:
            models[v] = M.Model(*play.shared(v))
        out = f.with_suffix(".facts.md")
        out.write_text(facts(head, events, models[v]), encoding="utf-8", newline="\n")
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
