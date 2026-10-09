"""Team-neutral win probability for the dice game (tosw_play_spec.md section 6).

The league-average batter against the league-average pitcher, played by the
game's own rules, and solved exactly rather than sampled:

1. one plate appearance from every (outs, bases), every d100 face and every d12
   face enumerated through the same `engine.apply_line` the game uses;
2. the distribution of runs to the end of the half-inning from every state,
   one linear solve per run total;
3. backward induction over half-innings by run difference, with extra innings
   solved in closed form because every extra inning is the same.

Steals are left out: the steal rule is decided by this win probability, so
putting them in would make the model depend on itself.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from wpbl import engine

DICE_DIR = Path(__file__).resolve().parents[2] / "data" / "dice"
MAX_RUNS = 40            # runs in one half-inning; the tail past this is negligible
DECIDED = 30             # a lead this big is treated as won
EMPTY, ON_2ND = (False, False, False), (False, True, False)


def parse_range(text) -> list[int]:
    """'45-69' -> 45..69, '99' -> [99], blank or '-' -> []."""
    if not isinstance(text, str) or text.strip() in ("", "-"):
        return []
    lo, _, hi = text.strip().partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def faces(row: pd.Series, lines, prefix: str, span: range) -> np.ndarray:
    """The printed card as one label per d100 face across `span`."""
    out = np.empty(len(span), object)
    seen = []
    for line in lines:
        for f in parse_range(row[f"{prefix}{line}"]):
            out[f - span.start] = line
            seen.append(f)
    if sorted(seen) != list(span):
        raise ValueError(f"{row['player']}: card does not cover {span.start}-{span.stop - 1}")
    return out


CARD_LINES = ("OUT", "K", "HBP", "BB", "1B", "HR")
P_SPAN, B_SPAN = range(0, engine.RUN_START), range(engine.BAT_START, 100)


def league_table() -> engine.Table:
    """League batter against the league pitcher's season card (no fatigue column)."""
    lg = pd.read_csv(DICE_DIR / "cards_league.csv", comment="#", dtype=str)
    pitcher = lg[(lg["player"] == "League average pitcher") & (lg["column"] == "season card")]
    batter = lg[lg["player"] == "League average batter"]
    p = faces(pitcher.iloc[0], CARD_LINES, "", P_SPAN)
    b = faces(batter.iloc[0], CARD_LINES, "", B_SPAN)
    return engine.Table.from_lines(p, b)


class FixedDie:
    """Stands in for the game's dice, returning one chosen d12 face (0-11)."""

    def __init__(self, face):
        self.face = face

    def integers(self, lo, hi):
        return lo + self.face


def state_index(outs, bases):
    return outs * 8 + bases[0] + 2 * bases[1] + 4 * bases[2]


STATES = [(o, (bool(b & 1), bool(b & 2), bool(b & 4))) for o in range(3) for b in range(8)]


def transitions(table: engine.Table):
    """Every (state, probability, next state or None for the third out, runs).

    A running play is its own transition, and its runs are banked: they stand
    even if the plate appearance then ends the inning. Runs on the play that
    makes the third out do not count, as in `engine.half_inning`.
    """
    out = []
    for outs, bases in STATES:
        for face in range(100):
            line = table.read(face)
            if line == "RUN":
                b, r = engine.advance_all(bases) if any(bases) else (bases, 0)
                out.append((outs, bases, 0.01, (outs, b), r))
                continue
            dice = range(12) if line in ("1B", "OUT") else [0]
            for d in dice:
                b, made, r = engine.apply_line(line, bases, outs, FixedDie(d))
                nxt = None if outs + made >= 3 else (outs + made, b)
                out.append((outs, bases, 0.01 / len(dice), nxt, 0 if nxt is None else r))
    return out


def run_distributions(table: engine.Table) -> np.ndarray:
    """D[state, k]: probability of exactly k more runs this half-inning."""
    n = len(STATES)
    T = np.zeros((MAX_RUNS, n, n))
    end = np.zeros(n)
    for outs, bases, p, nxt, r in transitions(table):
        i = state_index(outs, bases)
        if nxt is None:
            end[i] += p
        else:
            T[min(r, MAX_RUNS - 1), i, state_index(*nxt)] += p
    solve = np.linalg.inv(np.eye(n) - T[0])
    D = np.zeros((n, MAX_RUNS))
    for k in range(MAX_RUNS):
        rhs = end * (k == 0)
        for r in range(1, k + 1):
            rhs = rhs + T[r] @ D[:, k - r]
        D[:, k] = solve @ rhs
    return D


class WinProbability:
    """P(home wins) from any point in the game, for league-average teams."""

    def __init__(self, table: engine.Table | None = None):
        self.D = run_distributions(table or league_table())
        start, extra = self.dist(0, EMPTY), self.dist(0, ON_2ND)
        cdf_above = 1 - np.cumsum(extra)                  # P(home scores > a)
        win = float(extra @ cdf_above)
        tie = float(extra @ extra)
        self.extra = win / (1 - tie)                      # tied, start of an extra inning
        self._start = start
        self.top = lru_cache(None)(self._top)
        self.bottom = lru_cache(None)(self._bottom)

    def dist(self, outs, bases):
        return self.D[state_index(outs, tuple(bool(x) for x in bases))]

    def half_dist(self, inning):
        return self._start if inning <= engine.INNINGS else self.dist(0, ON_2ND)

    def ended(self, d):
        """After a bottom half in the 7th or later."""
        return 1.0 if d > 0 else 0.0 if d < 0 else self.extra

    def after_top(self, inning, d):
        if inning >= engine.INNINGS and d > 0:
            return 1.0                                    # home does not bat
        return self.bottom(min(inning, engine.INNINGS + 1), d)

    def after_bottom(self, inning, d):
        if inning >= engine.INNINGS:
            return self.ended(d)
        return self.top(inning + 1, d)

    def _top(self, inning, d):
        """Start of the top of `inning`, home leading by d."""
        if abs(d) > DECIDED:
            return float(d > 0)
        D = self.half_dist(inning)
        return float(sum(D[k] * self.after_top(inning, d - k) for k in range(MAX_RUNS)))

    def _bottom(self, inning, d):
        if abs(d) > DECIDED:
            return float(d > 0)
        D = self.half_dist(inning)
        return float(sum(D[k] * self.after_bottom(inning, d + k) for k in range(MAX_RUNS)))

    def mid(self, inning, half, outs, bases, d):
        """Before a plate appearance: `half` is 'top' or 'bottom', d is home minus away."""
        inning = min(inning, engine.INNINGS + 1)
        if outs >= 3:
            return self.after_top(inning, d) if half == "top" else self.after_bottom(inning, d)
        D = self.dist(outs, bases)
        if half == "top":
            return float(sum(D[k] * self.after_top(inning, d - k) for k in range(MAX_RUNS)))
        return float(sum(D[k] * self.after_bottom(inning, d + k) for k in range(MAX_RUNS)))


if __name__ == "__main__":
    wp = WinProbability()
    print(f"start of game {wp.top(1, 0):.4f}   tied extra inning {wp.extra:.4f}")
    print("runs per half-inning", float(wp._start @ np.arange(MAX_RUNS)))
