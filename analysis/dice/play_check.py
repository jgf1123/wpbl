"""Check `pixi run play` against the rulebook and against itself (tosw_play_spec.md).

    pixi run python analysis/dice/play_check.py

    the steal table      play.STEAL_TABLE is the rulebook's, cell for cell
    steal eligibility    every base state; p from the table for every cell
    win probability      a tied start is 0.5; a bigger lead never lowers it
    the log              a stop-by-stop game replays; an edited play-by-play,
                         seed or decision is refused, and nothing is written
    pitching changes     DH kept or pitcher's slot taken; re-entry, a fielder,
                         and a batless pitcher without a DH are refused
    three-batter min     no change before three batters or the end of a half;
                         the minimum carries into a half she starts
    whole games          runs add up, pitch counts add up, no ties, the home
                         team does not bat when already ahead after the top of
                         the 7th, extra innings place the last batter on 2nd,
                         caught stealing for the third out leads off next inning
    fatigue across days  --after recovers 20 a day to -30, a doubleheader
                         recovers nothing, each team from its own game
"""
import contextlib
import datetime as dt
import io
import re
import tempfile
from pathlib import Path

from wpbl import engine, play

ROOT = Path(__file__).resolve().parents[2]
cards, wp = play.shared()
failures = []


def check(cond, what):
    print(("ok   " if cond else "FAIL ") + what)
    if not cond:
        failures.append(what)


def refused(fn, *args):
    try:
        fn(*args)
    except play.Refused as e:
        return str(e)
    return None


# --- the steal table -----------------------------------------------------------
rules = (ROOT / "Two_Outs_So_What_rules.md").read_text(encoding="utf-8")
printed = {}
for m in re.finditer(r"^\| (2nd|3rd), (Goes|League) \| (.+?) \|\s*$", rules, re.M):
    cells = tuple(c.strip() for c in m.group(3).split("|"))
    printed[(int(m.group(1)[0]), m.group(2))] = cells
check(printed == play.STEAL_TABLE, "steal table matches the rulebook")

# --- steal eligibility and p -----------------------------------------------------
want = {"___": None, "1__": (1, 2), "_2_": (2, 3), "__3": None,
        "12_": (2, 3), "1_3": (1, 2), "_23": None, "123": None}
got = {s: play.steal_candidate([c != "_" for c in s]) for s in want}
check(got == want, "steal eligibility, all 8 base states")
spec_p = {(2, "Goes"): (0.5, 24 / 36, 33 / 36), (2, "League"): (0.5, 4 / 6, 5.5 / 6),
          (3, "Goes"): (0.5, 8 / 12, 11 / 12), (3, "League"): (0.5, 1.0, 1.0)}
check(all(abs(play.steal_p(b, a, c + 1) - spec_p[(b, a)][c]) < 1e-12
          for (b, a) in spec_p for c in range(3)), "steal p, spec section 5 table")
for (b, a), row in play.STEAL_TABLE.items():
    for c in (1, 2, 3):
        faces = play.steal_faces(b, a, c)
        none = play._steal_faces(row[0] + " none")
        check(sorted(set(faces) | set(none)) == list(range(100)) and not set(faces) & set(none),
              f"steal {b} {a} column {c} covers 00-99 once")

# --- win probability -------------------------------------------------------------
check(abs(wp.top(1, 0) - 0.5) < 1e-9, f"tied start of game is 0.5 ({wp.top(1, 0):.6f})")
bad = 0
for inning in range(1, 9):
    for half in ("top", "bottom"):
        for outs in range(3):
            for b in range(8):
                bases = [bool(b & 1), bool(b & 2), bool(b & 4)]
                vals = [wp.mid(inning, half, outs, bases, d) for d in range(-12, 13)]
                bad += sum(y < x - 1e-12 for x, y in zip(vals, vals[1:]))
check(bad == 0, f"home WP never falls as the home lead grows ({bad} violations)")
check(abs(wp.mid(3, "top", 3, [0, 0, 0], 1) - wp.bottom(3, 1)) < 1e-12,
      "three outs in the top hands over to the bottom")

# --- lineups for test games --------------------------------------------------------


