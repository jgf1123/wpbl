"""An oracle for pitcher usage: the best a manager who knew the future could do.

    pixi run python analysis/manager/oracle.py [--teams NYH] [--samples 40]

User (2026-10-14): not a plan to follow, but an upper bound and a teacher. A
warm-up costs 30 pitches, so long stints are efficient -- a durable arm turns one
warm-up into 80-100 useful pitches; a good arm is worth most in the half-innings
that matter. An oracle that sees how each game will go can schedule stints to get
both. What it does tells us how much better than today's managers is possible,
how high the stakes must be before the ace is worth spending (and how that moves
with her fatigue and the series), and how load should spread over the staff.
There are no starters or relievers here, only stints: if a starter shape and a
reliever shape come out anyway, they are real for this game.

A sampled postseason, for one team: its 8 dates (semifinal, then final, the final
as if the semifinal went three games), each game weighted by its series leverage
times the chance it is played (series_plan.coin_weights). Each date draws one real
2026 team-game at random: the run-value index at the start of each half-inning
that team fielded (half_inning_starts), innings 1-7 -- the stakes, KNOWN to the
oracle and held fixed (a good pitcher keeping a game close is not credited: an
optimism, fine for a bound). Counts start from the 9 Sep chart and recover 20 a
day to the floor of -30; disfavored pitchers are left out.

One game: the half-innings are split into unbroken stints, at most one per arm,
changes only between half-innings (user). A stint costs, for each inning, the
stakes x her runs that inning (fresh below 20, fading to her stamina, gassed past
it; her card's runs and pitches per inning in each column), and puts 30 + her
pitches on her count. Solved exactly by a dynamic program over (inning, arms used).

Across games: each arm has a price per pitch, the stand-in for "she is needed
later". For given prices the games are solved in order, fatigue carried; the
prices are searched with the whole postseason in view (the second piece of
foresight). Score: the leverage-weighted sum of stakes x runs -- weighted runs.

Compared, on the same sampled postseasons:
  B0-like        the shared starter rule (usage_starter_step); each arm pitches
                 until the inning she would start gassed; then the best rested
                 arm by her column's runs per inning, role starters held back
  myopic oracle  hindsight inside each game, no price on later games
  oracle         both pieces of hindsight
"""
import argparse
import importlib.util
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from wpbl import engine, manager as M, play, postseason as P, usage
from wpbl.leverage import half_inning_starts

spec = importlib.util.spec_from_file_location("series_plan", Path(__file__).with_name("series_plan.py"))
SP = importlib.util.module_from_spec(spec)
spec.loader.exec_module(SP)

INN = engine.INNINGS
PRICES = (0.0, 0.002, 0.004, 0.008, 0.016, 0.032)     # weighted runs per pitch
NO_GASSED_START = True      # an arm may not start a half-inning gassed (--allow-gassed lifts it)
GASSED_START = 2.5          # runs an inning charged when she must anyway: nobody else is left
B0_TIMING = False           # --b0-timing: every stint runs until she would start an inning gassed


def stake_paths(model):
    """Each real 2026 team-game's stakes, the half-innings that team fielded."""
    st = half_inning_starts()
    st = st[st["inning"] <= INN]
    rv = [model.run_value(r.inning, r.half == "top", 0, (False, False, False), int(r.diff))
          for r in st.itertuples()]
    st = st.assign(rv=rv).sort_values(["game_id", "inning"])
    return [g["rv"].to_numpy() for _, g in st.groupby(["game_id", "pitching_team_id"])]


class Arms:
    def __init__(self, model, team):
        cards = model.cards
        self.names = [n for n in M.arms(model, team) if n in cards.pitcher]
        self.S = np.array([cards.stamina(n) for n in self.names], float)
        cols = ("fresh", "fading", "gassed")
        self.r = np.array([[model.runs_per_inning(n, c) for c in cols] for n in self.names])
        self.p = np.array([[model.pitches_per_inning(n, c) for c in cols] for n in self.names])

    def inning(self, i, c):
        """(runs, pitches) for one inning from count c, split across column lines."""
        runs = pitches = 0.0
        left = 1.0
        while left > 1e-9:
            col = 0 if c < engine.FRESH_UNTIL else (1 if c < self.S[i] else 2)
            edge = engine.FRESH_UNTIL if col == 0 else (self.S[i] if col == 1 else np.inf)
            p = self.p[i, col]
            use = min(left, (edge - c) / p) if np.isfinite(edge) else left
            runs += use * self.r[i, col]
            pitches += use * p
            c += use * p
            left -= use
        return runs, pitches


