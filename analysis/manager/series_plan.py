"""What a good pitching plan for a whole postseason looks like, for one team.

    pixi run python analysis/manager/series_plan.py [--teams NYH LAQ] [--restarts 4]

User (2026-10-14): before tuning B2 further, find out what an optimal assignment
looks like -- who should start, how many starters to cycle, which stints the best
reliever should take, and how often a better arm should pitch tired rather than a
worse one fresh. This plans in expected values, not dice, so the answers are the
shape of good usage, not a game log.

The team's postseason: its semifinal dates, then the final's (the final planned
as if its semifinal went three games, so fatigue is never understated). Counts
start from the 9 Sep chart (postseason.FATIGUE_0909), recover 20 a day with the
floor at -30, and every arm who pitches adds the 30-pitch warm-up and what she
throws (engine.enter, engine.recover), in expectation. Disfavored pitchers are
left out.

One game, for the fielding side:
  starter   pitches innings 1..s (s planned), each at the average run-value index
            real 2026 half-innings had in that inning (half_inning_starts), from
            the count she takes the mound with: fresh below 20, fading until her
            stamina, gassed at it (her card's runs and pitches per inning in each
            column; straight division, no spread)
  relief    WITHOUT FORESIGHT (user, 2026-10-14): the innings after her come one
            at a time. Before each, the manager sees that inning's stakes -- one of
            five equally likely bands of the run values real half-innings had in
            that inning -- and picks an unused arm for one inning or two; a used
            arm cannot come back. The next inning's band follows this one's as it
            did between consecutive innings in the real games (a close 6th tends to
            mean a close 7th). Solved exactly by a small dynamic program over the
            arms left (`relief_dp`), the eight best relievers of the game.
  later     an arm used today carries pitches into later games; the plan prices
            that with a cost per pitch for each arm (warm-up included), chosen by
            the search like the starters. It steers who relieves; the score is runs.
  value     runs allowed weighted by those run values (1.00 = an average
            half-inning start). Innings nobody can cover cost 2.5 runs an inning.

The series: each game counts by its series leverage times the chance it is
played, every result a coin flip from 0-0 (manager.leverage). Semifinal and final
games are on the same footing (reaching the final and winning it each taken as
50%). The total is a leverage-weighted sum of weighted runs, not a probability.

Choices: each game's starter (any arm) and her innings (STARTER_INNINGS), and each
arm's cost per pitch (PITCH_COSTS). Searched by coordinate descent from the rotation
B2 uses now and from random starts.

Baseline ("B2-like"): B2's starter rule (usage_starter_step), the starter until she
is gassed, relief by the same program with no cost for later games.
"""
import argparse

import numpy as np
import pandas as pd

from wpbl import engine, manager as M, play, postseason as P, usage
from wpbl.leverage import half_inning_starts

STARTER_INNINGS = (1, 2, 3, 4, 5, 6, 7)   # her plan; she stops sooner if gassed
PITCH_COSTS = (0.0, 0.004, 0.008, 0.016, 0.032)   # weighted runs per pitch, for later games
UNCOVERED = 2.5                           # runs an inning for innings nobody covers
BANDS = 5                                 # stakes bands per inning, equally likely
MAX_ARMS = 8                              # relievers the in-game program considers
INN = engine.INNINGS


def coin_weights(need, n):
    """Series leverage x chance played for games 1..n of a best-of-(2*need-1)."""
    states, out = {(0, 0): 1.0}, []
    for _ in range(n):
        out.append(sum(p * M.leverage(a, b, need) for (a, b), p in states.items()))
        nxt = {}
        for (a, b), p in states.items():
            for s in ((a + 1, b), (a, b + 1)):
                if s[0] < need and s[1] < need:
                    nxt[s] = nxt.get(s, 0.0) + 0.5 * p
        states = nxt
    return out


