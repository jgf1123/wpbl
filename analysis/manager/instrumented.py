"""Instrumented series: record everything about how each manager uses its staff.

    pixi run python analysis/manager/instrumented.py [--series 100] [--policies B0 B2 B2noearly]

The same seeded best-of-5 series as `pixi run manager --conventions` (each team
against each other, both home schedules), the opponent always B0. For every
managed team it writes four tables to data/sim/ (csv, one row per):

  games        team-game: starter and the step of the starter rule that chose
               her, her count before and on entering, innings and pitches;
               runs for and against; arms used; batters faced by a gassed
               pitcher; DH kept or lost
  appearances  pitcher-game: starter or reliever, role (starter by role or
               not), entering count and column, inning entered, batters faced,
               pitches, outs, runs allowed, finished the game, left gassed
  decisions    every gassed-pitcher decision (and B2's high-leverage ones):
               situation, options, what was chosen and why
  nights       team-night between games: pitches recovered, arms already at
               the -30 floor, the staff's total count before and after

and prints a summary. The opponent's rows are not recorded.
"""
import argparse
import re
import time
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

from wpbl import engine, manager as M, play, usage

OUT = Path(__file__).resolve().parents[2] / "data" / "sim"
TEAMS = ["BOS", "LAQ", "NYH", "SFF"]


def outs_of(text):
    m = re.match(r"(\d) out", text or "")
    return int(m.group(1)) if m else 0


def make(model, label, team):
    if label == "B0":
        return M.Baseline(model, team)
    p = M.Planner(model, team)
    p.early = label != "B2noearly"
    return p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--series", type=int, default=100)
    ap.add_argument("--policies", nargs="*", default=["B0", "B2", "B2noearly"])
    a = ap.parse_args()
    cards, wp = play.shared()
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    roles = model.usage.starters
    OUT.mkdir(parents=True, exist_ok=True)

    for label in a.policies:
        t0 = time.time()
        games, apps, decisions, nights = [], [], [], []
        sid = 0
        for me in TEAMS:
            for opp in TEAMS:
                if me == opp:
                    continue
                for hi_me in (True, False):
                    hi, lo = (me, opp) if hi_me else (opp, me)
                    for k in range(a.series):
                        sid += 1
                        mine = make(model, label, me)
                        mine.log = []

                        def record(g, info, sid=sid, mine=mine, me=me, opp=opp):
                            side = g.home if g.home.team == me else g.away
                            other = g.away if side is g.home else g.home
                            gn = info["game"]
                            pas = [e for e in g.events if e["event"] == "pa" and e["fielding"] == me]
                            gassed = [e for e in pas if e["column"] == "gassed"]
                            start_lineup = info["lineups"][me]["order"]
                            for i, n in enumerate(side.used):
                                mine_pa = [e for e in pas if e["pitcher"] == n]
                                outs = sum(outs_of(e.get("outs_after")) - outs_of(e.get("outs_before"))
                                           for e in mine_pa if e.get("outs_after"))
                                entering = g.stats[n]["start"] + engine.ENTRY_COST
                                apps.append({
                                    "policy": label, "series": sid, "game": gn, "team": me,
                                    "pitcher": n, "starter": i == 0, "role_starter": n in roles[me],
                                    "disfavored": n in M.DISFAVORED, "order": i,
                                    "count_before": g.stats[n]["start"], "count_entering": entering,
                                    "column_entering": engine.column_for(entering, cards.stamina(n)),
                                    "stamina": cards.stamina(n),
                                    "inning_in": mine_pa[0]["inning"] if mine_pa else None,
                                    "bf": g.stats[n]["BF"], "pitches": g.fatigue[n] - entering,
                                    "outs": outs, "runs": sum(e.get("scored", 0) for e in mine_pa),
                                    "finished": i == len(side.used) - 1,
                                    "left_gassed": g.fatigue[n] > cards.stamina(n),
                                    "gassed_bf": sum(e["column"] == "gassed" for e in mine_pa)})
                            st = side.used[0]
                            games.append({
                                "policy": label, "series": sid, "game": gn, "team": me, "opp": opp,
                                "home": side is g.home, "wins_before": info["wins_before"][me],
                                "losses_before": info["wins_before"][opp],
                                "starter": st, "starter_step": info["steps"][me],
                                "starter_count_before": info["fatigue_before"][st],
                                "starter_entering": info["fatigue_before"][st] + engine.ENTRY_COST,
                                "starter_stamina": cards.stamina(st),
                                "starter_outs": next(x["outs"] for x in apps[::-1]
                                                     if x["series"] == sid and x["game"] == gn and x["starter"]),
                                "runs_for": side.runs, "runs_against": other.runs, "won": side.runs > other.runs,
                                "arms": len(side.used), "gassed_bf": len(gassed),
                                "innings": len(side.line),
                                "dh_start": any(e.endswith(" DH") for e in start_lineup),
                                "dh_end": any(s_.pos == "DH" for s_ in side.order),
                                "staff_count_after": sum(g.fatigue[n] for n in cards.team_pitchers(me))})
                            if info["next_gap"] is not None:
                                gap = info["next_gap"]
                                staff = [n for n in cards.team_pitchers(me)]
                                before = {n: g.fatigue[n] for n in staff}
                                after = {n: engine.recover(c, gap) for n, c in before.items()}
                                nights.append({
                                    "policy": label, "series": sid, "after_game": gn, "team": me, "days": gap,
                                    "recovered": sum(before[n] - after[n] for n in staff),
                                    "possible": sum(engine.RECOVERY * gap for n in staff),
                                    "at_floor_before": sum(before[n] <= engine.RESTED for n in staff),
                                    "staff_count_before": sum(before.values()),
                                    "staff_count_after": sum(after.values())})
                            for d in mine.log:
                                decisions.append({"policy": label, "series": sid, "game": gn, **d})
                            mine.log.clear()

                        pol = {me: mine, opp: M.Baseline(model, opp)}
                        M.series(model, hi, lo, pol, M.FINAL, zlib.crc32(f"{me}{opp}{hi_me}{k}".encode()),
                                 record=record)
        G, A, D, N = (pd.DataFrame(x) for x in (games, apps, decisions, nights))
        for name, df in (("games", G), ("appearances", A), ("decisions", D), ("nights", N)):
            df.to_csv(OUT / f"{label}_{name}.csv", index=False)
        summarise(label, G, A, D, N, time.time() - t0)


