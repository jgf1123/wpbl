"""Play Two Outs, So What? from a log file (tosw_play_spec.md).

    pixi run play new games/<name>.md --date 2026-10-03 --away SFF --home LAQ [--after LOG ...]
    pixi run play games/<name>.md
    pixi run play export games/<name>.md
    pixi run play suggest games/<name>.md [--team SFF] [--write]

`new` writes a log with a setup block: every league pitcher's pitch count and
an empty lineup for each team. Fill in the lineups, then `play` it.

`play` replays the game from the seed, the setup and every decision block so
far, plays on to the next stop, and rewrites the file. A stop is the start of
every half-inning, and every plate appearance while the fielding pitcher is
Gassed. The command leaves a decision block filled in with `keep`. Edit it
or leave it alone, and run `play` again.

The play-by-play is output, not input. If the replay does not reproduce it
exactly, `play` stops and writes nothing: something changed under the game
(an edited line, new cards, new code).

The rules are `engine.py`'s, which `analysis/dice/rules_check.py` holds to the
rulebook. This module adds what a single game needs on top: lineups, runner
names, steals by win probability, pitching changes, and the log.
"""
from __future__ import annotations

import csv
import datetime as dt
import re
import secrets
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from wpbl import engine
from wpbl.play_wp import B_SPAN, CARD_LINES, DICE_DIR, P_SPAN, WinProbability, faces

COLUMNS = ("fresh", "fading", "gassed")
POSITIONS = ("C", "1B", "2B", "3B", "SS", "LF", "CF", "RF")
BENITES = "Denae Benites"
BASE_NAMES = {2: "2nd", 3: "3rd"}

# The rulebook's steal table (Stealing), as printed. play_check compares this to
# the rulebook, so a change to either side is caught. Columns: no attempt, then
# success Low (any catcher), League vs Benites, League against anyone else.
STEAL_TABLE = {
    (2, "Goes"):   ("00-63", "64-81 out, 82-99 safe", "64-75 out, 76-99 safe", "64-66 out, 67-99 safe"),
    (2, "League"): ("00-93", "94-96 out, 97-99 safe", "94-95 out, 96-99 safe", "94 *, 95-99 safe"),
    (3, "Goes"):   ("00-87", "88-93 out, 94-99 safe", "88-91 out, 92-99 safe", "88 out, 89-99 safe"),
    (3, "League"): ("00-98", "99 *", "99 safe", "99 safe"),
}


class Refused(Exception):
    """A problem in the log the manager has to fix. Nothing is written."""


class Stopped(Exception):
    """The game reached a stop with no decision for it."""

    def __init__(self, block):
        self.block = block


# --- cards ---------------------------------------------------------------------

def card_version() -> str:
    first = (DICE_DIR / "cards_batters.csv").read_text(encoding="utf-8").splitlines()[0]
    return re.search(r"v\d+\.\d+\.\d+", first).group(0)


class Cards:
    def __init__(self):
        B = pd.read_csv(DICE_DIR / "cards_batters.csv", comment="#", dtype=str)
        P = pd.read_csv(DICE_DIR / "cards_pitchers.csv", comment="#", dtype=str)
        self.version = card_version()
        self.batter = {r["player"]: r for _, r in B.iterrows()}
        self.pitcher = {r["player"]: r for _, r in P.iterrows()}
        self.bat_faces = {n: faces(r, CARD_LINES, "", B_SPAN) for n, r in self.batter.items()}
        self.pitch_faces = {n: {c: faces(r, CARD_LINES, f"{c} ", P_SPAN) for c in COLUMNS}
                            for n, r in self.pitcher.items()}

    def positions(self, name):
        return self.batter[name]["position"].split("/")

    def stamina(self, name):
        return int(self.pitcher[name]["stamina"])

    def team_pitchers(self, team):
        return [n for n, r in self.pitcher.items() if r["team"] == team]

    def team_batters(self, team):
        return [n for n, r in self.batter.items() if r["team"] == team]


# --- steals --------------------------------------------------------------------

def _steal_faces(text):
    """'64-81 out, 82-99 safe' -> {face: 'out' | 'safe' | '*'}."""
    out = {}
    for part in text.split(", "):
        rng, result = part.split(" ")
        lo, _, hi = rng.partition("-")
        for f in range(int(lo), int(hi or lo) + 1):
            out[f] = result
    return out


def steal_column(success, catcher):
    if success == "Low":
        return 1
    return 2 if catcher == BENITES else 3


def steal_faces(base, attempt, column):
    return _steal_faces(STEAL_TABLE[(base, attempt)][column])


def steal_p(base, attempt, column):
    """Safe share of the attempt faces, a * counting half. The decision's p."""
    f = steal_faces(base, attempt, column)
    safe = sum(1.0 if r == "safe" else 0.5 if r == "*" else 0.0 for r in f.values())
    return safe / len(f)


def steal_candidate(bases):
    """(runner's base, target) or None. Only a runner whose next base is empty."""
    if bases[0] and not bases[1]:
        return 1, 2
    if bases[1] and not bases[2]:
        return 2, 3
    return None