class Staff:
    def __init__(self, model, team):
        self.model, self.team = model, team
        cards = model.cards
        self.arms = [n for n in M.arms(model, team) if n in cards.pitcher]
        self.q = {n: dict(S=cards.stamina(n),
                          rf=model.runs_per_inning(n, "fresh"), rd=model.runs_per_inning(n, "fading"),
                          pf=model.pitches_per_inning(n, "fresh"), pd=model.pitches_per_inning(n, "fading"))
                  for n in self.arms}

    def segments(self, n, c):
        """[(innings, runs per inning, pitches per inning)] from count c on the
        mound until gassed: the fresh part, then the fading part."""
        a, out = self.q[n], []
        if c < engine.FRESH_UNTIL:
            out.append(((min(engine.FRESH_UNTIL, a["S"]) - c) / a["pf"], a["rf"], a["pf"]))
        lo = max(c, engine.FRESH_UNTIL)
        if lo < a["S"]:
            out.append(((a["S"] - lo) / a["pd"], a["rd"], a["pd"]))
        return out

    def take(self, n, c, innings):
        """(innings covered, runs, pitches) for up to `innings` from count c."""
        got = runs = pitches = 0.0
        for length, r, p in self.segments(n, c):
            use = min(length, innings - got)
            if use <= 0:
                break
            got, runs, pitches = got + use, runs + use * r, pitches + use * p
        return got, runs, pitches

    def cover(self, n, c, innings):
        """(runs, pitches) for `innings`, any part she cannot reach charged UNCOVERED."""
        got, runs, pitches = self.take(n, c, innings)
        return runs + (innings - got) * UNCOVERED, pitches


class Stakes:
    """Run-value index at the start of real 2026 half-innings: each inning's mean,
    five equally likely bands, and how the band moves from one inning to the next
    for the same fielding side."""

    def __init__(self, model):
        st = half_inning_starts()
        st = st[st["inning"] <= INN].copy()
        st["rv"] = [model.run_value(r.inning, r.half == "top", 0, (False, False, False), int(r.diff))
                    for r in st.itertuples()]
        self.mean = st.groupby("inning")["rv"].mean().to_dict()
        self.edges, self.value = {}, {}
        for i, g in st.groupby("inning"):
            v = np.sort(g["rv"].to_numpy())
            parts = np.array_split(v, BANDS)
            self.value[i] = np.array([p.mean() for p in parts])
            self.edges[i] = np.array([p[-1] for p in parts[:-1]])
        st["band"] = [int(np.searchsorted(self.edges[i], v, side="left")) for i, v in zip(st["inning"], st["rv"])]
        band = {(r.game_id, r.pitching_team_id, r.inning): r.band for r in st.itertuples()}
        self.move = {}
        for i in range(1, INN):
            T = np.full((BANDS, BANDS), 0.5)                       # light smoothing
            for (gid, team, inn), b in band.items():
                if inn == i and (gid, team, i + 1) in band:
                    T[b, band[(gid, team, i + 1)]] += 1
            self.move[i] = T / T.sum(axis=1, keepdims=True)

    def starter_value(self, staff, n, c, innings):
        """(innings, weighted runs, pitches) for the starter's innings 1..innings."""
        got = w = pitches = 0.0
        segs = staff.segments(n, c)
        k, left = 0, segs[0][0] if segs else 0.0
        while got < innings - 1e-9 and k < len(segs):
            inn = int(got + 1e-9) + 1
            frac = min(inn - got, innings - got, left)
            _, r, p = segs[k]
            w += frac * r * self.mean[min(inn, INN)]
            pitches += frac * p
            got += frac
            left -= frac
            if left <= 1e-9:
                k += 1
                left = segs[k][0] if k < len(segs) else 0.0
        return got, w, pitches


