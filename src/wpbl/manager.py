"""A computer manager for Two Outs, So What? (manager_spec.md).

    pixi run manager [--series N] [--b1] [--lambdas 0 0.001 ...] [--skip-b0]

Two policies manage the fielding side's pitching, both inside the rules of
`play.Game` (the three-batter minimum included):

  B0      keep the pitcher until she is gassed, then bring in the arm that
          allows the fewest runs per inning to a league lineup.
  B1      the user's median rule (manager_spec.md, v2 item 4). When the pitcher
          is gassed: one of the team's two best arms (A) if the stakes beat the
          cost, else a lesser arm (B). She is always relieved. Stakes:
          series leverage x (1 - the leading team's WP). Cost: k x the expected
          number of later games, k set so that game 1 is the median rule.
  shadow  before every plate appearance, for "keep" and each legal change, the
          fielding side's win probability over the rest of this half-inning,
          less a shadow price on the slack each arm loses for the rest of the
          series:

              value  = WP - lambda * sum over pitchers of excess
              excess = sum over every later game the series could reach of
                       max(0, her count recovered to that day + 30)

          A pitch that recovers before a game costs nothing at that game. Summing
          over all later games, not just the next, matters: a starter will not
          pitch tomorrow anyway, but an overworked one is still tired at her next
          start. The last game a series can reach has no later game, so lambda
          does not bite there.

The half-inning is solved exactly: a Markov chain over (batting slot, outs,
bases) with the real batting order and the pitcher's card at her current column,
every d100 face and d12 face enumerated through `engine.apply_line`. What follows
the half-inning is the team-neutral table in `play_wp`, so the model knows this
half's matchup and nothing about later ones.

Fixed for every policy, so that only bullpen management differs: the starting
nine (best nine by runs against a league pitcher; the starter bats in place of
the DH only when that scores more), the batting order, the starting pitcher (the
best rested arm), steals (the game's own WP rule), and the conventions --
disfavored pitchers do not pitch.
"""
from __future__ import annotations

import argparse
import datetime as dt
import time
import zlib
from math import erf
from functools import lru_cache

import numpy as np

from wpbl import engine, play, play_lineup
from wpbl.play_wp import B_SPAN, CARD_LINES, STATES, FixedDie, faces, state_index

# Pitchers the team stopped calling on (user, 2026-10-04). They still bat.
DISFAVORED = {"Raine Padgham", "Maggie Foxx", "Adelaide Frank", "Brittany Apgar",
              "Suzu Narasaki", "Jua Park"}
LINES = ("OUT", "K", "HBP", "BB", "1B", "HR", "ROE", "2B", "RUN")
PITCHES = np.array([3, 5, 3, 5, 3, 3, 3, 3, 0])     # per line, as play.py counts them
MAX_RUNS = 16
LEAGUE = "League average batter"
FIELD = play.POSITIONS
PA_PER_HALF = 4.4                                   # league plate appearances per half-inning


# --- the chain over one half-inning -----------------------------------------------

def _line_moves():
    """For each line: arrays (state, next state or -1 for the third out, runs, prob)."""
    out = {}
    for line in LINES:
        moves = []
        for outs, bases in STATES:
            i = state_index(outs, bases)
            if line == "RUN":
                b, r = engine.advance_all(bases) if any(bases) else (bases, 0)
                moves.append((i, state_index(outs, b), r, 1.0))
                continue
            dice = range(12) if line in ("1B", "OUT") else [0]
            for d in dice:
                b, made, r = engine.apply_line(line, bases, outs, FixedDie(d))
                j = -1 if outs + made >= 3 else state_index(outs + made, b)
                moves.append((i, j, 0 if j < 0 else r, 1 / len(dice)))
        m = np.array(moves)
        out[line] = (m[:, 0].astype(int), m[:, 1].astype(int), m[:, 2].astype(int), m[:, 3])
    return out


MOVES = _line_moves()


def line_probs(p_faces, b_faces):
    """Per-roll probability of each line: pitcher card, batter card and the bands."""
    t = engine.Table.from_lines(p_faces, b_faces)
    counts = dict.fromkeys(LINES, 0)
    for f in range(100):
        counts[t.read(f)] += 1
    return np.array([counts[l] / 100 for l in LINES])


def half_chain(p_faces, order_faces):
    """From every (slot, outs, bases), slot 0-8 of `order_faces`:
    D[s, k] = P(exactly k more runs this half), E[s] = expected pitches thrown."""
    n = 24 * 9
    T = np.zeros((MAX_RUNS, n, n))
    end, rate = np.zeros(n), np.zeros(n)
    for k, b_faces in enumerate(order_faces):
        pr = line_probs(p_faces, b_faces)
        base = 24 * k
        rate[base:base + 24] = pr @ PITCHES
        for li, line in enumerate(LINES):
            if pr[li] == 0:
                continue
            i, j, r, q = MOVES[line]
            nk = k if line == "RUN" else (k + 1) % 9
            ends = j < 0
            np.add.at(end, base + i[ends], pr[li] * q[ends])
            np.add.at(T, (np.minimum(r[~ends], MAX_RUNS - 1), base + i[~ends],
                          24 * nk + j[~ends]), pr[li] * q[~ends])
    inv = np.linalg.inv(np.eye(n) - T[0])
    D = np.zeros((n, MAX_RUNS))
    for k in range(MAX_RUNS):
        rhs = end * (k == 0)
        for r in range(1, k + 1):
            rhs = rhs + T[r] @ D[:, k - r]
        D[:, k] = inv @ rhs
    E = np.linalg.solve(np.eye(n) - T.sum(0), rate)
    return D, E


