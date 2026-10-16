"""Does the series planner's plan win in the dice game? (user, 2026-10-14)

    pixi run python analysis/manager/plan_test.py [--series 100]

series_plan.py plans a team's pitching in expected values and claims a large edge
over B2's habits. This plays that plan with the game's dice. For each team, a plan
for a best-of-5 final (16, 17, 19, 20, 22 Sep, every arm rested, as the 9 Sep chart
recovers by the 16th), found by series_plan.search. The plan-following manager:

  starter   the plan's starter for the date, for her planned innings (B2's starter
            rule if she would take the mound gassed)
  relief    at the start of each half-inning once her planned innings or stint are
            done, or as soon as the pitcher is gassed: the planner's in-game table
            (relief_dp), read with the real stakes band of the moment (the run-value
            index now, in that inning's bands) and the planned arms still available;
            one inning or two as the table says. Any legal arm when the table's arm
            cannot come in.

Each team plays the plan against B2 (manager.Planner, as it now stands) in every
pairing and on both sides; the control is B2 against B2 on the same seeds.
"""
import argparse
import datetime as dt
import time
import zlib
from collections import Counter, defaultdict

import numpy as np

from wpbl import engine, manager as M, play, postseason as P, usage
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("series_plan", Path(__file__).with_name("series_plan.py"))
SP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SP)

TEAMS = ["SFF", "NYH", "LAQ", "BOS"]
DATES = [P.D(16), P.D(17), P.D(19), P.D(20), P.D(22)]
DECISIONS = Counter()          # how the plan manager chose: from its table, or a fallback


