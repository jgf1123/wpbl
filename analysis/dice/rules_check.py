"""Play `dice_rules.md` as written, and check it matches the engine exactly.

    pixi run python analysis/dice/rules_check.py

The rulebook is a SEPARATE statement of the same mechanics, written for a player
rather than derived from the code, so the two can drift apart silently: a d12
band edited in one and not the other changes the game without failing anything.
This re-implements the rules from the printed text and compares every line
against `engine.apply_line` over every base state, out count and d12 face --
720 combinations. Change either side and this is what catches it.
"""
import itertools
import numpy as np

from wpbl import engine


class FixedDie:
    """Stands in for rng, returning a chosen d12 face."""

    def __init__(self, face):
        self.face = face

    def integers(self, lo, hi=None):
        if hi is None:
            lo, hi = 0, lo
        if (lo, hi) == (1, 13):        # SINGLE_D12 draws 1..12
            return self.face
        if (lo, hi) == (0, 12):        # out flavour draws 0..11
            return self.face - 1
        raise AssertionError((lo, hi))


def rulebook(line, bases, outs, d12):
    """The rules exactly as dice_rules.md states them."""
    on1, on2, on3 = bases

    if line == "K":
        return bases, 1, 0

    if line in ("BB", "HBP"):
        # batter to 1st, forced runners advance one
        if on1 and on2 and on3:
            return (True, True, True), 0, 1
        if on1 and on2:
            return (True, True, True), 0, 0
        if on1:
            return (True, True, on3), 0, 0
        return (True, on2, on3), 0, 0

    if line == "HR":
        return (False, False, False), 0, 1 + sum(bases)

    if line == "2B":
        # batter to 2nd; runners from 2nd and 3rd score; runner from 1st to 3rd
        return (False, True, on1), 0, int(on2) + int(on3)

    if line == "ROE":
        # batter to 1st; every runner advances one
        return (True, on1, on2), 0, int(on3)

    if line == "1B":
        scores_from_2nd, to_3rd_from_1st = ((8, 11) if outs < 2 else (5, 10))
        scored = d12 >= scores_from_2nd
        plus = d12 >= to_3rd_from_1st
        runs = int(on3) + int(on2 and scored)          # 3rd always scores
        third = (on2 and not scored) or (on1 and plus)  # otherwise advance one
        second = on1 and not plus
        return (True, bool(second), bool(third)), 0, runs

    if line == "OUT":
        if on1:
            flavour = ("B" if d12 <= 6 else "B+" if d12 <= 8
                       else "F+" if d12 <= 10 else "FB+")
        else:
            flavour = "B" if d12 <= 5 else "B+"
        plus = flavour.endswith("+")
        if flavour == "B":
            return bases, 1, 0                          # runners hold
        if flavour == "B+":                             # every runner advances one
            return (False, on1, on2), 1, int(on3)
        if flavour == "F+":
            # runner from 1st out, batter to 1st, every OTHER runner advances one
            return (True, False, on2), 1, int(on3)
        if flavour == "FB+":
            # batter and runner from 1st both out, others advance one
            return (False, False, on2), 2, int(on3)
    raise ValueError(line)


bad = 0
checked = 0
for line in ("K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"):
    for bits in itertools.product((False, True), repeat=3):
        for outs in (0, 1, 2):
            faces = range(1, 13) if line in ("1B", "OUT") else (1,)
            for d in faces:
                got = rulebook(line, bits, outs, d)
                want = engine.apply_line(line, bits, outs, FixedDie(d))
                checked += 1
                if got != want:
                    bad += 1
                    if bad <= 12:
                        print(f"  MISMATCH {line} bases={bits} outs={outs} d12={d}")
                        print(f"     rulebook {got}")
                        print(f"     engine   {want}")
print(f"\n{checked} combinations checked, {bad} mismatches")