class Model:
    """Cards plus cached chains. One per process."""

    def __init__(self, cards, wp):
        self.cards, self.wp = cards, wp
        lg = play.pd.read_csv(play.DICE_DIR / "cards_league.csv", comment="#", dtype=str)
        row = lg[lg["player"] == LEAGUE].iloc[0]
        self.bat_faces = dict(cards.bat_faces)
        self.bat_faces[LEAGUE] = faces(row, CARD_LINES, "", B_SPAN)
        self.chain = lru_cache(maxsize=4096)(self._chain)
        self.bat_score = lru_cache(maxsize=None)(self._bat_score)
        self.usage = None              # a usage.Usage turns the conventions on
        self._lev_scale, self._lev_cache, self.run_scale = None, {}, None
        self.bats_only = set()         # teams that pick the nine by batting alone anyway
        self.starter_sits = set()      # teams whose starter never bats: they keep the DH

    def can_play(self, name, pos):
        """Legal by her card, and with the conventions on, 2+ starts there."""
        if pos == "DH":
            return True
        if pos not in self.cards.positions(name):
            return False
        return self.usage is None or self.usage.eligible(name, pos)

    def _chain(self, pitcher, column, order):
        return half_chain(self.cards.pitch_faces[pitcher][column],
                          [self.bat_faces[b] for b in order])

    def runs_per_inning(self, pitcher, column):
        """Quality: runs a league lineup scores off her in an inning from scratch."""
        D, _ = self.chain(pitcher, column, (LEAGUE,) * 9)
        return float(D[0] @ np.arange(MAX_RUNS))

    def pitches_per_inning(self, pitcher, column):
        """Pitches she throws in an inning from scratch, league lineup."""
        _, E = self.chain(pitcher, column, (LEAGUE,) * 9)
        return float(E[0])

    def leverage(self, inning, top, outs, bases, diff):
        """The leverage index (leverage.py's definition) in the dice game: the
        spread of win probability over the runs still possible this half-inning,
        scaled so an average real half-inning start reads 1.00."""
        if self._lev_scale is None:
            from wpbl.leverage import half_inning_starts
            st = half_inning_starts()
            self._lev_scale = float(np.mean([
                self._lev_raw(r.inning, r.half == "top", 0,
                              (False, r.inning > engine.INNINGS, False), int(r.diff))
                for r in st.itertuples()]))
        return self._lev_raw(inning, top, outs, tuple(bool(b) for b in bases), diff) / self._lev_scale

    def _lev_raw(self, inning, top, outs, bases, diff):
        key = (min(inning, engine.INNINGS + 1), top, outs, bases, diff)
        if key not in self._lev_cache:
            wp, inn = self.wp, key[0]
            D = wp.dist(outs, bases)
            vals = np.array([wp.after_top(inn, diff - k) if top else wp.after_bottom(inn, diff + k)
                             for k in range(len(D))])
            m = D @ vals
            self._lev_cache[key] = float(np.sqrt(D @ (vals - m) ** 2))
        return self._lev_cache[key]

    def run_value(self, inning, top, outs, bases, diff):
        """The run-value index: the win probability the fielding side loses to
        one more run allowed, given the runs that score anyway this half-inning,
        scaled so an average real half-inning start reads 1.00 (one run there is
        worth `self.run_scale` of win probability, about 0.062)."""
        if self.run_scale is None:
            from wpbl.leverage import half_inning_starts
            st = half_inning_starts()
            self.run_scale = float(np.mean([
                self._rv_raw(r.inning, r.half == "top", 0,
                             (False, r.inning > engine.INNINGS, False), int(r.diff))
                for r in st.itertuples()]))
        return self._rv_raw(inning, top, outs, tuple(bool(b) for b in bases), diff) / self.run_scale

    def _rv_raw(self, inning, top, outs, bases, diff):
        key = ("rv", min(inning, engine.INNINGS + 1), top, outs, bases, diff)
        if key not in self._lev_cache:
            wp, inn = self.wp, key[1]
            D = wp.dist(outs, bases)
            if top:                              # home fields: away's runs lower home WP
                v = sum(D[k] * (wp.after_top(inn, diff - k) - wp.after_top(inn, diff - k - 1))
                        for k in range(len(D)))
            else:                                # away fields: home's runs raise home WP
                v = sum(D[k] * (wp.after_bottom(inn, diff + k + 1) - wp.after_bottom(inn, diff + k))
                        for k in range(len(D)))
            self._lev_cache[key] = float(v)
        return self._lev_cache[key]

    def _bat_score(self, name):
        """Runs a lineup of nine of her scores in seven innings off the league pitcher."""
        p_line = play_lineup.league_table().p_line
        blocks = {name: play_lineup.batter_blocks(p_line, self.bat_faces[name])}
        return play_lineup.expected_runs(blocks, [name] * 9)


# --- pregame: the nine, the order, the starter ---------------------------------------

@lru_cache(maxsize=None)
def best_nine(model, team, starter):
    """[(name, pos)] in batting order. The starter bats at P (no DH) only when
    that scores more than a DH; otherwise she is out of the lineup."""
    cards = model.cards
    bats = [b for b in cards.team_batters(team) if b != starter]
    score = {b: model.bat_score(b) for b in bats}

    def assign(spots, pool):
        best = {}                                   # mask of used -> (total, picks)
        best[frozenset()] = (0.0, ())
        for pos in spots:
            nxt = {}
            for used, (tot, picks) in best.items():
                for b in pool:
                    if b in used or (pos != "DH" and pos not in cards.positions(b)):
                        continue
                    key = used | {b}
                    cand = (tot + score[b], picks + ((b, pos),))
                    if key not in nxt or cand[0] > nxt[key][0]:
                        nxt[key] = cand
            best = nxt
        return max(best.values(), key=lambda x: x[0]) if best else (-1.0, ())

    dh_total, dh = assign(FIELD + ("DH",), bats)
    nine = list(dh)
    if starter in cards.batter:
        f_total, field = assign(FIELD, bats)
        if f_total + model.bat_score(starter) > dh_total:
            nine = list(field) + [(starter, "P")]
    pos = dict(nine)
    names = [n for n, _ in sorted(nine, key=lambda x: -model.bat_score(x[0]))]
    p_line = play_lineup.league_table().p_line
    blocks = {n: play_lineup.batter_blocks(p_line, model.bat_faces[n]) for n in names}
    order, _ = play_lineup.local_best(blocks, names, {})
    return [(n, pos[n]) for n in order]


