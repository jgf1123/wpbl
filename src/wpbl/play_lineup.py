"""Suggest a batting order for the nine names in a game file's lineup.

    pixi run play suggest <game.md> [--team SFF] [--write]

For each team whose `order` has nine names, this finds the order with the most
expected runs over seven innings, every batter facing the league-average
pitcher's season card, by the dice game's own rules (engine.apply_line, the
d12 enumerated, running plays at 6 in 100). Expected runs are solved exactly
over (outs, bases, batting slot), so the slot carries from inning to inning.

Left out: steals (the green light depends on the game state, not on the order)
and fielding (positions do not change with the order). So it ranks bats only.

The search is local: swap and move-one-batter steps, run to a standstill from
the file's own order and from 40 seeded random orders. It reports how many of
those starts reached the best order, which is the evidence that the search found
the best one. The difference between good orders is usually a few hundredths of
a run a game.

--write puts the suggested order into the setup block, which is allowed only
before the game has started.
"""
from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from wpbl import engine
from wpbl.play_wp import STATES, FixedDie, league_table, state_index

INNINGS = engine.INNINGS
EMPTY = state_index(0, (False, False, False))
RESTARTS = 40


def batter_blocks(p_line, b_line):
    """One batter against the pitcher, per roll, over the 24 base-out states.

    stay  [24x24]  a running play: same batter, runners moved
    next  [24x24]  the plate appearance ended and the inning goes on
    runs  [24]     expected runs per roll (a running play's runs stand; runs on
                   the third out do not count)
    end   [24]     probability the roll makes the third out
    """
    table = engine.Table.from_lines(p_line, b_line)
    stay, nxt = np.zeros((24, 24)), np.zeros((24, 24))
    runs, end = np.zeros(24), np.zeros(24)
    for outs, bases in STATES:
        i = state_index(outs, bases)
        for face in range(100):
            line = table.read(face)
            if line == "RUN":
                b, r = engine.advance_all(bases) if any(bases) else (bases, 0)
                stay[i, state_index(outs, b)] += 0.01
                runs[i] += 0.01 * r
                continue
            dies = range(12) if line in ("1B", "OUT") else [0]
            for d in dies:
                q = 0.01 / len(dies)
                b, made, r = engine.apply_line(line, bases, outs, FixedDie(d))
                if outs + made >= 3:
                    end[i] += q
                else:
                    nxt[i, state_index(outs + made, b)] += q
                    runs[i] += q * r
    return stay, nxt, runs, end


def expected_runs(blocks, order):
    """Expected runs over seven innings, the first batter leading off the 1st."""
    n = len(order)
    Q = np.zeros((24 * n, 24 * n))
    r = np.zeros(24 * n)
    E = np.zeros((24 * n, n))                  # third out made -> next leadoff slot
    for k, b in enumerate(order):
        stay, nxt, runs, end = blocks[b]
        s, t = slice(24 * k, 24 * k + 24), slice(24 * ((k + 1) % n), 24 * ((k + 1) % n) + 24)
        Q[s, s] += stay
        Q[s, t] += nxt
        r[s] = runs
        E[s, (k + 1) % n] = end
    sol = np.linalg.solve(np.eye(24 * n) - Q, np.column_stack([r, E]))
    half_runs = sol[EMPTY::24, 0]              # by leadoff slot
    lead_next = sol[EMPTY::24, 1:]             # leadoff slot -> next inning's
    lead = np.zeros(n)
    lead[0] = 1.0
    total = 0.0
    for _ in range(INNINGS):
        total += lead @ half_runs
        lead = lead @ lead_next
    return float(total)


def local_best(blocks, start, cache):
    def score(o):
        key = tuple(o)
        if key not in cache:
            cache[key] = expected_runs(blocks, key)
        return cache[key]

    order, best = list(start), score(start)
    while True:
        moves = []
        for i in range(9):
            for j in range(9):
                if i == j:
                    continue
                if i < j:
                    sw = order.copy()
                    sw[i], sw[j] = sw[j], sw[i]
                    moves.append(sw)
                mv = order.copy()
                mv.insert(j, mv.pop(i))
                moves.append(mv)
        cand = max(moves, key=score)
        if score(cand) <= best + 1e-12:
            return tuple(order), best
        order, best = cand, score(cand)


def suggest(cards, side_order, seed=0):
    """side_order: the file's nine names. Returns (best, runs, file runs, hits, ranked)."""
    p_line = league_table().p_line
    blocks = {n: batter_blocks(p_line, cards.bat_faces[n]) for n in side_order}
    cache = {}
    rng = np.random.default_rng(seed)
    starts = [list(side_order)] + [list(rng.permutation(side_order)) for _ in range(RESTARTS)]
    found = [local_best(blocks, s, cache) for s in starts]
    best, runs = max(found, key=lambda x: x[1])
    hits = sum(abs(r - runs) < 1e-9 for _, r in found)
    ranked = sorted(cache.items(), key=lambda x: -x[1])     # every order the search scored
    return best, runs, cache[tuple(side_order)], hits, len(starts), ranked


def write_order(path, text, team, entries):
    body = "order = [\n" + "".join(f'  "{e}",\n' for e in entries) + "]"
    pat = re.compile(rf"(\[lineup\.{re.escape(team)}\][^\[]*?)order\s*=\s*\[.*?\n\]", re.S)
    new, n = pat.subn(lambda m: m.group(1) + body, text, count=1)
    if n != 1:
        raise ValueError(f"could not find [lineup.{team}] order in {path}")
    Path(path).write_text(new, encoding="utf-8", newline="\n")
    return new