def stint_table(arms, entering, stakes):
    """cost[i, h, e] = stakes-weighted runs for arm i pitching halves h..e-1, and
    pitches[i, h, e] (warm-up included), from her entering count. With
    NO_GASSED_START, an inning she would start gassed costs GASSED_START runs."""
    R, H = len(arms.names), len(stakes)
    cost = np.full((R, H + 1, H + 1), np.inf)
    pitches = np.zeros((R, H + 1, H + 1))
    for i in range(R):
        for h in range(H):
            c, w, p = entering[i], 0.0, 30.0
            for e in range(h + 1, H + 1):
                r, q = arms.inning(i, c)
                if NO_GASSED_START and c >= arms.S[i]:
                    r = GASSED_START
                w += stakes[e - 1] * r
                p += q
                c += q
                cost[i, h, e], pitches[i, h, e] = w, p
    return cost, pitches


def solve_game(arms, entering, stakes, price):
    """Best split of one game into stints, given the stakes and a price per pitch
    for each arm. Returns (weighted runs, [(arm, first half, last half + 1)],
    pitches each arm adds)."""
    R, H = len(arms.names), len(stakes)
    cost, pitches = stint_table(arms, entering, stakes)
    obj = cost + price[:, None, None] * pitches
    if B0_TIMING:                      # only the stint that ends where B0's would
        for i in range(R):
            for h in range(H):
                c = entering[i]
                end = H
                for e in range(h + 1, H):
                    c += arms.inning(i, c)[1]
                    if c >= arms.S[i]:
                        end = e
                        break
                keep, last = obj[i, h, end], obj[i, h, H]
                obj[i, h, :] = np.inf
                obj[i, h, end] = keep
                obj[i, h, H] = last        # or left in to finish: nobody else may be left
    M_ = 1 << R
    V = np.full((H + 1, M_), np.inf)
    V[H] = 0.0
    choice = {}
    masks = np.arange(M_)
    for h in range(H - 1, -1, -1):
        best = np.full(M_, np.inf)
        arg = np.full((M_, 2), -1)
        for i in range(R):
            free = masks[((masks >> i) & 1) == 0]
            for e in range(h + 1, H + 1):
                val = obj[i, h, e] + V[e][free | (1 << i)]
                better = val < best[free]
                best[free] = np.where(better, val, best[free])
                arg[free[better]] = (i, e)
        V[h] = best
        choice[h] = arg
    stints, mask, h = [], 0, 0
    while h < H:
        i, e = choice[h][mask]
        stints.append((int(i), h, int(e)))
        mask |= 1 << int(i)
        h = int(e)
    runs = sum(cost[i, h, e] for i, h, e in stints)
    add = np.zeros(R)
    for i, h, e in stints:
        add[i] = pitches[i, h, e]
    return runs, stints, add


def run_postseason(arms, sched, start, paths, price):
    counts, prev = start.copy(), sched[0][0]
    total, games = 0.0, []
    for (day, weight), stakes in zip(sched, paths):
        counts = np.maximum(engine.RESTED, counts - engine.RECOVERY * (day - prev).days)
        prev = day
        entering = counts + engine.ENTRY_COST
        runs, stints, add = solve_game(arms, entering, stakes, price)
        total += weight * runs
        games.append((weight, stakes, entering.copy(), stints, add.copy()))
        counts = np.where(add > 0, entering - engine.ENTRY_COST + add, counts)
    return total, games


def b0_like(arms, sched, start, paths, model, team):
    starters = set(model.usage.starters[team])
    counts, prev = start.copy(), sched[0][0]
    total, games = 0.0, []
    for (day, weight), stakes in zip(sched, paths):
        counts = np.maximum(engine.RESTED, counts - engine.RECOVERY * (day - prev).days)
        prev = day
        entering = counts + engine.ENTRY_COST
        fat = {n: counts[i] for i, n in enumerate(arms.names)}
        s, _ = M.usage_starter_step(model, team, fat)
        used, stints, h, cur = set(), [], 0, arms.names.index(s)
        H = len(stakes)
        runs, add = 0.0, np.zeros(len(arms.names))
        while h < H:
            used.add(cur)
            c, e, p, w = entering[cur], h, 30.0, 0.0
            while e < H and (c < arms.S[cur] or e == h):
                r, q = arms.inning(cur, c)
                w += stakes[e] * r
                c += q
                p += q
                e += 1
            runs += w
            add[cur] = p
            stints.append((cur, h, e))
            h = e
            if h < H:
                pool = [i for i in range(len(arms.names)) if i not in used]
                ok = [i for i in pool if arms.names[i] not in starters and entering[i] < arms.S[i]] or \
                     [i for i in pool if entering[i] < arms.S[i]] or pool
                if not ok:
                    break
                cur = min(ok, key=lambda i: arms.inning(i, entering[i])[0])
        total += weight * runs
        games.append((weight, stakes, entering.copy(), stints, add.copy()))
        counts = np.where(add > 0, entering - engine.ENTRY_COST + add, counts)
    return total, games