def arms(model, team):
    return [n for n in model.cards.team_pitchers(team) if n not in DISFAVORED]


def pick_starter(model, team, fatigue):
    """The best rested arm with the stamina to start; failing that, the most rested."""
    cards = model.cards
    rested = [n for n in arms(model, team) if engine.enter(fatigue[n]) <= 0]
    deep = [n for n in rested if cards.stamina(n) >= 70] or rested
    if deep:
        return min(deep, key=lambda n: model.runs_per_inning(n, "fading"))
    return min(arms(model, team), key=lambda n: fatigue[n])


def _order(model, nine):
    """Best batting order for [(name, pos)]."""
    pos = dict(nine)
    names = [n for n, _ in sorted(nine, key=lambda x: -model.bat_score(x[0]))]
    p_line = play_lineup.league_table().p_line
    blocks = {n: play_lineup.batter_blocks(p_line, model.bat_faces[n]) for n in names}
    order, _ = play_lineup.local_best(blocks, names, {})
    return [(n, pos[n]) for n in order]


@lru_cache(maxsize=None)
def usage_nine(model, team, starter, starter_bats=True):
    """The conventions' nine: most weighted window starts (ties to batting),
    then positions by window starts there. A starter her team mostly batted
    when she started (usage.bats_at_p, rule 4') bats at P and the team has no DH."""
    cards, u = model.cards, model.usage
    roster = cards.team_batters(team)
    total = {b: u.weight[(team, b)] for b in roster}
    batting_starter = starter_bats and starter in roster and (team, starter) in u.bats_at_p
    pool = [b for b in roster if b != starter]
    spots = FIELD if batting_starter else FIELD + ("DH",)

    def value(b, pos):
        # the nine first (window starts), then where she played, then her bat
        return 1000 * total[b] + u.weight_at[(team, b, pos)] + 1e-3 * model.bat_score(b)

    for strict in (True, False):           # if 2+ starts leaves a hole, fall back to the card
        best = {frozenset(): (0.0, ())}
        for pos in spots:
            nxt = {}
            for used, (tot, picks) in best.items():
                for b in pool:
                    ok = model.can_play(b, pos) if strict else (pos == "DH" or pos in cards.positions(b))
                    if b in used or not ok:
                        continue
                    key, cand = used | {b}, (tot + value(b, pos), picks + ((b, pos),))
                    if key not in nxt or cand[0] > nxt[key][0]:
                        nxt[key] = cand
            best = nxt
        if best:
            break
    nine = list(max(best.values(), key=lambda x: x[0])[1])
    if batting_starter:
        nine.append((starter, "P"))
    return _order(model, nine)


def usage_starter(model, team, fatigue):
    return usage_starter_step(model, team, fatigue)[0]


def usage_starter_step(model, team, fatigue):
    """ASSUMPTION. (starter, step): 1, a starter by role (2+ starts in the last
    10) who would take the mound fresh, the best of them; 2, else the least tired
    role starter who would not enter gassed; 3, else the best rested arm of any
    role (a bullpen game); 4, else the least tired arm."""
    cards = model.cards
    roles = [n for n in model.usage.starters[team] if n in cards.pitcher and n not in DISFAVORED]
    on = {n: engine.enter(fatigue[n]) for n in arms(model, team)}
    fresh = [n for n in roles if on[n] < engine.FRESH_UNTIL]
    if fresh:
        return min(fresh, key=lambda n: model.runs_per_inning(n, "fading")), 1
    able = [n for n in roles if on[n] <= cards.stamina(n)]
    if able:
        return min(able, key=lambda n: fatigue[n]), 2
    rested = [n for n in arms(model, team) if on[n] <= 0]
    if rested:
        return min(rested, key=lambda n: model.runs_per_inning(n, "fading")), 3
    return min(arms(model, team), key=lambda n: fatigue[n]), 4


def starting_nine(model, team, starter):
    if model.usage and team not in model.bats_only:
        return usage_nine(model, team, starter, team not in model.starter_sits)
    return best_nine(model, team, starter)


def starter_for(model, team, fatigue):
    return usage_starter(model, team, fatigue) if model.usage else pick_starter(model, team, fatigue)


# --- in-game: the moves a fielding side can make ---------------------------------------

def options(g, side, model, disfavored=False):
    """Every legal pitching change: [(pitcher, lineup or None, slots after)].

    A reliever from the bench takes the pitcher's slot when there is no DH -- or,
    if the outgoing pitcher bats and can play a field position, she moves there
    and the reliever takes that fielder's slot (Whitmore to CF). A player already
    in the lineup moves to P; her field position goes to the DH or to the
    outgoing pitcher if either can play it, else to the best bench bat who can.
    Positions follow `model.can_play` (the card, plus 2+ starts with the
    conventions on). Disfavored pitchers are left out unless `disfavored`."""
    cards = model.cards
    order = [(s.name, s.pos) for s in side.order]
    out = []
    p_slot = next((i for i, (m, p) in enumerate(order) if p == "P"), None)
    for n in g.available(side):
        if n in DISFAVORED and not disfavored:
            continue
        if n in cards.batter and cards.batter[n]["team"] != side.team:
            continue                 # traded away: her pitcher card is her old team's (Narasaki)
        after = [(n if p == "P" else m, p) for m, p in order]
        out.append((n, None, after))
        if p_slot is None:
            continue
        old = order[p_slot][0]
        for j, (q, qpos) in enumerate(order):         # she stays in, a fielder makes way
            if j == p_slot or qpos == "DH" or not model.can_play(old, qpos):
                continue
            new = list(order)
            new[p_slot], new[j] = (old, qpos), (n, "P")
            out.append((n, new, new))
    bench = sorted((b for b in cards.team_batters(side.team) if b not in side.batting()
                    and b not in side.gone and b not in side.used and b != side.pitcher),
                   key=lambda b: -model.bat_score(b))
    for x, xpos in order:
        if (x not in cards.pitcher or x in side.used or xpos == "P"
                or cards.pitcher[x]["team"] != side.team       # no pitcher card for this team
                or (x in DISFAVORED and not disfavored)):
            continue
        base = [(m, "P" if m == x else p) for m, p in order]
        if xpos == "DH":
            out.append((x, base, base))
            continue
        # who covers xpos: the DH, or the pitcher batting at P, or a bench player in that slot
        filler_slot = next((i for i, (m, p) in enumerate(order) if p in ("DH",)
                            or (p == "P" and m == side.pitcher)), None)
        if filler_slot is None:
            continue
        holder = order[filler_slot][0]
        for f in [holder] + bench:                       # the holder herself stays in the game
            if not model.can_play(f, xpos):
                continue
            new = list(base)
            new[filler_slot] = (f, xpos)
            out.append((x, new, new))
            break
    return out