class PlanManager(M.Policy):
    def __init__(self, model, team, staff, stakes, starter, s_inn, cost, fatigue):
        super().__init__(model, team)
        self.staff, self.stakes = staff, stakes
        self.starter = starter
        self.s_got, _, _ = stakes.starter_value(staff, starter, engine.enter(fatigue[starter]), s_inn)
        entering = {n: engine.enter(fatigue[n]) for n in staff.arms if n != starter}
        self.arms, self.slots, self.act = SP.relief_dp(staff, stakes, self.s_got, entering, cost, policy=True)
        self.entry, self.length = 1, None

    def decide(self, g, side):
        p = side.pitcher
        gassed = g.column(p) == "gassed"
        if p == self.starter:
            over = g.at_half_start and g.inning > self.s_got + 1e-9
        else:
            over = g.at_half_start and self.length is not None and g.inning >= self.entry + self.length
        if not (gassed or over):
            return "keep"
        cards = self.model.cards
        opts = {}
        for o in M.options(g, side, self.model):
            if engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0])) != "gassed":
                opts.setdefault(o[0], o)
        if not opts:
            DECISIONS["nobody available"] += 1
            return "keep"
        name, length = None, 1
        k = next((i for i, (inn, _) in enumerate(self.slots) if inn == g.inning), None)
        if k is not None and self.act is not None:
            rv = self.model.run_value(g.inning, g.top, g.outs, [b is not None for b in g.bases],
                                      g.home.runs - g.away.runs)
            band = int(np.searchsorted(self.stakes.edges[min(g.inning, engine.INNINGS)], rv, side="left"))
            mask = sum(1 << i for i, n in enumerate(self.arms) if n in opts)
            a = int(self.act[k, mask, band])
            if a >= 0:
                name, length = self.arms[a // 2], 1 + a % 2
        if name is None or name not in opts:
            name = min(opts, key=lambda n: self.model.runs_per_inning(
                n, engine.column_for(engine.enter(g.fatigue[n]), cards.stamina(n))))
            DECISIONS["fallback (table arm unavailable or no slot)"] += 1
            length = 1
        else:
            DECISIONS["planner table"] += 1
        self.entry, self.length = g.inning, length
        o = opts[name]
        return name if o[1] is None else (name, M.lineup_text(o[1]))


def make_plans(model, stakes, restarts, rng):
    weights = SP.coin_weights(3, len(DATES))
    sched = list(zip(DATES, weights))
    plans = {}
    for team in TEAMS:
        staff = SP.Staff(model, team)
        start = {n: engine.RESTED for n in staff.arms}
        base = SP.b2_like(staff, stakes, sched, start, model)
        best_val, best, best_cost = SP.search(staff, stakes, sched, start, base, {})
        for _ in range(restarts):
            good = sorted(staff.arms, key=lambda n: staff.q[n]["rd"])[:6]
            init = [(rng.choice(good), int(rng.choice(SP.STARTER_INNINGS))) for _ in sched]
            c0 = {n: float(rng.choice(SP.PITCH_COSTS)) for n in staff.arms}
            v, p_, c = SP.search(staff, stakes, sched, start, init, c0)
            if v < best_val:
                best_val, best, best_cost = v, p_, c
        plans[team] = (staff, dict(zip(DATES, best)), best_cost)
        print(f"  plan {team}: " + ", ".join(f"{d:%d} {s.split()[-1]} {k}" for d, (s, k) in zip(DATES, best)),
              flush=True)
    return plans


def run_series(model, stakes, x, y, plan_team, plans, seed, stats):
    """One best-of-5 final, x hosting games 1, 2 and 5. Returns the winner."""
    rng = np.random.default_rng(seed)
    series = P.final(x, y)
    fatigue = {n: engine.RESTED for n in model.cards.pitcher}
    today = {"date": None}
    orig_start, orig_mgr = M.usage_starter_step, P.manager_for

    def starter_step(model_, team, fat):
        if team == plan_team:
            staff, plan, _ = plans[team]
            s, _ = plan[today["date"]]
            if engine.enter(fat[s]) < model_.cards.stamina(s):
                return s, 0
        return orig_start(model_, team, fat)

    def manager_for(model_, team, series_, date, fat, starter, explain):
        if team == plan_team:
            staff, plan, cost = plans[team]
            s, k = plan[date]
            return PlanManager(model_, team, staff, stakes, starter, k if starter == s else 7, cost, fat)
        return orig_mgr(model_, team, series_, date, fat, starter, explain)

    M.usage_starter_step, P.manager_for = starter_step, manager_for
    try:
        day = DATES[0]
        while series.winner is None:
            home = series.due(day)
            if home is not None:
                today["date"] = day
                g, lineups, _ = P.play_game(model, series, day, home, fatigue, rng)
                for t in series.teams:
                    for n in model.cards.team_pitchers(t):
                        fatigue[n] = g.fatigue[n]
                    if t == plan_team and stats is not None:
                        st = lineups[t]["pitcher"]
                        stats["starter BF"].append(g.stats[st]["BF"])
                        stats["arms"].append(sum(1 for s in g.stats.values() if s["team"] == t))
                        side = g.home if g.home.team == t else g.away
                        other = g.away if side is g.home else g.home
                        stats["runs allowed"].append(other.runs)
                win = g.home.team if g.home.runs > g.away.runs else g.away.team
                series.wins[win] += 1
                series.played += 1
                if series.wins[win] == series.need:
                    series.winner = win
            day += dt.timedelta(days=1)
            fatigue = {n: engine.recover(c, 1) for n, c in fatigue.items()}
    finally:
        M.usage_starter_step, P.manager_for = orig_start, orig_mgr
    return series.winner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=100, help="series per (pairing, side)")
    ap.add_argument("--restarts", type=int, default=2)
    a = ap.parse_args()
    cards, wp = play.shared()
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    model.run_value(1, True, 0, (False, False, False), 0)
    stakes = SP.Stakes(model)
    t0 = time.time()
    print("plans for a best-of-5 final, everyone rested:")
    plans = make_plans(model, stakes, a.restarts, np.random.default_rng(20261014))
    res = {"plan": defaultdict(lambda: [0, 0]), "control": defaultdict(lambda: [0, 0])}
    stats = {k: defaultdict(list) for k in res}
    for x in TEAMS:
        for y in TEAMS:
            if x == y:
                continue
            for side in (x, y):
                for i in range(a.series):
                    seed = zlib.crc32(f"{x}{y}{side}{i}".encode())
                    for label, pt in (("plan", side), ("control", None)):
                        w = run_series(model, stakes, x, y, pt, plans, seed,
                                       stats[label] if pt else None)
                        r = res[label][side]
                        r[0] += w == side
                        r[1] += 1
        print(f"  {x} hosting done, {time.time() - t0:.0f}s", flush=True)
    print("\nseries won by the team named (best of 5, 100 per pairing and side):")
    for t in TEAMS:
        pw, pn = res["plan"][t]
        cw, cn = res["control"][t]
        print(f"  {t}: with its plan {100 * pw / pn:.1f}%  |  as B2 (same seeds) {100 * cw / cn:.1f}%  "
              f"(n {pn})")
    pw = sum(v[0] for v in res["plan"].values()); pn = sum(v[1] for v in res["plan"].values())
    cw = sum(v[0] for v in res["control"].values()); cn = sum(v[1] for v in res["control"].values())
    se = 100 * np.sqrt(0.25 / pn)
    print(f"  all: plan {100 * pw / pn:.1f}% vs control {100 * cw / cn:.1f}% (+/- {se:.1f} each)")
    s = stats["plan"]
    print(f"\nplan teams' games: starter BF {np.mean(s['starter BF']):.1f}, arms {np.mean(s['arms']):.2f}, "
          f"runs allowed {np.mean(s['runs allowed']):.2f}")
    print("plan manager's choices:", dict(DECISIONS))


if __name__ == "__main__":
    main()