def lineup(team, pitcher, dh=True):
    bats = sorted((b for b in cards.team_batters(team) if b != pitcher),
                  key=lambda n: -int(cards.batter[n]["PA"]))

    def assign(i, used):
        if i == len(play.POSITIONS):
            return {}
        for b in bats:
            if b not in used and play.POSITIONS[i] in cards.positions(b):
                r = assign(i + 1, used | {b})
                if r is not None:
                    r[play.POSITIONS[i]] = b
                    return r
        return None

    a = assign(0, frozenset())
    rest = [b for b in bats if b not in a.values()]
    order = [f"{b} {p}" for p, b in a.items()]
    order.append(f"{rest[0]} DH" if dh else f"{pitcher} P")
    return {"pitcher": pitcher, "order": order}


def setup(seed, away="SFF", home="LAQ", ap="Kelsie Whitmore", hp="Ayami Sato",
          dh=(True, True), fatigue=None):
    return {"seed": seed, "date": dt.date(2026, 10, 3), "cards": cards.version,
            "away": away, "home": home,
            "lineup": {away: lineup(away, ap, dh[0]), home: lineup(home, hp, dh[1])},
            "fatigue": fatigue or {}}


def game(s, manager=lambda g, at, side: "keep"):
    g = play.Game(s, [], cards, wp)
    g.manager = manager
    g.run()
    return g


# --- the log -----------------------------------------------------------------------
tmp = Path(tempfile.mkdtemp())


def write_setup(path, s):
    order = lambda t: "order = [\n" + "".join(f'  "{o}",\n' for o in s["lineup"][t]["order"]) + "]"
    text = (f"# test\n\n```tosw-setup\nseed = {s['seed']}\ndate = {s['date']}\n"
            f'cards = "{s["cards"]}"\naway = "{s["away"]}"\nhome = "{s["home"]}"\n'
            + "".join(f'\n[lineup.{t}]\npitcher = "{s["lineup"][t]["pitcher"]}"\n{order(t)}\n'
                      for t in (s["away"], s["home"]))
            + "\n[fatigue]\n" + "\n".join(play.fatigue_lines(s["fatigue"])) + "\n```\n")
    path.write_text(text, encoding="utf-8", newline="\n")