def relief(policy, opts):
    """Who may relieve, with the conventions on. Under the blanket ban (the
    policy's `reserve` is "ban") no starter by role relieves; otherwise only the
    arms series() has protected for a planned start are held back. Either way, if
    nobody else can come in, anyone may."""
    model = policy.model
    if model.usage is None:
        return opts
    held = model.usage.starters[policy.team] if policy.reserve == "ban" else policy.protected
    return [o for o in opts if o[0] not in held] or opts


RELIEF_PITCHES = 31      # a relief outing: 31 pitches, every 5 days (dice_game_spec section 7.4)


def plan_rotation(model, team, fatigue, today, days):
    """[(starter, days from today)] for each later game in `days`: the best role
    starter who will be fresh that day, else the least tired. Today's starter is
    not planned again."""
    cards = model.cards
    pool = [n for n in model.usage.starters[team]
            if n in cards.pitcher and n not in DISFAVORED and n != today]
    plan = []
    for d in days:
        free = [n for n in pool if n not in {x for x, _ in plan}]
        if not free:
            break
        fresh = [n for n in free if engine.enter(engine.recover(fatigue[n], d)) < engine.FRESH_UNTIL]
        pick = (min(fresh, key=lambda n: model.runs_per_inning(n, "fading")) if fresh
                else min(free, key=lambda n: fatigue[n]))
        plan.append((pick, d))
    return plan


def protected(model, team, fatigue, today, days):
    """Planned starters a typical relief outing today would leave short of fresh
    on their start day."""
    held = set()
    for n, d in plan_rotation(model, team, fatigue, today, days):
        after = engine.enter(fatigue[n]) + RELIEF_PITCHES
        if engine.enter(engine.recover(after, d)) >= engine.FRESH_UNTIL:
            held.add(n)
    return held


LADDER = ("relievers", "starters not held for a start", "disfavored pitchers", "anyone legal")


def ladder(policy, g, side):
    """(options, tier) for a pitcher who must be replaced (user, 2026-10-12): the
    first tier with anyone in it, of
      1 relievers by role who would not enter gassed
      2 starters by role not held for an upcoming start (`policy.protected`),
        who would not enter gassed
      3 disfavored pitchers who would not enter gassed
      4 anyone legal
    The policy's own score then chooses within the tier."""
    model, cards = policy.model, policy.model.cards
    every = options(g, side, model, disfavored=True)
    starters = model.usage.starters[policy.team] if model.usage else set()
    held = starters if policy.reserve == "ban" else policy.protected

    def ready(o):
        return engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0])) != "gassed"

    tiers = [
        [o for o in every if ready(o) and o[0] not in DISFAVORED and o[0] not in starters],
        [o for o in every if ready(o) and o[0] not in DISFAVORED and o[0] in starters
         and o[0] not in held],
        [o for o in every if ready(o) and o[0] in DISFAVORED],
        every,
    ]
    for i, t in enumerate(tiers):
        if t:
            return t, i + 1
    return [], 0


def lineup_text(slots):
    return [f"{n} {p}" for n, p in slots]


# --- the policies -----------------------------------------------------------------------

class Policy:
    """Shared plumbing. `series` sets `future`: days from today to each later game
    the series could still reach."""

    def __init__(self, model, team):
        self.model, self.team = model, team
        self.future = []
        self.record, self.need = (0, 0), 3       # (my wins, theirs) before this game
        self.log = None                          # a list turns on the decision log
        self.reserve = "ban"     # "ban": no starter relieves; "guaranteed": hold starters
        self.protected = set()   # planned for games sure to be played; "next": and the next game

    def note(self, g, side, kind, choice=None, options=0, rv=None):
        """One row of the decision log, when it is on."""
        if self.log is None:
            return
        name = choice[0] if isinstance(choice, tuple) else choice
        self.log.append({"team": side.team, "inning": g.inning, "half": "top" if g.top else "bottom",
                         "outs": g.outs, "lead": (g.home.runs - g.away.runs) * (1 if side is g.home else -1),
                         "pitcher": side.pitcher, "count": g.fatigue[side.pitcher],
                         "column": g.column(side.pitcher), "kind": kind, "options": options,
                         "chosen": name, "lineup_move": isinstance(choice, tuple),
                         "chosen_count": None if name in (None, "keep") else g.fatigue[name],
                         "run_value": rv, "record": self.record})

    def __call__(self, g, at, side):
        if side.team != self.team or not g.can_change(side):
            return "keep"
        return self.decide(g, side)


DH_MARGIN = 0.1         # ASSUMPTION: runs an inning a lineup arm must save to cost the DH


class Baseline(Policy):
    """B0: keep her until gassed, then the arm that allows the fewest runs. With
    `dh_aware`, an arm who keeps the DH comes in unless one who costs it allows
    DH_MARGIN fewer runs an inning."""

    dh_aware = False

    def decide(self, g, side):
        if g.column(side.pitcher) != "gassed":
            return "keep"
        opts = relief(self, options(g, side, self.model))
        if not opts:
            self.note(g, side, "nobody left")
            return "keep"
        cards = self.model.cards

        def quality(o):
            c = engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0]))
            # her pitching first; between moves that bring in the same arm, more bats
            return (self.model.runs_per_inning(o[0], c),
                    -sum(self.model.bat_score(m) for m, _ in o[2]))
        best = min(opts, key=quality)
        if self.dh_aware and any(p == "DH" for _, p in ((s_.name, s_.pos) for s_ in side.order)):
            keeps = [o for o in opts if any(p == "DH" for _, p in o[2])]
            if keeps:
                k = min(keeps, key=quality)
                if quality(k)[0] <= quality(best)[0] + DH_MARGIN:
                    best = k
        choice = best[0] if best[1] is None else (best[0], lineup_text(best[1]))
        self.note(g, side, "relieved gassed", choice, len(opts))
        return choice