def summarise(label, G, A, D, N, secs):
    print(f"\n===== {label}  ({G['series'].nunique()} series, {len(G)} team-games, {secs:.0f}s)")
    won = G.groupby("series")["won"].sum() >= 3
    print(f"series won {100 * won.mean():.1f}%  games won {100 * G['won'].mean():.1f}%  "
          f"runs for {G['runs_for'].mean():.2f} against {G['runs_against'].mean():.2f}")
    by = G.groupby("game")
    print("by game number:")
    t = pd.DataFrame({
        "games": by.size(),
        "starter step 1/2/3/4 %": by["starter_step"].apply(
            lambda s: "/".join(f"{100 * (s == k).mean():.0f}" for k in (1, 2, 3, 4))),
        "starter entering": by["starter_entering"].mean().round(1),
        "starter innings": (by["starter_outs"].mean() / 3).round(2),
        "arms": by["arms"].mean().round(2),
        "gassed BF": by["gassed_bf"].mean().round(2),
        "runs against": by["runs_against"].mean().round(2)})
    print(t.to_string())
    s = G.groupby("starter_step")
    print("starters by rule step: " + "; ".join(
        f"step {int(k)}: {len(x)} games, entering {x['starter_entering'].mean():.0f}, "
        f"{x['starter_outs'].mean() / 3:.2f} innings" for k, x in s))
    R = A[~A["starter"]]
    print(f"relief appearances: {len(R)} ({len(R) / len(G):.2f} a game); entering column "
          + ", ".join(f"{c} {100 * (R['column_entering'] == c).mean():.0f}%" for c in ("fresh", "fading", "gassed"))
          + f"; innings {R['outs'].mean() / 3:.2f}; finished the game {100 * R['finished'].mean():.0f}%; "
          f"left gassed {100 * R['left_gassed'].mean():.0f}%; role starters relieving "
          f"{100 * R['role_starter'].mean():.0f}%")
    print("  relief appearances by game number: " + "  ".join(
        f"G{int(k)} {len(x) / (G['game'] == k).sum():.2f} ({x['outs'].mean() / 3:.2f} inn, "
        f"fin {100 * x['finished'].mean():.0f}%)" for k, x in R.groupby("game")))
    if len(N):
        nb = N.groupby("after_game")
        print("nights: pitches recovered per team (of possible), arms already at the floor:")
        print("  " + "  ".join(f"after G{int(k)}: {x['recovered'].mean():.0f} of {x['possible'].mean():.0f}, "
                               f"{x['at_floor_before'].mean():.1f} at floor" for k, x in nb))
    if len(D):
        print("decisions: " + ", ".join(f"{k} {v}" for k, v in D["kind"].value_counts().items()))


if __name__ == "__main__":
    main()