def relief_dp(staff, stakes, s_got, entering, cost, policy=False):
    """Relief without foresight. `entering`: {arm: count she would take the mound
    with}; `cost`: {arm: weighted runs per pitch for later games}. Returns
    (expected weighted runs, {arm: (chance used, expected innings, expected
    pitches incl. warm-up, expected stakes x innings)}); with `policy`, the
    decision table instead: (arms, slots, act), act[slot, arms-left mask, band] =
    2 * arm index + (1 if for two innings), -1 for nobody."""
    slots, x = [], s_got                  # the rest of the starter's last inning, then whole innings
    while x < INN - 1e-9:
        inn = int(x + 1e-9) + 1
        slots.append((inn, inn - x))
        x = inn
    if not slots:
        return ([], [], None) if policy else (0.0, {})

    def rate(n):
        got, runs, _ = staff.take(n, entering[n], 1.0)
        return runs / got if got > 1e-9 else np.inf
    arms = [n for n in sorted(entering, key=rate) if entering[n] < staff.q[n]["S"]][:MAX_ARMS]
    R, K, B = len(arms), len(slots), BANDS
    full = (1 << R) - 1
    one = np.zeros((R, K)); two_a = np.zeros((R, K)); two_b = np.zeros((R, K))
    p1 = np.zeros((R, K)); p2 = np.zeros((R, K))
    for i, n in enumerate(arms):
        c = entering[n]
        for k in range(K):
            f = slots[k][1]
            r_f, pt_f = staff.cover(n, c, f)
            one[i, k], p1[i, k] = r_f, 30 + pt_f
            if k + 1 < K:
                r_2, pt_2 = staff.cover(n, c, f + slots[k + 1][1])
                two_a[i, k], two_b[i, k], p2[i, k] = r_f, r_2 - r_f, 30 + pt_2
    lam = np.array([cost.get(n, 0.0) for n in arms])
    masks = np.arange(full + 1)
    move = lambda inn: stakes.move[inn] if inn < INN else np.eye(B)

    V = np.zeros((K + 1, full + 1, B))                 # objective: runs + priced pitches; V[K] = 0
    act = np.full((K, full + 1, B), -1, int)           # 2*i + (0: one slot, 1: two)
    for k in range(K - 1, -1, -1):
        inn, f = slots[k]
        val = stakes.value[inn]
        EV1 = V[k + 1] @ move(inn).T if k + 1 < K else np.zeros((full + 1, B))
        best = np.full((full + 1, B), np.inf)
        best_a = np.full((full + 1, B), -1)
        best[0] = val * f * UNCOVERED + EV1[0]
        for i in range(R):
            has = masks[((masks >> i) & 1) == 1]
            rest = has ^ (1 << i)
            c1 = val[None, :] * one[i, k] + lam[i] * p1[i, k] + EV1[rest]
            upd = c1 < best[has]
            best[has] = np.where(upd, c1, best[has])
            best_a[has] = np.where(upd, 2 * i, best_a[has])
            if k + 1 < K:
                inn2 = slots[k + 1][0]
                EV2 = V[k + 2] @ move(inn2).T if k + 2 < K else np.zeros((full + 1, B))
                after = (stakes.value[inn2][None, :] * two_b[i, k] + EV2[rest]) @ move(inn).T
                c2 = val[None, :] * two_a[i, k] + lam[i] * p2[i, k] + after
                upd = c2 < best[has]
                best[has] = np.where(upd, c2, best[has])
                best_a[has] = np.where(upd, 2 * i + 1, best_a[has])
        V[k], act[k] = best, best_a
    if policy:
        return arms, slots, act

    # forward: chance of each (arms left, band); expected runs and usage
    prob = [np.zeros((full + 1, B)) for _ in range(K + 1)]
    prob[0][full] = 1.0 / B
    runs = 0.0
    use = {n: [0.0, 0.0, 0.0, 0.0] for n in arms}
    for k in range(K):
        inn, f = slots[k]
        val = stakes.value[inn]
        Pk = prob[k]
        for m in np.nonzero(Pk.sum(axis=1) > 1e-12)[0]:
            for b in range(B):
                pr = Pk[m, b]
                if pr <= 1e-12:
                    continue
                a = act[k, m, b]
                if a < 0:                                        # nobody left
                    runs += pr * val[b] * f * UNCOVERED
                    if k + 1 < K:
                        prob[k + 1][m] += pr * move(inn)[b]
                    continue
                i, two = divmod(int(a), 2)
                n, rest = arms[i], m ^ (1 << i)
                u = use[n]
                if not two:
                    runs += pr * val[b] * one[i, k]
                    u[0] += pr; u[1] += pr * f; u[2] += pr * p1[i, k]; u[3] += pr * val[b] * f
                    if k + 1 < K:
                        prob[k + 1][rest] += pr * move(inn)[b]
                else:
                    inn2, f2 = slots[k + 1]
                    nb = move(inn)[b]
                    v2 = nb @ stakes.value[inn2]
                    runs += pr * (val[b] * two_a[i, k] + v2 * two_b[i, k])
                    u[0] += pr; u[1] += pr * (f + f2); u[2] += pr * p2[i, k]; u[3] += pr * (val[b] * f + v2 * f2)
                    if k + 2 < K:
                        prob[k + 2][rest] += pr * (nb @ move(inn2))
    return runs, {n: tuple(v) for n, v in use.items() if v[0] > 1e-9}