# --- the series and the median rule (B1) ------------------------------------------------

@lru_cache(maxsize=None)
def series_win(a, b, need):
    """P(win the series) from a wins to b, a coin flip per game."""
    if a == need:
        return 1.0
    if b == need:
        return 0.0
    return 0.5 * series_win(a + 1, b, need) + 0.5 * series_win(a, b + 1, need)


@lru_cache(maxsize=None)
def games_left(a, b, need):
    """Expected number of games still to be played from a wins to b."""
    if need in (a, b):
        return 0.0
    return 1 + 0.5 * games_left(a + 1, b, need) + 0.5 * games_left(a, b + 1, need)


def leverage(a, b, need):
    """How much this game moves the series: P(series) if won minus if lost."""
    return series_win(a + 1, b, need) - series_win(a, b + 1, need)


def median_leader_wp(wp):
    """{(inning, 'top'/'bottom'): median WP of the leading team at the start of
    that half}, ties counting 0.5 -- the user's table, solved exactly from the
    team-neutral run distributions. Innings 1-7."""
    R = 40
    dist = np.zeros(2 * R + 1)
    dist[R] = 1.0                                   # home minus away, offset R
    D = wp._start
    diffs = np.arange(2 * R + 1) - R

    def median(f):
        home = np.array([f(d) for d in diffs])
        lead = np.where(diffs > 0, home, 1 - home)
        lead[R] = 0.5
        o = np.argsort(lead)
        return float(lead[o][np.searchsorted(np.cumsum(dist[o]), 0.5)])

    out = {}
    for inning in range(1, engine.INNINGS + 1):
        out[(inning, "top")] = median(lambda d: wp.top(inning, d))
        new = np.zeros_like(dist)
        for k in range(len(D)):
            new[:len(dist) - k] += D[k] * dist[k:]          # away scores k
        dist = new
        out[(inning, "bottom")] = median(lambda d: wp.bottom(inning, d))
        new = np.zeros_like(dist)
        for k in range(len(D)):
            new[k:] += D[k] * dist[:len(dist) - k]          # home scores k
        dist = new
    return out


A_ARMS = 2


class MedianRule(Policy):
    """B1. Relieves when the pitcher is gassed, like B0; the stakes decide which
    arm. Counts what it chose in `MedianRule.counts`."""

    counts = {}
    _median = None

    def __init__(self, model, team):
        super().__init__(model, team)
        if MedianRule._median is None:
            MedianRule._median = median_leader_wp(model.wp)
        pool = arms(model, team)
        if model.usage is not None:                    # A arms are relievers
            pool = [n for n in pool if n not in model.usage.starters[team]]
        ranked = sorted(pool, key=lambda n: model.runs_per_inning(n, "fading"))
        self.a_arms = set(ranked[:A_ARMS])

    def bar(self, inning, half):
        """The (1 - leader WP) above which an A arm comes in."""
        a, b = self.record
        lev, later = leverage(a, b, self.need), games_left(a, b, self.need) - 1
        lev0, later0 = leverage(0, 0, self.need), games_left(0, 0, self.need) - 1
        m = MedianRule._median[(min(inning, engine.INNINGS), half)]
        return (1 - m) * (later / lev) / (later0 / lev0)

    def decide(self, g, side):
        if g.column(side.pitcher) != "gassed":
            return "keep"
        opts = relief(self, options(g, side, self.model))
        if not opts:
            MedianRule.counts["nobody left"] = MedianRule.counts.get("nobody left", 0) + 1
            return "keep"
        half = "top" if g.top else "bottom"
        home = g.wp_home()
        lead = max(home, 1 - home) if g.home.runs != g.away.runs else 0.5
        cards = self.model.cards

        def quality(o):
            c = engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0]))
            # her pitching first; between moves that bring in the same arm, more bats
            return (self.model.runs_per_inning(o[0], c),
                    -sum(self.model.bat_score(m) for m, _ in o[2]))

        if 1 - lead >= self.bar(g.inning, half):
            # an A arm, unless the ones left would enter already gassed
            ready = [o for o in opts if o[0] in self.a_arms and engine.column_for(
                engine.enter(g.fatigue[o[0]]), cards.stamina(o[0])) != "gassed"]
            pool, kind = ready or opts, "A" if ready else "A wanted, none ready"
        else:
            pool, kind = [o for o in opts if o[0] not in self.a_arms] or opts, "B"
        MedianRule.counts[kind] = MedianRule.counts.get(kind, 0) + 1
        best = min(pool, key=quality)
        return best[0] if best[1] is None else (best[0], lineup_text(best[1]))


# --- B2: runs over the rest of the game, and the warm-ups that cost ----------------------------

WARMUP_WP = 0.0077      # one warm-up: 30 marginal pitches in a 7-day window, run-value index
                        # (marginal_pitches.py)
EARLY_GATE = 2.0        # user: replace a pitcher who is not gassed only in the top ~4% of
                        # plate appearances by run value (2.03 in real 2026 games)
PITCH_SD = 6.0          # ASSUMPTION: spread of pitches per inning, for the chance an arm runs out