# --- the log -------------------------------------------------------------------

BLOCK = re.compile(r"^```tosw-([a-z-]+)[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)


def normalise(text):
    """Trailing spaces and runs of blank lines do not count as a difference."""
    joined = "\n".join(line.rstrip() for line in text.strip().splitlines())
    return re.sub(r"\n{3,}", "\n\n", joined)


ENTRY = re.compile(r'^\s*"?(.+?)\s*\(?([A-Z0-9]{1,2})\)?"?\s*,?\s*$')


def lenient_orders(body):
    """Let a lineup be pasted straight from the roster listing.

    Inside `order = [ ... ]` or `lineup = [ ... ]`, a line may be quoted or not,
    with or without a trailing comma, and with the position bare or in parentheses:
    `Denver Bryant (3B)`, `"Denver Bryant 3B",` and `Denver Bryant 3B` all read
    as "Denver Bryant 3B". Only the TOML that is parsed changes; the file's own
    text is left as written."""
    out, inside = [], False
    for line in body.split("\n"):
        s = line.strip()
        if not inside and re.match(r"(order|lineup)\s*=\s*\[\s*$", s):
            inside = True
        elif inside and s.startswith("]"):
            inside = False
        elif inside and s and not s.startswith("#"):
            m = ENTRY.match(s.split(" #")[0])
            if m:
                line = f'  "{m.group(1)} {m.group(2)}",'
        out.append(line)
    return "\n".join(out)


def blocks(text):
    """[(kind, raw text including fences, parsed TOML, start offset)]."""
    out = []
    for m in BLOCK.finditer(text):
        body = lenient_orders(m.group(2)) if m.group(1) in ("setup", "decision") else m.group(2)
        try:
            data = tomllib.loads(body)
        except tomllib.TOMLDecodeError as e:
            line_no = text.count("\n", 0, m.start(2)) + getattr(e, "lineno", 1)
            bad = text.splitlines()[line_no - 1] if line_no <= len(text.splitlines()) else ""
            raise Refused(f"tosw-{m.group(1)} block, file line {line_no}: {e.msg}\n"
                          f"  {bad.strip()}\n"
                          '  A lineup entry looks like "Amanda Gianelloni 2B", and '
                          'other values need quotes, e.g. pitcher = "Kate Blunt".')
        out.append((m.group(1), m.group(0), data, m.start()))
    return out


def toml_str(s):
    return '"' + str(s).replace("\\", "\\\\").replace('"', '\\"') + '"'


def fatigue_lines(fatigue):
    return [f"{toml_str(n)} = {c}" for n, c in fatigue.items()]


# --- the game ------------------------------------------------------------------

@dataclass
class Slot:
    name: str
    pos: str


@dataclass
class Side:
    team: str
    order: list
    pitcher: str
    spot: int = 0
    runs: int = 0
    used: list = field(default_factory=list)
    line: list = field(default_factory=list)
    gone: set = field(default_factory=set)     # left the game; cannot come back
    faced: int = 0                             # batters the current pitcher has faced
    finished_half: bool = False                # she has pitched to the end of a half

    def batting(self):
        return [s.name for s in self.order]

    def catcher(self):
        return next(s.name for s in self.order if s.pos == "C")


class Dice:
    """One seeded stream, drawn in a fixed order, so a replay rolls the same dice."""

    def __init__(self, seed):
        self.g = np.random.default_rng(seed)
        self.last = None

    def integers(self, lo, hi):
        self.last = int(self.g.integers(lo, hi))
        return self.last

    def d100(self):
        return self.integers(0, 100)


def bases_text(bases):
    return "".join(c if b else "_" for c, b in zip("123", bases))


def pct(x):
    return f"{100 * x:.1f}%"


def parse_slots(cards, team, order):
    """["Name POS", ...] -> [Slot], each player with a batter card for `team`."""
    if len(order) != 9:
        raise Refused(f"{team}: the lineup needs 9 batters, not {len(order)}")
    slots = []
    for entry in order:
        name, _, pos = entry.rpartition(" ")
        if name not in cards.batter or cards.batter[name]["team"] != team:
            raise Refused(f"{team}: {name!r} has no {team} batter card")
        slots.append(Slot(name, pos))
    return slots


def check_slots(cards, team, slots, pitcher, who="starting pitcher"):
    """Positions: C through RF once each, plus P (the pitcher, batting) or DH."""
    for s in slots:
        if s.pos == "P":
            if s.name != pitcher:
                raise Refused(f"{team}: only the {who} plays P, not {s.name}")
        elif s.name == pitcher:
            raise Refused(f"{team}: {s.name} is the {who}, so her position is P")
        elif s.pos != "DH" and s.pos not in cards.positions(s.name):
            raise Refused(f"{team}: {s.name} cannot play {s.pos} "
                          f"(card: {cards.batter[s.name]['position']})")
    if len({s.name for s in slots}) != 9:
        raise Refused(f"{team}: a player is in the lineup twice")
    pos = sorted(s.pos for s in slots)
    if sorted(p for p in pos if p in POSITIONS) != sorted(POSITIONS) or \
            sorted(p for p in pos if p not in POSITIONS) not in (["DH"], ["P"]):
        raise Refused(f"{team}: positions must be {', '.join(POSITIONS)} once each, plus P or DH")


def check_lineup(cards, team, data):
    pitcher = data.get("pitcher", "")
    slots = parse_slots(cards, team, data.get("order", []))
    if pitcher not in cards.pitcher or cards.pitcher[pitcher]["team"] != team:
        raise Refused(f"{team}: starting pitcher {pitcher!r} has no {team} pitcher card")
    check_slots(cards, team, slots, pitcher)
    return Side(team, slots, pitcher)


class Game:
    def __init__(self, setup, decisions, cards, wp):
        self.cards, self.wp = cards, wp
        if setup.get("cards") != cards.version:
            raise Refused(f"setup says cards {setup.get('cards')}, the cards are {cards.version}")
        self.date = setup["date"]
        lineups = setup.get("lineup", {})
        self.away = check_lineup(cards, setup["away"], lineups.get(setup["away"], {}))
        self.home = check_lineup(cards, setup["home"], lineups.get(setup["home"], {}))
        self.fatigue = {n: int(c) for n, c in setup.get("fatigue", {}).items()}
        for n in cards.pitcher:
            self.fatigue.setdefault(n, engine.RESTED)
        self.dice = Dice(setup["seed"])
        self.decisions = decisions
        self.manager = None
        self.used_decisions = 0
        self.text = []
        self.mark = 0                     # chars of text the log already holds
        self.events = []
        self.stats = {}                   # pitcher -> dict
        self.over = False
        self.inning, self.top = 1, True
        self.outs, self.bases = 0, [None, None, None]
        self.at_half_start = False
        self.every_pa = False             # in-process managers: a stop before every PA

    # -- output --
    def emit(self, line=""):
        self.text.append(line)

    def joined(self):
        return "\n".join(self.text)

    def score(self):
        return f"{self.away.team} {self.away.runs}, {self.home.team} {self.home.runs}"

    def bat_fld(self):
        return (self.away, self.home) if self.top else (self.home, self.away)

    def half_name(self):
        return f"{'Top' if self.top else 'Bottom'} {self.inning}"

    def wp_home(self, outs=None, bases=None, diff=None):
        outs = self.outs if outs is None else outs
        bases = self.bases if bases is None else bases
        diff = self.home.runs - self.away.runs if diff is None else diff
        return self.wp.mid(self.inning, "top" if self.top else "bottom", outs,
                           [b is not None for b in bases], diff)

    def column(self, name):
        return engine.column_for(self.fatigue[name], self.cards.stamina(name))

    # -- pitchers --
    def enter(self, side, name):
        before = self.fatigue[name]
        self.fatigue[name] = engine.enter(before)
        side.used.append(name)
        side.pitcher = name
        side.faced, side.finished_half = 0, False
        self.stats[name] = {"team": side.team, "start": before, "BF": 0}
        return before

    def can_change(self, side):
        """The three-batter minimum (OBR 5.10(g)): a pitcher faces three batters,
        or pitches until the side is out. Between half-innings she may leave once
        she has finished one; if she starts the next, the minimum carries on."""
        return side.faced >= 3 or (self.at_half_start and side.finished_half)

    def available(self, side):
        out = []
        p_slot = any(s.pos == "P" for s in side.order)
        for n in self.cards.team_pitchers(side.team):
            if n in side.used or n in side.batting() or n in side.gone:
                continue
            if p_slot and n not in self.cards.batter:
                continue                       # would have to bat, and has no batter card
            out.append(n)
        return out

    def change(self, side, new, lineup=None):
        """A pitching change, a lineup change, or both, for the fielding side.

        Without `lineup` the old rule applies: a reliever from outside the
        lineup, taking the pitcher's batting slot if there is no DH. With it,
        `lineup` is the whole new nine in batting order. Each slot keeps its
        player or takes one from the bench; nobody changes slot, and nobody who
        has left comes back. A pitcher already in the lineup moves to P. The DH
        stays only if the pitcher is outside the lineup, and once gone it does
        not return."""
        team, old = side.team, side.pitcher
        new = old if new == "keep" else new
        if new != old:
            if new not in self.cards.pitcher or self.cards.pitcher[new]["team"] != team:
                raise Refused(f"{new!r} has no {team} pitcher card")
            if new in side.used:
                raise Refused(f"{new} has already pitched in this game and cannot re-enter")
            if new in side.gone:
                raise Refused(f"{new} has left the game and cannot re-enter")
            if not self.can_change(side):
                raise Refused(f"three-batter minimum: {old} has faced {side.faced} batter(s) "
                              f"and must face 3, or pitch until the side is out")
        if lineup is None:
            if new == old:
                return
            if new in side.batting():
                raise Refused(f"{new} is in the lineup, so moving her to pitch changes the "
                              f"positions. Give the new nine with lineup = [...] under "
                              f"[{team}]; the stop's notes list the current one to copy.")
            slots = [Slot(s.name, s.pos) for s in side.order]
            p_slot = next((s for s in slots if s.pos == "P"), None)
            if p_slot is not None:
                if new not in self.cards.batter:
                    raise Refused(f"{new} has no batter card, and without a DH she would bat "
                                  f"in {old}'s place")
                p_slot.name = new
        else:
            slots = parse_slots(self.cards, team, lineup)
            for i, (was, now) in enumerate(zip(side.order, slots), 1):
                if now.name == was.name:
                    continue
                if now.name in side.batting():
                    raise Refused(f"{team}: {now.name} bats {side.batting().index(now.name) + 1}"
                                  f"; a player cannot change her place in the order")
                if now.name in side.gone:
                    raise Refused(f"{team}: {now.name} has left the game and cannot re-enter")
            check_slots(self.cards, team, slots, new, who="pitcher")
            had_dh = any(s.pos == "DH" for s in side.order)
            if any(s.pos == "DH" for s in slots) and not had_dh:
                raise Refused(f"{team}: the DH is gone and cannot come back")
        # apply
        out_of_order = [w.name for w, n in zip(side.order, slots) if w.name != n.name]
        if new != old:
            before = self.enter(side, new)
            p_was = next((s.name for s in side.order if s.pos == "P"), None)
            p_now = next((s.name for s in slots if s.pos == "P"), None)
            if old in [s.name for s in slots]:
                stays = " and stays in the game"
            elif p_was == old and p_now == new and new not in side.batting():
                stays = " and takes her place in the batting order"    # v1 wording, kept
            else:
                stays = ""
            self.emit(f"- Pitching change ({team}): {new} replaces {old}{stays} · "
                      f"{new} {before} + 30 = {self.fatigue[new]} ({self.column(new)})")
            if old not in [s.name for s in slots]:
                side.gone.add(old)
        for i, (was, now) in enumerate(zip(side.order, slots), 1):
            if (was.pos, now.pos, was.name, now.name) == ("P", "P", old, new):
                continue                       # said above: she takes the pitcher's slot
            if now.name != was.name:
                self.emit(f"- Lineup change ({team}): {now.name} bats {i} and plays {now.pos}, "
                          f"replacing {was.name} ({was.pos})")
            elif now.pos != was.pos:
                self.emit(f"- Position change ({team}): {now.name} moves {was.pos} → {now.pos}")
        if any(s.pos == "DH" for s in side.order) and not any(s.pos == "DH" for s in slots):
            self.emit(f"- {team} lose the DH")
        side.gone.update(out_of_order)
        side.order = slots
        self.events.append(self.event("change", pitcher=new, replaced=old,
                                      lineup=" | ".join(f"{s.name} {s.pos}" for s in slots)))

    def stop(self, at, notes):
        """Take the next decision from the log, or end the run here."""
        _, fld = self.bat_fld()
        if self.used_decisions < len(self.decisions):
            raw, data = self.decisions[self.used_decisions]
            self.used_decisions += 1
            if data.get("at") != at:
                raise Refused(f"the log does not match its replay: decision block "
                              f"{self.used_decisions} is for {data.get('at')!r}, but the replay "
                              f"is at {at!r}. Was the setup or an earlier decision edited? "
                              "Nothing was written.")
            choice = data.get(fld.team, {}).get("pitcher")
            if choice is None:
                raise Refused(f"decision block at {at!r} needs [{fld.team}] pitcher = ...")
            lineup = data.get(fld.team, {}).get("lineup")
            self.emit()
            self.emit(raw)
            self.emit()
            self.mark = len(self.joined())
            self.change(fld, choice, lineup)
            return
        if self.manager is not None:           # tests: decide in-process, no log
            choice = self.manager(self, at, fld)
            pitcher, lineup = choice if isinstance(choice, tuple) else (choice, None)
            self.change(fld, pitcher, lineup)
            return
        lines =["```tosw-decision", f"at = {toml_str(at)}"]
        lines += [f"# {n}" for n in notes]
        lines += [f"[{fld.team}]", 'pitcher = "keep"', "```"]
        raise Stopped("\n".join(lines))

    def stop_notes(self, why):
        bat, fld = self.bat_fld()
        p = fld.pitcher
        notes = [f"{why}. {bat.team} batting, {fld.team} fielding. {self.score()}. "
                 f"{self.outs} out, bases {bases_text(self.bases)}. WP home {pct(self.wp_home())}.",
                 f"On the mound: {p}, {self.fatigue[p]} pitches, {self.column(p)} "
                 f"(fresh to 20, gassed past {self.cards.stamina(p)}).",
                 f"Up next: {bat.order[bat.spot % 9].name}."]
        if not self.can_change(fld):
            notes.append(f"Three-batter minimum: {p} has faced {fld.faced} and stays in; "
                         "positions may still change.")
        notes.append(f"{fld.team} pitchers who can come in (count now -> on entering, column):")
        for n in self.available(fld):
            c = engine.enter(self.fatigue[n])
            col = engine.column_for(c, self.cards.stamina(n))
            notes.append(f"  {n}: {self.fatigue[n]} -> {c}, {col} (stamina {self.cards.stamina(n)})")
        in_game = [s.name for s in fld.order
                   if s.name in self.cards.pitcher and s.name not in fld.used]
        if in_game:
            notes.append(f"In the lineup and able to pitch (needs a lineup, below): "
                         + ", ".join(f"{n} ({self.fatigue[n]} -> {engine.enter(self.fatigue[n])})"
                                     for n in in_game))
        bench = [n for n in self.cards.team_batters(fld.team)
                 if n not in fld.batting() and n not in fld.gone and n != fld.pitcher
                 and n not in fld.used]
        notes.append("Bench: " + ", ".join(f"{n} ({self.cards.batter[n]['position']})"
                                           for n in bench))
        notes.append('To change pitchers, replace "keep" with her name. To change positions or')
        notes.append("bring in a bench player, also give the new nine, keeping each batting slot:")
        notes.append("lineup = [")
        notes += [f'  "{s.name} {s.pos}",' for s in fld.order]
        notes.append("]")
        return notes

    # -- events --
    def event(self, kind, **kw):
        bat, fld = self.bat_fld()
        row = {"inning": self.inning, "half": "top" if self.top else "bottom",
               "batting": bat.team, "fielding": fld.team, "event": kind}
        row.update(kw)
        row.update({"away_runs": self.away.runs, "home_runs": self.home.runs})
        return row

    def score_runs(self, side, n):
        side.runs += n
        if (not self.top and self.inning >= engine.INNINGS
                and self.home.runs > self.away.runs):
            self.over = True                   # walk-off

    def maybe_steal(self):
        cand = steal_candidate(self.bases)
        if cand is None:
            return
        bat, fld = self.bat_fld()
        on, target = cand
        runner = self.bases[on - 1]
        card = self.cards.batter[runner]
        col = steal_column(card["success"], fld.catcher())
        p = steal_p(target, card["attempt"], col)
        sign = 1 if not self.top else -1
        diff = self.home.runs - self.away.runs
        stay = self.wp_home()
        safe_b = list(self.bases)
        safe_b[on - 1], safe_b[target - 1] = None, runner
        safe = self.wp_home(bases=safe_b)
        out_b = list(self.bases)
        out_b[on - 1] = None
        caught = self.wp_home(outs=self.outs + 1, bases=out_b, diff=diff)
        net = sign * (p * safe + (1 - p) * caught - stay)
        green = net > 0
        head = (f"- {self.outs} out {bases_text(self.bases)} · {runner} steal "
                f"{BASE_NAMES[target]} (p {p:.3f}): {'green' if green else 'red'} "
                f"{100 * net:+.1f} WP")
        if not green:
            self.emit(head)
            self.events.append(self.event("steal", runner=runner, light="red", net_wp=net))
            return
        roll = self.dice.d100()
        result = steal_faces(target, card["attempt"], col).get(roll, "no attempt")
        desc = f"d100 {roll:02d} {result}"
        if result == "*":
            coin = self.dice.integers(0, 2)
            result = "safe" if coin else "out"
            desc += f" · coin {result}"
        if result == "safe":
            self.bases = safe_b
        elif result == "out":
            self.bases = out_b
            self.outs += 1
        tail = f"{self.outs} out {bases_text(self.bases)}" if self.outs < 3 else "3 out"
        self.emit(f"{head} · {desc} → {tail} · WP home {pct(self.wp_home())}")
        self.events.append(self.event("steal", runner=runner, light="green", net_wp=net,
                                      up=bat.order[bat.spot % 9].name,
                                      rolls=desc, result=result))

    def plate_appearance(self):
        bat, fld = self.bat_fld()
        batter, pitcher = bat.order[bat.spot % 9].name, fld.pitcher
        col = self.column(pitcher)
        table = engine.Table.from_lines(self.cards.pitch_faces[pitcher][col],
                                        self.cards.bat_faces[batter])
        before = f"{self.outs} out {bases_text(self.bases)}"
        rolls, scorers = [], []
        while True:
            roll = self.dice.d100()
            line = table.read(roll)
            if line != "RUN":
                break
            if any(self.bases):
                if self.bases[2]:
                    scorers.append(self.bases[2])
                    self.score_runs(bat, 1)
                self.bases = [None, self.bases[0], self.bases[1]]
                rolls.append(f"d100 {roll:02d} running play → {bases_text(self.bases)}")
                if self.over:
                    break
            else:
                rolls.append(f"d100 {roll:02d} running play, bases empty")
        if self.over:                          # walk-off on a running play
            self.emit(f"- {before} · {batter} vs {pitcher} ({col}) · {' · '.join(rolls)} · "
                      f"scores: {', '.join(scorers)} · {self.score()} · WALK-OFF")
            self.events.append(self.event("pa", batter=batter, pitcher=pitcher, column=col,
                                          rolls=" · ".join(rolls), line="RUN"))
            return
        src = "pitcher " if roll < engine.RUN_START else "batter " if roll >= engine.BAT_START else ""
        rolls.append(f"d100 {roll:02d} {src}{line}")
        occupied = [b is not None for b in self.bases]
        new, made, runs = engine.apply_line(line, tuple(occupied), self.outs, self.dice)
        # who is out: the batter, the runner from 1st, or both
        out_batter, out_first = line == "K", False
        if line == "OUT":
            table12 = engine.D12_FORCE if occupied[0] else engine.D12_NO_FORCE
            flavour = table12[self.dice.last]
            out_batter = not flavour.startswith("F") or flavour.startswith("FB")
            out_first = flavour.startswith("F")
            if self.outs < 2:
                rolls.append(f"d12 {self.dice.last + 1} {flavour}")
        elif line == "1B":
            rolls.append(f"d12 {self.dice.last}")
        people = [self.bases[i] for i in (2, 1, 0) if self.bases[i] is not None
                  and not (i == 0 and out_first)]
        if not out_batter:
            people.append(batter)
        self.outs += made
        self.fatigue[pitcher] += 5 if line in ("K", "BB") else 3
        self.stats[pitcher]["BF"] += 1
        fld.faced += 1
        if self.outs >= 3:
            self.bases = [None, None, None]
            runs = 0
        else:
            scorers += people[:runs]
            rest = people[runs:]
            self.bases = [None, None, None]
            for i in (2, 1, 0):
                if new[i]:
                    self.bases[i] = rest.pop(0)
            assert not rest, "runner bookkeeping lost a runner"
            self.score_runs(bat, runs)
        bat.spot += 1
        after = f"{self.outs} out {bases_text(self.bases)}" if self.outs < 3 else "3 out"
        tail = f" · scores: {', '.join(scorers)}" if scorers else ""
        wp = "WALK-OFF" if self.over else f"WP home {pct(self.wp_home())}"
        self.emit(f"- {before} · {batter} vs {pitcher} ({col}) · {' · '.join(rolls)} → "
                  f"{after}{tail} · {self.score()} · {pitcher} {self.fatigue[pitcher]} · {wp}")
        self.events.append(self.event("pa", batter=batter, pitcher=pitcher, column=col,
                                      rolls=" · ".join(rolls), line=line,
                                      outs_before=before, outs_after=after,
                                      scored=len(scorers), pitch_count=self.fatigue[pitcher],
                                      wp_home=None if self.over else self.wp_home()))

    def half(self):
        bat, fld = self.bat_fld()
        self.outs, self.bases = 0, [None, None, None]
        placed = None
        if self.inning > engine.INNINGS:
            placed = bat.order[(bat.spot - 1) % 9].name
            self.bases[1] = placed
        name = self.half_name()
        self.at_half_start = True
        self.stop(f"{name}, start", self.stop_notes(f"{name} is about to start"))
        self.at_half_start = False
        self.emit(f"## {name} · {bat.team} batting · {fld.pitcher} ({fld.team}) pitching")
        self.emit()
        if placed:
            self.emit(f"- Extra inning: {placed} placed on 2nd")
        start = bat.runs
        seen = fld.pitcher                     # the start-of-half stop covered her
        while self.outs < 3 and not self.over:
            # Stop while she is gassed, once per plate appearance per pitcher: a
            # "keep" plays on, a change to another gassed arm stops again.
            # The three-batter minimum can rule a change out; then there is no stop.
            while (self.column(fld.pitcher) == "gassed" and fld.pitcher != seen
                   and self.can_change(fld)):
                seen = fld.pitcher
                up = bat.order[bat.spot % 9].name
                self.stop(f"{name}, {self.outs} out {bases_text(self.bases)}, {up} up",
                          self.stop_notes(f"{fld.pitcher} is gassed"))
            if self.every_pa and seen is None and self.can_change(fld):
                seen = fld.pitcher
                up = bat.order[bat.spot % 9].name
                self.stop(f"{name}, {self.outs} out {bases_text(self.bases)}, {up} up", [])
            self.maybe_steal()
            if self.outs >= 3:
                break
            self.plate_appearance()
            seen = None
        fld.finished_half = True
        bat.line.append(bat.runs - start)
        if not self.over:
            self.emit(f"\n*End of {name.lower()}: {self.score()}.*")
        self.emit()

    def run(self):
        for side in (self.away, self.home):
            before = self.enter(side, side.pitcher)
            self.emit(f"- {side.team} starts {side.pitcher}: {before} + 30 = "
                      f"{self.fatigue[side.pitcher]} ({self.column(side.pitcher)})")
        self.emit()
        while True:
            self.top = True
            self.half()
            if self.inning >= engine.INNINGS and self.home.runs > self.away.runs:
                break
            self.top = False
            self.half()
            if self.over or (self.inning >= engine.INNINGS and self.home.runs != self.away.runs):
                break
            self.inning += 1
        self.finish()

    def finish(self):
        self.emit("## Final")
        self.emit()
        n = max(len(self.away.line), len(self.home.line))
        self.emit("| | " + " | ".join(str(i + 1) for i in range(n)) + " | R |")
        self.emit("|---" * (n + 2) + "|")
        for s in (self.away, self.home):
            cells = [str(x) for x in s.line] + ["x"] * (n - len(s.line))
            self.emit(f"| {s.team} | " + " | ".join(cells) + f" | {s.runs} |")
        self.emit()
        self.emit("| pitcher | team | BF | pitch count before → after |")
        self.emit("|---|---|---|---|")
        for p, st in self.stats.items():
            self.emit(f"| {p} | {st['team']} | {st['BF']} | {st['start']} → {self.fatigue[p]} |")
        self.emit()
        self.emit("```tosw-fatigue-after")
        self.emit(f"date = {self.date.isoformat()}")
        self.emit("[fatigue]")
        for line in fatigue_lines(self.fatigue):
            self.emit(line)
        self.emit("```")


# --- commands ------------------------------------------------------------------

def read_log(path):
    text = Path(path).read_text(encoding="utf-8")
    bl = blocks(text)
    setups = [b for b in bl if b[0] == "setup"]
    if len(setups) != 1:
        raise Refused("the log needs exactly one tosw-setup block")
    _, raw, setup, start = setups[0]
    preamble = text[:start]
    decisions = [(b[1], b[2]) for b in bl if b[0] == "decision"]
    return text, preamble, raw, setup, decisions


_SHARED = {}


def shared():
    """Cards and the WP table, built once per process."""
    if not _SHARED:
        _SHARED["cards"], _SHARED["wp"] = Cards(), WinProbability()
    return _SHARED["cards"], _SHARED["wp"]


def replay(path):
    text, preamble, raw, setup, decisions = read_log(path)
    game = Game(setup, decisions, *shared())
    game.emit((preamble.rstrip("\n") + "\n\n" if preamble.strip() else "") + raw + "\n")
    game.mark = len(game.joined())
    try:
        game.run()
        stopped = None
    except Stopped as s:
        stopped = s.block
    if game.used_decisions < len(decisions):
        raise Refused(f"the game ended with {len(decisions) - game.used_decisions} "
                      "decision block(s) unused")
    return text, game, stopped


def first_difference(a, b):
    la, lb = a.splitlines(), b.splitlines()
    for i, (x, y) in enumerate(zip(la, lb)):
        if x != y:
            return i + 1, y, x
    i = min(len(la), len(lb))
    return i + 1, (lb[i] if i < len(lb) else "<end>"), (la[i] if i < len(la) else "<end>")


def play(path):
    text, game, stopped = replay(path)
    done = normalise(game.joined())
    held = normalise(game.joined()[:game.mark])
    if normalise(text) == done and stopped is None:
        print("The game is over. Nothing to do.")
        return
    if normalise(text) != held:
        n, found, expected = first_difference(held, normalise(text))
        raise Refused(f"the log does not match its replay at line {n}.\n"
                      f"  in the file: {found}\n  replay:      {expected}\n"
                      "Was the play-by-play, the setup, or a past decision edited? "
                      "Nothing was written.")
    out = normalise(game.joined()) + "\n"
    if stopped is not None:
        out += "\n" + stopped + "\n"
    Path(path).write_text(out, encoding="utf-8", newline="\n")
    tail = "stopped for a decision" if stopped else "game over"
    print(f"{path}: {tail}. {game.score()}.")


def export(path):
    _, game, _ = replay(path)
    dest = Path(path).with_suffix(".csv")
    keys = list(dict.fromkeys(k for e in game.events for k in e))
    with dest.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, keys)
        w.writeheader()
        w.writerows(game.events)
    print(f"wrote {dest} ({len(game.events)} events)")