def play_to_end(path, edit=None):
    """Run `play` until the game is over. `edit(text, n)` may change the nth stop."""
    for n in range(500):
        before = path.read_text(encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            play.play(path)
        after =path.read_text(encoding="utf-8")
        if "```tosw-fatigue-after" in after:
            return n
        if edit:
            path.write_text(edit(after, n), encoding="utf-8", newline="\n")
        assert after != before
    raise AssertionError("no end")


log = tmp / "g.md"
write_setup(log, setup(7))
stops = play_to_end(log)
done = log.read_text(encoding="utf-8")
one_go = game(setup(7))
narrative = re.sub(r"```tosw-decision.*?```", "", done.split("```", 2)[2], flags=re.S)
lines = lambda t: [l.rstrip() for l in t.splitlines() if l.strip()]
check(lines(narrative) == lines(one_go.joined()),
      f"stop-by-stop log ({stops} stops) is the same game as playing straight through")
with contextlib.redirect_stdout(io.StringIO()):
    play.play(log)
check(log.read_text(encoding="utf-8") == done, "a finished log is left alone")

pa_line = next(l for l in done.splitlines() if l.startswith("- 0 out ___"))
for what, new_text in [
        ("an edited plate appearance", done.replace(pa_line, pa_line.replace("d100", "d100 1"), 1)),
        ("an edited seed", done.replace("seed = 7", "seed = 8")),
        ("an edited past decision",              # Top 3: a change the rules allow
         done[:done.index('at = "Top 3, start"')] + done[done.index('at = "Top 3, start"'):]
         .replace('pitcher = "keep"', 'pitcher = "Michelle Roche"', 1))]:
    log.write_text(new_text, encoding="utf-8", newline="\n")
    msg = refused(play.play, log)
    check(msg is not None and log.read_text(encoding="utf-8") == new_text,
          f"{what} is refused and nothing written: {msg and msg.splitlines()[0]}")

# a change made through the log, at the third stop (top 2, LAQ fielding)
log2 = tmp / "g2.md"
write_setup(log2, setup(7))


def change_at_third(text, n):
    if n == 2:
        i = text.rindex('pitcher = "keep"')
        return text[:i] + 'pitcher = "Michelle Roche"' + text[i + len('pitcher = "keep"'):]
    return text


play_to_end(log2, change_at_third)
t2 = log2.read_text(encoding="utf-8")
check("Pitching change (LAQ): Michelle Roche replaces Ayami Sato" in t2
      and "## Top 2 · SFF batting · Michelle Roche (LAQ) pitching" in t2,
      "a change written in the log is made before the half-inning")

# --- pitching changes -----------------------------------------------------------------


def change_once(team, name, at_text="Top 3, start"):
    def m(g, at, side):
        return name if at == at_text and side.team == team else "keep"
    return m


g = game(setup(11, dh=(True, False)), change_once("LAQ", "Michelle Roche"))
slot = [s for s in g.home.order if s.pos == "P"]
check(slot and slot[0].name == "Michelle Roche" and "Ayami Sato" not in g.home.batting(),
      "no DH: the new pitcher takes the pitcher's slot")
g = game(setup(11), change_once("LAQ", "Michelle Roche"))
check("Michelle Roche" not in g.home.batting() and g.home.used == ["Ayami Sato", "Michelle Roche"],
      "DH: the lineup is unchanged")
msg = refused(game, setup(11), lambda g, at, side: "Ayami Sato" if at == "Top 4, start"
              and side.team == "LAQ" and g.home.pitcher != "Ayami Sato" else
              ("Michelle Roche" if at == "Top 3, start" and side.team == "LAQ" else "keep"))
check(msg is not None and "re-enter" in msg, f"re-entry refused: {msg}")
fielder = next(o.rpartition(" ")[0] for o in lineup("LAQ", "Ayami Sato")["order"]
               if o.rpartition(" ")[0] in cards.pitcher)
msg = refused(game, setup(11), change_once("LAQ", fielder))
check(msg is not None and "lineup = [" in msg, f"a fielder to pitch without a lineup refused: {msg}")

# a fielder moves to pitch: she takes P in her own slot, the DH is lost, and a
# bench player who can play her old position takes the DH's slot
start = [play.Slot(*o.rsplit(" ", 1)) for o in lineup("LAQ", "Ayami Sato")["order"]]
f_slot = next(s for s in start if s.name == fielder)
dh_i = next(i for i, s in enumerate(start) if s.pos == "DH")
bench = next(n for n in cards.team_batters("LAQ") if n not in [s.name for s in start]
             and n != "Ayami Sato" and f_slot.pos in cards.positions(n))
new_nine = [f"{bench} {f_slot.pos}" if i == dh_i else
            f"{s.name} {'P' if s.name == fielder else s.pos}" for i, s in enumerate(start)]


def at_top3(choice):
    return lambda g, at, side: choice if at == "Top 3, start" and side.team == "LAQ" else "keep"


g = game(setup(11), at_top3((fielder, new_nine)))
check(g.home.pitcher == fielder and [f"{s.name} {s.pos}" for s in g.home.order] == new_nine
      and "LAQ lose the DH" in g.joined() and {"Ayami Sato", start[dh_i].name} <= g.home.gone,
      f"a fielder to pitch with a lineup: {fielder} to P, {bench} in for the DH at {f_slot.pos}")
swapped = list(new_nine)
swapped[0], swapped[1] = swapped[1], swapped[0]
msg = refused(game, setup(11), at_top3((fielder, swapped)))
check(msg is not None and "place in the order" in msg, f"batting order swap refused: {msg}")
keep_dh = [f"{s.name} {s.pos}" for s in start]
msg = refused(game, setup(11), at_top3((fielder, keep_dh)))
check(msg is not None and "her position is P" in msg, f"pitcher left at her field position refused: {msg}")
back = [f"{start[dh_i].name} DH" if i == dh_i else e for i, e in enumerate(new_nine)]


def twice(g, at, side):
    if side.team != "LAQ":
        return "keep"
    if at == "Top 3, start":
        return (fielder, new_nine)
    if at == "Top 4, start":
        return ("keep", [f"{start[dh_i].name} {f_slot.pos}" if i == dh_i else e
                         for i, e in enumerate(new_nine)])
    return "keep"


msg = refused(game, setup(11), twice)
check(msg is not None and "left the game" in msg, f"a replaced player coming back refused: {msg}")
g = play.Game(setup(11), [], cards, wp)
g.home.gone.add("Michelle Roche")
check("Michelle Roche" not in g.available(g.home), "a player who left is not offered to pitch")
msg = refused(game, setup(11), lambda g, at, side: (fielder, back)
              if at == "Top 3, start" and side.team == "LAQ" else "keep")
check(msg is not None, f"keeping the DH with the pitcher in the lineup refused: {msg}")
bos = setup(11, away="SFF", home="BOS", hp="Kate Blunt", dh=(True, False))
g = game(bos, change_once("BOS", "Gigi Schiano"))
check(cards.batter["Gigi Schiano"]["PA"] == "0" and "Gigi Schiano" in g.home.batting(),
      "a generic batter card (PA 0) lets a pitcher who never batted come in without a DH")
saved = cards.batter.pop("Gigi Schiano")            # as if she had no batter card at all
msg = refused(game, bos, change_once("BOS", "Gigi Schiano"))
cards.batter["Gigi Schiano"] = saved
check(msg is not None and "no batter card" in msg, f"a batless pitcher without a DH refused: {msg}")
g = game(setup(11, away="SFF", home="BOS", hp="Kate Blunt"), change_once("BOS", "Gigi Schiano"))
check("Gigi Schiano" in g.home.used, "a batless pitcher with a DH is allowed")

# --- three-batter minimum (OBR 5.10(g)) ------------------------------------------------------
msg = refused(game, setup(11), lambda g, at, side: "Michelle Roche"
              if at == "Top 1, start" and side.team == "LAQ" else "keep")
check(msg is not None and "three-batter" in msg, f"the starter cannot leave before a batter: {msg}")


def every_pa(s, manager):
    g = play.Game(s, [], cards, wp)
    g.manager, g.every_pa = manager, True
    g.run()
    return g


seen_stops, early_leave = [], {"ok": 0}


def two_out_reliever(g, at, side):
    """Bring Roche in with two out in the 3rd; change her at the next start if she
    faced fewer than three. Record every stop the fielding side is given."""
    seen_stops.append((at, side.team, side.faced, g.at_half_start, side.finished_half))
    if side.team != "LAQ":
        return "keep"
    if at.startswith("Top 3, 2 out") and side.pitcher == "Ayami Sato":
        return "Michelle Roche"
    if at == "Bottom 3, start" or at == "Top 4, start":
        if side.pitcher == "Michelle Roche" and side.faced < 3:
            early_leave["ok"] += 1
            return "Meggie Meidlinger"
    return "keep"


for seed in range(40):
    every_pa(setup(2000 + seed), two_out_reliever)
mid = [s for s in seen_stops if not s[3] and s[2] < 3]
check(not mid, f"no mid-half stop before the pitcher has faced three ({len(mid)} found)")
check(early_leave["ok"] > 0, f"after finishing a half under three batters she may leave between "
      f"halves ({early_leave['ok']} times in 40 games)")




def rule_case(faced, finished, at_start):
    """Can LAQ's pitcher leave, given batters faced, a finished half, and where we are?"""
    g = play.Game(setup(11), [], cards, wp)
    g.enter(g.home, g.home.pitcher)
    g.home.faced, g.home.finished_half, g.at_half_start = faced, finished, at_start
    return refused(g.change, g.home, "Michelle Roche") is None


cases = {(0, False, True): False,   # the starter before her first batter
         (2, False, False): False,  # mid-half, two faced
         (3, False, False): True,   # three faced
         (1, True, True): True,     # finished a half under three: may leave between halves
         (1, True, False): False}   # ...but if she starts the next, the minimum carries on
got = {c: rule_case(*c) for c in cases}
check(got == cases, f"three-batter cases (faced, finished a half, at a half's start): {got}")

# --- whole games -------------------------------------------------------------------------
N = 400
stats = {"extras": 0, "walkoffs": 0, "cs3": 0, "green": 0, "red": 0}
ok = {k: True for k in ("runs", "pitches", "tie", "skip", "placed", "cs3", "steal")}
for seed in range(N):
    g = game(setup(1000 + seed))
    for side in (g.away, g.home):
        ok["runs"] &= sum(side.line) == side.runs
    ok["tie"] &= g.away.runs != g.home.runs
    innings = len(g.away.line)
    stats["extras"] += innings > engine.INNINGS
    stats["walkoffs"] += g.over
    if len(g.home.line) < innings:              # bottom of the last inning not played
        ok["skip"] &= g.home.runs - sum(g.home.line) == 0 and \
            g.home.runs > g.away.runs
    cost = {}
    for e in g.events:
        if e["event"] == "pa" and e["line"] != "RUN":
            cost[e["pitcher"]] = cost.get(e["pitcher"], 0) + (5 if e["line"] in ("K", "BB") else 3)
    for p, st in g.stats.items():
        ok["pitches"] &= g.fatigue[p] == st["start"] + 30 + cost.get(p, 0)
    ev = g.events
    for i, e in enumerate(ev):
        if e["event"] == "steal":
            stats[e["light"]] += 1
            ok["steal"] &= (e["net_wp"] > 0) == (e["light"] == "green")
        if e["event"] == "steal" and e.get("result") == "out":
            nxt = ev[i + 1] if i + 1 < len(ev) else None
            if nxt and (nxt["inning"], nxt["half"]) != (e["inning"], e["half"]):
                stats["cs3"] += 1
                lead = next((x for x in ev[i + 1:]
                             if x["event"] == "pa" and x["batting"] == e["batting"]), None)
                if lead is not None:                   # None: it ended the game
                    ok["cs3"] &= lead["batter"] == e["up"]
    for m in re.finditer(r"## (Top|Bottom) (\d+) · (\w+) batting[^\n]*\n\n- Extra inning: (.+?) placed",
                         g.joined()):
        inning, team, placed = int(m.group(2)), m.group(3), m.group(4)
        last = [x for x in ev if x["event"] == "pa" and x["batting"] == team and x["inning"] < inning]
        ok["placed"] &= last[-1]["batter"] == placed
print(f"     {N} games: {stats}")
check(ok["runs"], "line score adds up to runs")
check(ok["pitches"], "pitch counts: start + 30 + 5 per K or BB + 3 per other PA")
check(ok["tie"], "no game ends tied")
check(ok["skip"], "home does not bat in the last bottom half when already ahead")
check(ok["placed"] and stats["extras"] > 0, "extra innings place the team's last batter on 2nd")
check(ok["cs3"] and stats["cs3"] > 0, "caught stealing for the third out: she leads off next")
check(ok["steal"], "green light exactly when net WP > 0")

# --- fatigue across days ---------------------------------------------------------------
g1 = tmp / "a.md"
write_setup(g1, setup(7))
play_to_end(g1)
after = play.blocks(g1.read_text(encoding="utf-8"))[-1][2]["fatigue"]
f2 = play.carried_fatigue(cards, [g1], dt.date(2026, 10, 5))
check(all(f2[n] == max(-30, after.get(n, -30) - 40) for n in cards.pitcher),
      f"two days later: 20 a day, floor -30 (Whitmore {after['Kelsie Whitmore']} -> "
      f"{f2['Kelsie Whitmore']})")
f0 = play.carried_fatigue(cards, [g1], dt.date(2026, 10, 3))
check(all(f0[n] == after.get(n, -30) for n in cards.pitcher), "a doubleheader recovers nothing")
g3 = tmp / "b.md"
write_setup(g3, setup(9, away="NYH", home="BOS", ap="Jaida Lee", hp="Kate Blunt"))
play_to_end(g3)
after3 = play.blocks(g3.read_text(encoding="utf-8"))[-1][2]["fatigue"]
both = play.carried_fatigue(cards, [g1, g3], dt.date(2026, 10, 4))
check(both["Kelsie Whitmore"] == max(-30, after["Kelsie Whitmore"] - 20)
      and both["Jaida Lee"] == max(-30, after3["Jaida Lee"] - 20),
      "two games on one date: each pitcher from her own team's game")
check(refused(play.carried_fatigue, cards, [g1], dt.date(2026, 10, 2)) is not None,
      "a log dated after the new game is refused")

print(f"\n{len(failures)} failure(s)" if failures else "\nall checks pass")