class Planner(Policy):
    """B2 (manager_spec.md, "Pricing a warm-up"). At each legal plate appearance
    where the pitcher is gassed -- or not gassed but the leverage is 2.0+ -- every
    option gets

        score = series leverage today x WP per run now x (-runs to the end)
                - next game's series leverage x 0.0077 x (expected warm-ups)

    WP per run now = the run-value index x 0.062: what one more run allowed
    costs from this state (a blowout's is near 0, a tie late about 4 times
    average).

    Runs to the end: the arm pitches until gassed (fresh, then fading column),
    then the other arms in turn, each for her own coverage (`plan`). Expected
    warm-ups: 1 for a new arm, plus each later arm by the chance she is needed.
    An arm who would enter gassed is not an option while another would not. A gassed pitcher is always replaced, except with
    2 outs in the 7th or later (user), where keeping her is scored too."""

    counts = {}
    early = True             # consider replacing a pitcher who is not gassed
    use_ladder = False       # the fallback ladder (postseason): disfavored arms as tier 3
    explain = False          # write a manager's note into the game log before each change

    def _count(self, k):
        Planner.counts[k] = Planner.counts.get(k, 0) + 1

    def next_weight(self):
        """The next game's series leverage, averaged over today's result; 0 if
        no next game is possible either way."""
        a, b = self.record
        return sum(0.5 * leverage(x, y, self.need) for x, y in ((a + 1, b), (a, b + 1))
                   if x < self.need and y < self.need)

    def explain_note(self, g, side, gassed, rv, stake, later, tier, scored, detail, chosen):
        """One line for the game log: why this choice."""
        cards = self.model.cards
        why = f"{side.pitcher} is gassed" if gassed else "high stakes"
        a, b = self.record
        head = (f"- Manager ({side.team}): {why}. Series {a}-{b} (leverage "
                f"{leverage(a, b, self.need):.2f}), run value {rv:.2f}, next game weight "
                f"{self.next_weight():.2f}")
        if tier:
            head += f"; choosing among {LADDER[tier - 1]}"
        parts = []
        seen = set()
        top = max(sc for sc, _ in scored)
        for sc, o in sorted(scored, key=lambda x: -x[0]):
            name = side.pitcher if o is None else o[0]
            if name in seen:
                continue
            seen.add(name)
            count, runs, warm = detail[name]
            label = "keep " + name if o is None else name
            col = engine.column_for(count, cards.stamina(name))
            parts.append(f"{label} ({count}, {col}): {runs:.2f} runs to the end, "
                         f"{warm:.1f} warm-ups, {1000 * (sc - top):+.2f}")
            if len(parts) == 3:
                break
        pick = "keep " + side.pitcher if chosen is None else chosen[0]
        g.emit(head + ". Options (count on entering, column; score against the best, in "
               "thousandths of series win probability): " + "; ".join(parts)
               + f". Choice: {pick}.")

    def stint(self, name, count, left):
        """(innings she can pitch before she is gassed, capped at `left`; runs
        allowed in them). Fresh column to 20, then fading."""
        model, stam = self.model, self.model.cards.stamina(name)
        if count >= stam:                        # gassed at her stamina (cards v0.7.0 on)
            return 0.0, 0.0
        fresh = max(0, engine.FRESH_UNTIL - count)
        fade = max(0, stam - max(count, engine.FRESH_UNTIL))
        i_fresh = min(fresh / model.pitches_per_inning(name, "fresh"), left)
        i_fade = min(fade / model.pitches_per_inning(name, "fading"), left - i_fresh)
        return (i_fresh + i_fade, i_fresh * model.runs_per_inning(name, "fresh")
                + i_fade * model.runs_per_inning(name, "fading"))

    def plan(self, g, name, count, others):
        """(runs to the end of regulation, expected warm-ups after hers).

        She pitches until gassed (a pitcher already gassed, kept with 2 outs in
        the 7th, finishes this half only). The innings left go to the other
        arms in turn, best first (runs per inning in the column she would enter
        in), each only for her own coverage; each is a warm-up, counted by the
        chance she is needed at all. If the staff runs out, the last arm pitches
        the rest from her gassed column."""
        model, cards = self.model, self.model.cards
        now = (3 - g.outs) / 3
        left = now + max(0, engine.INNINGS - g.inning)
        sd = PITCH_SD / 18.6                     # innings: about a third of an inning
        if count >= cards.stamina(name):
            cov, runs = now, now * model.runs_per_inning(name, "gassed")
        else:
            cov, runs = self.stint(name, count, left)
        warm, last = 0.0, name
        queue = sorted(others, key=lambda n: model.runs_per_inning(
            n, engine.column_for(engine.enter(g.fatigue[n]), cards.stamina(n))))
        for n in queue:
            if cov >= left - 1e-9:
                break
            warm += 0.5 * (1 + erf((left - cov) / (sd * np.sqrt(max(left, 1e-9))) / np.sqrt(2)))
            c, r = self.stint(n, engine.enter(g.fatigue[n]), left - cov)
            cov, runs, last = cov + c, runs + r, n
        if cov < left - 1e-9:                    # nobody left: the last arm pitches on gassed
            runs += (left - cov) * model.runs_per_inning(last, "gassed")
        return runs, warm

    def decide(self, g, side):
        gassed = g.column(side.pitcher) == "gassed"
        if not gassed and (not self.early or g.column(side.pitcher) == "fresh"):
            return "keep"            # user: no early swap while she is still fresh
        rv = self.model.run_value(g.inning, g.top, g.outs, [b is not None for b in g.bases],
                                  g.home.runs - g.away.runs)
        if not gassed and rv < EARLY_GATE:
            return "keep"
        cards = self.model.cards
        if self.use_ladder:
            opts, tier = ladder(self, g, side)
        else:
            opts, tier = relief(self, options(g, side, self.model)), None
            # the floor: no arm who would enter gassed while another would not
            ready = [o for o in opts if engine.column_for(engine.enter(g.fatigue[o[0]]),
                                                          cards.stamina(o[0])) != "gassed"]
            opts = ready or opts
        if not opts:
            self._count("nobody left")
            self.note(g, side, "nobody left", None, 0, rv)
            if self.explain and gassed:
                g.emit(f"- Manager ({side.team}): {side.pitcher} is gassed and no one can come in")
            return "keep"
        a, b = self.record
        stake = leverage(a, b, self.need) * rv * self.model.run_scale
        later = self.next_weight() * WARMUP_WP
        names = list(dict.fromkeys(o[0] for o in opts))

        detail = {}

        def score(name, count, warm, slots):
            runs, need = self.plan(g, name, count, [n for n in names if n != name])
            bats = sum(self.model.bat_score(m) for m, _ in slots)
            detail[name] = (count, runs, warm + need)
            return -stake * runs - later * (warm + need) + 1e-9 * bats

        scored = [(score(o[0], engine.enter(g.fatigue[o[0]]), 1, o[2]), o) for o in opts]
        if not gassed or (g.inning >= engine.INNINGS and g.outs == 2):
            keep = score(side.pitcher, g.fatigue[side.pitcher], 0,
                         [(s_.name, s_.pos) for s_ in side.order])
            scored.append((keep, None))
        best, o = max(scored, key=lambda x: x[0])
        if self.explain and (gassed or o is not None):
            self.explain_note(g, side, gassed, rv, stake, later, tier, scored, detail, o)
        if o is None:
            kind = "rode out the 7th" if gassed else "kept at high leverage"
            self._count(kind)
            self.note(g, side, kind, "keep", len(opts), rv)
            return "keep"
        kind = "relieved gassed" if gassed else "early swap"
        self._count(kind)
        choice = o[0] if o[1] is None else (o[0], lineup_text(o[1]))
        self.note(g, side, kind, choice, len(opts), rv)
        return choice