def play_game(staff, stakes, counts, starter, s_inn, cost):
    """(weighted runs, counts after, starter innings, relief usage) for one game."""
    after = dict(counts)
    c0 = engine.enter(counts[starter])
    s_got, w, thrown = stakes.starter_value(staff, starter, c0, s_inn)
    after[starter] = c0 + thrown
    entering = {n: engine.enter(counts[n]) for n in staff.arms if n != starter}
    runs, use = relief_dp(staff, stakes, s_got, entering, cost)
    for n, (pu, inn, pitches, _) in use.items():
        after[n] = counts[n] + pitches                  # warm-up and pitches, in expectation
    return w + runs, after, s_got, use


def evaluate(staff, stakes, sched, start, plan, cost, detail=False):
    counts, prev = dict(start), sched[0][0]
    total, rows = 0.0, []
    for (day, weight), (starter, s_inn) in zip(sched, plan):
        counts = {n: engine.recover(c, (day - prev).days) for n, c in counts.items()}
        prev = day
        w, after, s_got, use = play_game(staff, stakes, counts, starter, s_inn, cost)
        if detail:
            rows.append((day, weight, starter, s_inn, counts, s_got, use, w))
        total += weight * w
        counts = after
    return total, rows


def b2_like(staff, stakes, sched, start, model):
    counts, prev, plan = dict(start), sched[0][0], []
    for day, _ in sched:
        counts = {n: engine.recover(c, (day - prev).days) for n, c in counts.items()}
        prev = day
        starter, _ = M.usage_starter_step(model, staff.team, counts)
        plan.append((starter, 7))
        _, counts, _, _ = play_game(staff, stakes, counts, starter, 7, {})
    return plan


def search(staff, stakes, sched, start, plan, cost, sweeps=8):
    plan, cost = list(plan), dict(cost)
    best, _ = evaluate(staff, stakes, sched, start, plan, cost)
    for _ in range(sweeps):
        improved = False
        for g in range(len(plan)):
            for var, values in (("starter", staff.arms), ("inn", STARTER_INNINGS)):
                for v in values:
                    trial = list(plan)
                    trial[g] = (v, plan[g][1]) if var == "starter" else (plan[g][0], v)
                    val, _ = evaluate(staff, stakes, sched, start, trial, cost)
                    if val < best - 1e-9:
                        best, plan, improved = val, trial, True
        for n in staff.arms:
            for v in PITCH_COSTS:
                c2 = dict(cost)
                c2[n] = v
                val, _ = evaluate(staff, stakes, sched, start, plan, c2)
                if val < best - 1e-9:
                    best, cost, improved = val, c2, True
        if not improved:
            break
    return best, plan, cost