def suggest_lineups(path, team=None, write=False):
    """Print the best batting order for each filled-in lineup (play_lineup.py)."""
    from wpbl import play_lineup
    text, _, _, setup, decisions = read_log(path)
    started = bool(decisions) or "```tosw-fatigue-after" in text or "\n## " in text
    if write and started:
        raise Refused("the game has started; --write only changes a lineup before the first play")
    cards = Cards()
    teams = [team] if team else [setup["away"], setup["home"]]
    for t in teams:
        data = setup.get("lineup", {}).get(t, {})
        side = check_lineup(cards, t, data)          # the nine must be a legal lineup
        names = side.batting()
        pos = {s.name: s.pos for s in side.order}
        best, runs, now, hits, starts, ranked = play_lineup.suggest(cards, names)
        print(f"\n{t}: expected runs in 7 innings against the league-average pitcher")
        print(f"  file's order {now:.3f}   suggested {runs:.3f}   gain {runs - now:+.3f} "
              f"(best order reached from {hits} of {starts} starts)")
        for i, n in enumerate(best, 1):
            print(f"  {i}. {n} {pos[n]}")
        if len(ranked) > 1:
            print("  next best orders the search scored:")
            for o, r in ranked[1:4]:
                print(f"    {r:.3f}  " + ", ".join(n.split()[-1] for n in o))
        entries = [f"{n} {pos[n]}" for n in best]
        if write:
            text = play_lineup.write_order(path, text, t, entries)
            print(f"  written to {path}")
        else:
            print("  paste into the setup block:\n  order = [\n"
                  + "".join(f'    "{e}",\n' for e in entries) + "  ]")
    print("\nBats only: steals and fielding are left out. Orders near the top are often "
          "within a hundredth of a run of each other; treat them as ties.")