class Shadow(Policy):
    """Rest-of-half WP, less lambda per pitch carried into the next game."""

    def __init__(self, model, team, lam):
        super().__init__(model, team)
        self.lam = lam

    def excess(self, count):
        return sum(max(0.0, engine.recover(count, d) - engine.RESTED) for d in self.future)

    def value(self, g, side, pitcher, count, entering, slots):
        model, cards = self.model, self.model.cards
        bat = g.away if side is g.home else g.home
        now = engine.enter(count) if entering else count
        col = engine.column_for(now, cards.stamina(pitcher))
        D, E = model.chain(pitcher, col, tuple(bat.batting()))
        s = 24 * (bat.spot % 9) + state_index(g.outs, tuple(b is not None for b in g.bases))
        d = g.home.runs - g.away.runs
        wp = model.wp
        if g.top:
            home = sum(D[s, k] * wp.after_top(g.inning, d - k) for k in range(MAX_RUNS))
        else:
            home = sum(D[s, k] * wp.after_bottom(g.inning, d + k) for k in range(MAX_RUNS))
        mine = home if side is g.home else 1 - home
        # slack this arm loses for the rest of the series
        cost = self.lam * (self.excess(now + E[s]) - self.excess(count))
        # offence: a bench bat replacing a lineup bat, for the rest of the game
        if slots is not None:
            before = sum(model.bat_score(s_.name) for s_ in side.order)
            after = sum(model.bat_score(n) for n, _ in slots)
            left = max(engine.INNINGS - g.inning + 0.5, 0.5) / engine.INNINGS
            runs = (after - before) / 9 * left
            lev = abs(wp.after_top(g.inning, d + 1) - wp.after_top(g.inning, d - 1)) / 2
            mine += runs * lev
        return mine - cost

    def decide(self, g, side):
        keep = self.value(g, side, side.pitcher, g.fatigue[side.pitcher], False, None)
        best, choice = keep, "keep"
        for name, lineup, after in options(g, side, self.model):
            v = self.value(g, side, name, g.fatigue[name], True, after)
            if v > best + 1e-9:
                best, choice = v, (name if lineup is None else (name, lineup_text(lineup)))
        return choice


# --- a series ------------------------------------------------------------------------------

FINAL = {"days": [0, 1, 3, 4, 6], "home_hi": [True, True, False, False, True]}   # 16-22 Sep
SEMI = {"days": [0, 2, 4], "home_hi": [True, False, True]}


