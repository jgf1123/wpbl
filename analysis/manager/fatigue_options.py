"""How strong should fading be? Three spacings of the fatigue columns, compared.

    pixi run python analysis/manager/fatigue_options.py [--series 100]

The game's fresh -> fading step is +0.018 runs per plate appearance; the paired
measurement it rests on is +0.078 (an upper bound), the times-seen design +0.048
(dice_game_spec.md 7.2-7.4). Today fading is one G3 shift from fresh and gassed
one more beyond it (`dice.FATIGUE` 0 / 1 / 2). Options, gassed always one shift
beyond fading:

  current   fading 1
  middle    the spacing whose fresh -> fading step is nearest +0.048
  full      the spacing whose step is nearest +0.078

For each: the step (as rules_check computes it), the league card's columns and
the extremes across pitchers; then cards built in a scratch folder (data/dice is
not touched) and 2,400 seeded series with the conventions on -- B0 against B0
(runs a team-game, plate appearances by column), a careless manager (worst arm,
never gassed) against B0, and B2 against B0.
"""
import argparse
import contextlib
import io
import tempfile
import time
import zlib
from pathlib import Path

import numpy as np

from wpbl import dice, engine, manager as M, play, play_wp, usage

TEAMS = ["BOS", "LAQ", "NYH", "SFF"]


def step(fading):
    """fresh -> fading and fading -> gassed, runs per plate appearance, as rules_check."""
    saved = dict(dice.FATIGUE)
    dice.FATIGUE.update({"fresh": 0.0, "fading": fading, "gassed": fading + 1.0})
    try:
        P = dice.cards("P")
        w = dice.line_weights()
        cc = dice.column_cells(P.to_numpy(), centred=True)
        pa = dice.plate_appearances()
        use = pa.groupby("P").size().reindex(P.index).fillna(0).to_numpy(float)
        use /= use.sum()
        v = {k: float(((cc[k] * w).sum(axis=1) / 100.0 * use).sum()) for k in cc}
        lines = list(dice.TREE_LINES)
        ext = {k: (cc[k][:, lines.index("K")].min(), cc[k][:, lines.index("HR")].max(),
                   cc[k][:, lines.index("HBP")].max()) for k in cc}
        return v["fading"] - v["fresh"], v["gassed"] - v["fading"], ext
    finally:
        dice.FATIGUE.clear()
        dice.FATIGUE.update(saved)


def nearest(target, grid):
    return min(grid, key=lambda s: abs(step(s)[0] - target))


def build(fading, where):
    saved_f, saved_out = dict(dice.FATIGUE), dice.OUT_DIR
    dice.FATIGUE.update({"fresh": 0.0, "fading": fading, "gassed": fading + 1.0})
    dice.OUT_DIR = where
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            dice.main()
    finally:
        dice.FATIGUE.clear()
        dice.FATIGUE.update(saved_f)
        dice.OUT_DIR = saved_out


class WorstArm(M.Policy):
    def decide(self, g, side):
        if g.column(side.pitcher) != "gassed":
            return "keep"
        opts = M.options(g, side, self.model)
        if not opts:
            return "keep"
        cards = self.model.cards

        def entering(o):
            return engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0]))
        pool = [o for o in opts if entering(o) != "gassed"] or opts
        o = max(pool, key=lambda o: self.model.runs_per_inning(o[0], entering(o)))
        return o[0] if o[1] is None else (o[0], M.lineup_text(o[1]))


def run(model, make, n):
    won = total = 0
    runs, cols = [], {"fresh": 0, "fading": 0, "gassed": 0}

    def record(g, info):
        for side in (g.away, g.home):
            runs.append(side.runs)
        for e in g.events:
            if e["event"] == "pa":
                cols[e["column"]] += 1

    for me in TEAMS:
        for opp in TEAMS:
            if me == opp:
                continue
            for hi_me in (True, False):
                hi, lo = (me, opp) if hi_me else (opp, me)
                for k in range(n):
                    pol = {me: make(model, me), opp: M.Baseline(model, opp)}
                    w, _ = M.series(model, hi, lo, pol, M.FINAL,
                                    zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()), record=record)
                    won += w == me
                    total += 1
    p = won / total
    s = sum(cols.values())
    return p, np.sqrt(p * (1 - p) / total), np.mean(runs), {k: v / s for k, v in cols.items()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=100)
    a = ap.parse_args()
    grid = [round(x, 2) for x in np.arange(1.0, 6.01, 0.1)]
    options = {"current": 1.0, "middle": nearest(0.048, grid), "full": nearest(0.078, grid)}
    print("spacing: fading = s G3 shifts from fresh, gassed = s + 1\n")
    lg = dice.cards("P")
    print(f"{'option':8s} {'s':>5s} {'fresh->fading':>14s} {'fading->gassed':>15s}   extremes across pitchers "
          "(fewest K cells / most HR / most HBP, of 33): fresh | fading | gassed")
    for name, s in options.items():
        a1, a2, ext = step(s)
        e = " | ".join(f"{int(ext[k][0])}/{int(ext[k][1])}/{int(ext[k][2])}" for k in ("fresh", "fading", "gassed"))
        print(f"{name:8s} {s:5.1f} {a1:+14.3f} {a2:+15.3f}   {e}", flush=True)

    root = Path(tempfile.mkdtemp(prefix="fatigue_options_"))
    for name, s in options.items():
        where = root / name
        where.mkdir()
        build(s, where)
        cards = play.Cards(where)
        wp = play_wp.WinProbability(play_wp.league_table(where))
        model = M.Model(cards, wp)
        model.usage = usage.Usage(cards)
        lgc = [r for r in (where / "cards_league.csv").read_text(encoding="utf-8").splitlines()
               if r.startswith("League average pitcher")]
        print(f"\n== {name} (s = {s}): league pitcher card, cells K/BB/HBP/HR/1B/OUT by column")
        for r in lgc:
            f = r.split(",")
            print(f"   {f[3]:12s} K {f[13]:>2s}  BB {f[15]:>2s}  HBP {f[17]:>2s}  HR {f[19]:>2s}  "
                  f"1B {f[21]:>2s}  OUT {f[23]:>2s}")
        t0 = time.time()
        for label, make in (("B0 vs B0", lambda m, t: M.Baseline(m, t)),
                            ("careless vs B0", lambda m, t: WorstArm(m, t)),
                            ("B2 vs B0", lambda m, t: M.Planner(m, t))):
            p, se, rpg, cols = run(model, make, a.series)
            print(f"   {label:15s} series won {100 * p:5.1f}% +/- {100 * se:.1f}   runs a team-game {rpg:.2f}   "
                  f"PAs fresh/fading/gassed {100 * cols['fresh']:.0f}/{100 * cols['fading']:.0f}/"
                  f"{100 * cols['gassed']:.1f}%   ({time.time() - t0:.0f}s)", flush=True)


if __name__ == "__main__":
    main()