def carried_fatigue(cards, logs, date):
    """Each pitcher's count from the latest log her team played in, recovered to `date`."""
    fatigue = {n: engine.RESTED for n in cards.pitcher}
    if not logs:
        return fatigue
    parsed = []
    for p in logs:
        bl = blocks(Path(p).read_text(encoding="utf-8"))
        setup = next((d for k, _, d, _ in bl if k == "setup"), None)
        after = next((d for k, _, d, _ in bl if k == "fatigue-after"), None)
        if setup is None or after is None:
            raise Refused(f"{p} is not a finished game (no tosw-fatigue-after block)")
        parsed.append((after["date"], {setup["away"], setup["home"]}, after["fatigue"], p))
    for name in cards.pitcher:
        team = cards.pitcher[name]["team"]
        mine = [x for x in parsed if team in x[1]] or parsed
        latest = max(x[0] for x in mine)
        on_day = [x for x in mine if x[0] == latest]
        if len(on_day) > 1 and team in on_day[0][1]:
            raise Refused(f"{team} played in more than one of the logs dated {latest}; "
                          "pass only the later game")
        d, _, fat, _ = on_day[0]
        days = (date - d).days
        if days < 0:
            raise Refused(f"{on_day[0][3]} is dated after {date}")
        fatigue[name] = engine.recover(int(fat.get(name, engine.RESTED)), days)
    return fatigue