def search_prices(arms, sched, start, paths, sweeps=4):
    price = np.zeros(len(arms.names))
    best, _ = run_postseason(arms, sched, start, paths, price)
    for _ in range(sweeps):
        improved = False
        for i in range(len(arms.names)):
            for v in PRICES:
                if v == price[i]:
                    continue
                trial = price.copy()
                trial[i] = v
                val, _ = run_postseason(arms, sched, start, paths, trial)
                if val < best - 1e-9:
                    best, price, improved = val, trial, True
        if not improved:
            break
    return best, price


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", nargs="*", default=["SFF", "NYH", "LAQ", "BOS"])
    ap.add_argument("--samples", type=int, default=40)
    ap.add_argument("--seed", type=int, default=20261014)
    ap.add_argument("--out", default=None, help="write every half-inning to this CSV")
    ap.add_argument("--b0-timing", action="store_true",
                    help="stints last until she would start an inning gassed, as B0's do")
    ap.add_argument("--allow-gassed", action="store_true",
                    help="let an arm start a half-inning gassed, as the rules allow")
    a = ap.parse_args()
    global NO_GASSED_START, B0_TIMING
    NO_GASSED_START = not a.allow_gassed
    B0_TIMING = a.b0_timing
    cards, wp = play.shared()
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    model.run_value(1, True, 0, (False, False, False), 0)
    paths = stake_paths(model)
    print(f"{len(paths)} real team-games of stakes; run_scale {model.run_scale:.4f}")
    s1, s2 = P.bracket()
    rng = np.random.default_rng(a.seed)
    rows, avail = [], []
    for team in a.teams:
        semi = s1 if team in s1.teams else s2
        fin = P.final(team, "XXX")
        sw, fw = SP.coin_weights(semi.need, len(semi.games)), SP.coin_weights(fin.need, len(fin.games))
        sched = [(d, w) for (d, _), w in zip(semi.games, sw)] + [(d, w) for (d, _), w in zip(fin.games, fw)]
        arms = Arms(model, team)
        start = np.array([engine.recover(P.FATIGUE_0909.get(n, engine.RESTED), (sched[0][0] - P.START).days)
                          for n in arms.names], float)
        totals = defaultdict(list)
        for k in range(a.samples):
            pick = [paths[j] for j in rng.integers(0, len(paths), len(sched))]
            b0, b0_games = b0_like(arms, sched, start, pick, model, team)
            my, _ = run_postseason(arms, sched, start, pick, np.zeros(len(arms.names)))
            orc, price = search_prices(arms, sched, start, pick)
            _, games = run_postseason(arms, sched, start, pick, price)
            totals["B0-like"].append(b0)
            totals["myopic oracle"].append(my)
            totals["oracle"].append(orc)
            rank = {i: r for r, i in enumerate(np.argsort(arms.r[:, 0]))}   # 0 = best fresh
            for g, (weight, stakes, entering, stints, add) in enumerate(games):
                who = {}
                for i, h, e in stints:
                    for inn in range(h, e):
                        who[inn] = (i, inn == h)
                for i in [j for j in range(len(arms.names)) if rank[j] < 3]:
                    for inn in range(len(stakes)):
                        j, starts = who.get(inn, (-1, False))
                        avail.append(dict(team=team, sample=k, game=g, weight=weight, inning=inn + 1,
                                          stakes=float(stakes[inn]), arm=arms.names[i], rank=rank[i],
                                          entering=float(entering[i]), stamina=arms.S[i],
                                          pitched=j == i, entered=(j == i and starts)))
            for label, gs in (("oracle", games), ("B0-like", b0_games)):
                for g, (weight, stakes, entering, stints, add) in enumerate(gs):
                    for i, h, e in stints:
                        for inn in range(h, e):
                            rows.append(dict(team=team, sample=k, who=label, game=g, weight=weight,
                                             inning=inn + 1, stakes=float(stakes[inn]),
                                             arm=arms.names[i], rank=rank[i],
                                             price=price[i] if label == "oracle" else 0.0,
                                             stint_first=h + 1, stint_innings=e - h,
                                             stint_pitches=float(add[i] - engine.ENTRY_COST),
                                             entering=float(entering[i]), stamina=arms.S[i],
                                             fresh_rate=arms.r[i, 0]))
        print(f"\n=== {team}: {a.samples} sampled postseasons ===")
        for lab, v in totals.items():
            v = np.array(v)
            print(f"  {lab:14s} {v.mean():7.3f} weighted runs (sd {v.std():.2f}); "
                  f"x run_scale = {v.mean() * model.run_scale:.3f}")
        d = np.array(totals["B0-like"]) - np.array(totals["oracle"])
        dm = np.array(totals["B0-like"]) - np.array(totals["myopic oracle"])
        print(f"  oracle saves {d.mean():.3f} +/- {d.std() / np.sqrt(len(d)):.3f} over B0-like; "
              f"hindsight inside games alone saves {dm.mean():.3f}")
    df = pd.DataFrame(rows)
    if a.out:
        df.to_csv(a.out, index=False)
        pd.DataFrame(avail).to_csv(a.out.replace(".csv", "_top3.csv"), index=False)
        print(f"\nwrote {len(df)} stints to {a.out}")


if __name__ == "__main__":
    main()