def series(model, hi, lo, policies, fmt, seed, usage=None, trace=None, record=None):
    """Play one series; hi hosts games 1, 2 and 5 of five (1 and 3 of three).
    policies: {team: Policy}. Returns (winner, games played). `usage`, if given,
    collects (team, game number, pitchers used, pitches thrown, started with a DH,
    ended with one, relievers who started in the lineup) per game; `trace`
    collects the record {team: wins} before each game."""
    cards, wp = model.cards, model.wp
    fatigue = {n: engine.RESTED for n in cards.pitcher}
    need = len(fmt["days"]) // 2 + 1
    wins = {hi: 0, lo: 0}
    rng = np.random.default_rng(seed)
    for gi, day in enumerate(fmt["days"]):
        home, away = (hi, lo) if fmt["home_hi"][gi] else (lo, hi)
        lineups = {}
        steps = {}
        for t in (away, home):
            if model.usage:
                st, steps[t] = usage_starter_step(model, t, fatigue)
            else:
                st, steps[t] = pick_starter(model, t, fatigue), None
            nine = starting_nine(model, t, st)
            lineups[t] = {"pitcher": st, "order": lineup_text(nine)}
        setup = {"seed": int(rng.integers(1 << 31)), "date": dt.date(2026, 9, 16) + dt.timedelta(day),
                 "cards": cards.version, "away": away, "home": home,
                 "lineup": lineups, "fatigue": dict(fatigue)}
        g = play.Game(setup, [], cards, wp)
        if trace is not None:
            trace.append(dict(wins))
        for t, p in policies.items():
            other = lo if t == hi else hi
            p.future = [d - day for d in fmt["days"][gi + 1:]]
            p.record, p.need = (wins[t], wins[other]), need
            if model.usage is not None and p.reserve != "ban":
                # games sure to be played after today; with "next", the next game too
                sure = need - max(wins[t], wins[other]) - 1
                ahead = p.future[:sure]
                if p.reserve == "next" and p.future and not ahead:
                    ahead = p.future[:1]
                p.protected = protected(model, t, fatigue, lineups[t]["pitcher"], ahead)
        g.manager = lambda g_, at, side: policies[side.team](g_, at, side)
        g.every_pa = True
        g.run()
        winner = home if g.home.runs > g.away.runs else away
        if record is not None:
            # every game, as it ends: `record(game, info)`
            nxt = fmt["days"][gi + 1] - day if gi + 1 < len(fmt["days"]) else None
            record(g, {"game": gi + 1, "day": day, "wins_before": dict(wins), "steps": steps,
                       "fatigue_before": dict(fatigue), "next_gap": nxt, "lineups": lineups})
        if usage is not None:
            for side in (g.away, g.home):
                start = lineups[side.team]["order"]
                in_lineup = {e.rpartition(" ")[0] for e in start}
                usage.append((side.team, gi + 1, len(side.used),
                              sum(g.fatigue[n] - g.stats[n]["start"] for n in side.used),
                              any(e.endswith(" DH") for e in start),          # started with a DH
                              any(s_.pos == "DH" for s_ in side.order),       # ended with one
                              sum(n in in_lineup for n in side.used[1:]),     # relievers from the lineup
                              sum(e["event"] == "pa" and e["fielding"] == side.team
                                  and e["column"] == "gassed" for e in g.events),    # PAs pitched gassed
                              tuple(e["inning"] for e in g.events if e["event"] == "pa"
                                    and e["fielding"] == side.team and e["column"] == "gassed")))
        wins[winner] += 1
        fatigue = dict(g.fatigue)
        if wins[winner] == need:
            return winner, gi + 1
        gap = fmt["days"][gi + 1] - day
        fatigue = {n: engine.recover(c, gap) for n, c in fatigue.items()}
    raise AssertionError("series without a winner")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="manager")
    ap.add_argument("--series", type=int, default=50, help="series per matchup and policy")
    ap.add_argument("--lambdas", type=float, nargs="*", default=[0.0, 0.001, 0.003])
    ap.add_argument("--format", choices=("final", "semi"), default="final")
    ap.add_argument("--teams", nargs="*", default=["BOS", "LAQ", "NYH", "SFF"])
    ap.add_argument("--b1", action="store_true", help="also play the median rule")
    ap.add_argument("--b2", action="store_true", help="also play B2 (runs to the end, priced warm-ups)")
    ap.add_argument("--b2-no-early", action="store_true", help="also play B2 relieving only at gassed")
    ap.add_argument("--skip-b0", action="store_true", help="leave out the B0-vs-B0 row")
    ap.add_argument("--conventions", action="store_true",
                    help="lineups, starters and positions as the real teams used them (usage.py)")
    a = ap.parse_args(argv)
    fmt = FINAL if a.format == "final" else SEMI
    cards, wp = play.shared()
    model = Model(cards, wp)
    if a.conventions:
        from wpbl import usage
        model.usage = usage.Usage(cards)
    pairs = [(x, y) for x in a.teams for y in a.teams if x != y]   # (AI team, opponent)
    t0 = time.time()
    print(f"{a.format}: {a.series} series per (team, opponent, side), opponent plays B0"
          + (", conventions on" if a.conventions else ""))
    rows = {}
    runs = [] if a.skip_b0 else [("B0", lambda t: Baseline(model, t))]
    if a.b1:
        runs.append(("B1 median", lambda t: MedianRule(model, t)))
    if a.b2:
        runs.append(("B2 planner", lambda t: Planner(model, t)))
    if a.b2_no_early:
        def no_early(t):
            p = Planner(model, t)
            p.early = False
            return p
        runs.append(("B2 no early", no_early))
    runs += [(f"shadow {l:g}", (lambda l: lambda t: Shadow(model, t, l))(l)) for l in a.lambdas]
    for label, make in runs:
        MedianRule.counts, Planner.counts = {}, {}
        won = n = games = 0
        usage = []
        for me, opp in pairs:
            for hi_is_me in (True, False):
                hi, lo = (me, opp) if hi_is_me else (opp, me)
                for k in range(a.series):
                    pol = {me: make(me), opp: Baseline(model, opp)}
                    seed = zlib.crc32(f"{me}{opp}{hi_is_me}{k}".encode())
                    w, played = series(model, hi, lo, pol, fmt, seed, use := [])
                    usage += [u for u in use if u[0] == me]
                    won += w == me
                    n += 1
                    games += played
        p = won / n
        rows[label] = p
        print(f"  {label:14s} series won {100 * p:5.1f}% +/- {100 * np.sqrt(p * (1 - p) / n):.1f} "
              f"of {n}  ({games / n:.2f} games each, {time.time() - t0:.0f}s)", flush=True)
        u = np.array([(x[1], x[2], x[3]) for x in usage], float)
        print("      pitchers used per game, by game number: " + "  ".join(
            f"G{int(k)} {u[u[:, 0] == k, 1].mean():.2f}" for k in sorted(set(u[:, 0]))), flush=True)
        d = np.array([x[4:8] for x in usage], float)
        print(f"      warm-ups a game {u[:, 1].mean():.2f}; PAs pitched gassed a game {d[:, 3].mean():.2f}; "
              f"relievers from the lineup a game {d[:, 2].mean():.2f}; DH lost in "
              f"{100 * (1 - d[d[:, 0] == 1, 1]).mean():.0f}% of DH games", flush=True)
        games_by = {k: sum(1 for x in usage if x[1] == k) for k in range(1, 6)}
        print("      PAs pitched gassed a game, by game number: " + "  ".join(
            f"G{k} {sum(x[7] for x in usage if x[1] == k) / games_by[k]:.2f}"
            for k in range(1, 6) if games_by[k]), flush=True)
        inns = [i for x in usage for i in x[8]]
        print("      ... by inning (share of all gassed PAs): " + "  ".join(
            f"{i if i < 8 else '8+'} {100 * sum(1 for j in inns if min(j, 8) == i) / max(len(inns), 1):.0f}%"
            for i in range(1, 9)), flush=True)
        if label.startswith("B1"):
            print(f"      gassed decisions: {MedianRule.counts}", flush=True)
        if label.startswith("B2"):
            print(f"      decisions: {Planner.counts}", flush=True)


if __name__ == "__main__":
    main()