def describe(staff, stakes, sched, start, plan, cost, label):
    total, rows = evaluate(staff, stakes, sched, start, plan, cost, detail=True)
    print(f"\n  {label}: {total:.3f} (leverage-weighted sum of weighted runs)")
    use = {n: {"starts": 0, "start inn": 0.0, "relief apps": 0.0, "relief inn": 0.0, "stakes x inn": 0.0}
           for n in staff.arms}
    for day, weight, starter, s_inn, before, s_got, rel, w in rows:
        c0 = engine.enter(before[starter])
        use[starter]["starts"] += 1
        use[starter]["start inn"] += s_got
        parts = []
        for n, (pu, inn, pitches, sv) in sorted(rel.items(), key=lambda t: -t[1][3] / max(t[1][1], 1e-9)):
            use[n]["relief apps"] += pu
            use[n]["relief inn"] += inn
            use[n]["stakes x inn"] += sv
            c = engine.enter(before[n])
            parts.append(f"{n.split()[-1]} {pu:.0%}, {inn:.1f} inn at {sv / max(inn, 1e-9):.2f} "
                         f"({engine.column_for(c, staff.q[n]['S'])} {c:.0f})")
        print(f"    {day:%d %b} (weight {weight:.2f}): {starter} starts at {c0:.0f} "
              f"({engine.column_for(c0, staff.q[starter]['S'])}), {s_got:.1f} inn; relief: "
              + ("; ".join(parts) if parts else "none"))
    tab = pd.DataFrame(use).T
    tab["relief stakes"] = (tab["stakes x inn"] / tab["relief inn"]).where(tab["relief inn"] > 1e-9)
    tab["fresh runs/inn"] = [staff.q[n]["rf"] for n in tab.index]
    tab["cost/pitch"] = [cost.get(n, 0.0) for n in tab.index]
    tab = tab[(tab["starts"] > 0) | (tab["relief apps"] > 0.05)].sort_values("fresh runs/inn")
    print(tab[["fresh runs/inn", "starts", "start inn", "relief apps", "relief inn", "relief stakes", "cost/pitch"]]
          .to_string(float_format=lambda x: f"{x:.2f}"))
    return total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--teams", nargs="*", default=["SFF", "NYH", "LAQ", "BOS"])
    ap.add_argument("--restarts", type=int, default=4)
    ap.add_argument("--seed", type=int, default=20261014)
    a = ap.parse_args()
    cards, wp = play.shared()
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    model.run_value(1, True, 0, (False, False, False), 0)
    stakes = Stakes(model)
    s1, s2 = P.bracket()
    rng = np.random.default_rng(a.seed)
    print("stakes bands by inning (real 2026):",
          {i: [round(x, 2) for x in v] for i, v in stakes.value.items()})
    for team in a.teams:
        semi = s1 if team in s1.teams else s2
        fin = P.final(team, "XXX")
        sw, fw = coin_weights(semi.need, len(semi.games)), coin_weights(fin.need, len(fin.games))
        sched = [(d, w) for (d, _), w in zip(semi.games, sw)] + [(d, w) for (d, _), w in zip(fin.games, fw)]
        start = {n: engine.recover(P.FATIGUE_0909.get(n, engine.RESTED), (sched[0][0] - P.START).days)
                 for n in M.arms(model, team) if n in cards.pitcher}
        staff = Staff(model, team)
        base = b2_like(staff, stakes, sched, start, model)
        best_val, best, best_cost = search(staff, stakes, sched, start, base, {})
        for _ in range(a.restarts):
            good = sorted(staff.arms, key=lambda n: staff.q[n]["rd"])[:6]
            init = [(rng.choice(good), int(rng.choice(STARTER_INNINGS))) for _ in sched]
            c0 = {n: float(rng.choice(PITCH_COSTS)) for n in staff.arms}
            v, p, c = search(staff, stakes, sched, start, init, c0)
            if v < best_val:
                best_val, best, best_cost = v, p, c
        print(f"\n=== {team}: {len(sched)} dates ({', '.join(f'{d:%d}' for d, _ in sched)} Sep) ===")
        b = describe(staff, stakes, sched, start, base, {}, "B2-like")
        o = describe(staff, stakes, sched, start, best, best_cost, "best plan found")
        print(f"  difference: {b - o:.3f}")


if __name__ == "__main__":
    main()