def new(path, date, away, home, after, seed):
    path = Path(path)
    if path.exists():
        raise Refused(f"{path} already exists")
    cards = Cards()
    teams = {r["team"] for r in cards.pitcher.values()}
    for t in (away, home):
        if t not in teams:
            raise Refused(f"unknown team {t}; teams are {', '.join(sorted(teams))}")
    fatigue = carried_fatigue(cards, after, date)
    lines = [f"# {away} @ {home}, {date.isoformat()}", "",
             "Fill in both lineups below, then run `pixi run play` on this file.", "",
             "```tosw-setup",
             f"seed = {seed}",
             f"date = {date.isoformat()}",
             f"cards = {toml_str(cards.version)}",
             f"away = {toml_str(away)}",
             f"home = {toml_str(home)}"]
    for t in (away, home):
        lines += ["", f"[lineup.{t}]", 'pitcher = ""',
                  "order = [",
                  "  # nine lines in batting order, one per batter: a line copied from the",
                  "  # list below with its position edited down to one, e.g. Amanda Gianelloni (2B).",
                  "  # The position is one on her card, DH, or P for the starting pitcher if she bats.",
                  "]",
                  f"# {t} batters:"]
        lines += [f"#   {n} ({cards.batter[n]['position']})" for n in cards.team_batters(t)]
        lines += [f"# {t} pitchers (pitch count before this game, stamina):"]
        lines += [f"#   {n} {fatigue[n]}, {cards.stamina(n)}"
                  + ("" if n in cards.batter else " -- no batter card")
                  for n in cards.team_pitchers(t)]
    lines += ["", "[fatigue]   # pitch count before this game, whole league"]
    lines += fatigue_lines(fatigue)
    lines += ["```", ""]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"wrote {path}")


def main(argv=None):
    import argparse
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv and argv[0] == "new":
            ap = argparse.ArgumentParser(prog="play new")
            ap.add_argument("path")
            ap.add_argument("--date", required=True, type=dt.date.fromisoformat)
            ap.add_argument("--away", required=True)
            ap.add_argument("--home", required=True)
            ap.add_argument("--after", nargs="*", default=[])
            ap.add_argument("--seed", type=int, default=None)
            a = ap.parse_args(argv[1:])
            new(a.path, a.date, a.away, a.home, a.after,
                a.seed if a.seed is not None else secrets.randbelow(10 ** 6))
        elif argv and argv[0] == "export":
            export(argv[1])
        elif argv and argv[0] == "suggest":
            ap = argparse.ArgumentParser(prog="play suggest")
            ap.add_argument("path")
            ap.add_argument("--team", default=None)
            ap.add_argument("--write", action="store_true")
            a = ap.parse_args(argv[1:])
            suggest_lineups(a.path, a.team, a.write)
        elif len(argv) == 1:
            play(argv[0])
        else:
            print(__doc__)
            return 2
    except Refused as e:
        print(f"Refused: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
