"""Who pitched, when, for how long, and why they came out: B2 as it stands (four
fixes, series horizon, innings by their stakes) against the four fixes alone, in
the same simulated postseasons (B2 managing both sides).

    pixi run python analysis/manager/usage_report.py [--postseasons 300]

User (2026-10-15). Per named pitcher, per postseason: appearances (each a warm-up;
starts counted apart), batters faced and pitches per outing, the run-value index
when she came in and over her outing, the column she came in with, and why she
came out. Per team: arms and warm-ups a game, batters faced by gassed pitchers,
how many arms were available at each change (fresh, or at least not gassed), and
how often a gassed pitcher stayed in because nobody else could come in. Then each
team's best arm gassed against its other arms fresh and fading.
"""
import argparse
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from wpbl import engine, manager as M, play, postseason as P, usage


def collect(model, n, setup):
    cards = model.cards
    stints, decisions, games = [], [], []
    orig_mgr, orig_play, orig_decide = P.manager_for, P.play_game, M.Planner.decide
    current = {}

    def manager_for(*a, **k):
        p = orig_mgr(*a, **k)
        setup(p)
        p.log = []
        current[p.team] = p
        return p

    def decide(self, g, side):
        out = orig_decide(self, g, side)
        gassed = g.column(side.pitcher) == "gassed"
        if out != "keep" or gassed:
            opts = M.options(g, side, model)
            ready = [o[0] for o in opts
                     if engine.column_for(engine.enter(g.fatigue[o[0]]), cards.stamina(o[0])) != "gassed"]
            fresh = [x for x in ready if engine.enter(g.fatigue[x]) < engine.FRESH_UNTIL]
            decisions.append(dict(team=side.team, gassed=gassed, changed=out != "keep",
                                  fresh=len(set(fresh)), ready=len(set(ready)), inning=g.inning))
        return out

    def play_game(model_, series, date, home, fatigue, rng, explain=False):
        g, lineups, steps = orig_play(model_, series, date, home, fatigue, rng, explain)
        reasons = {}
        for t, p in current.items():
            for row in p.log or []:
                if row["chosen"] not in (None, "keep"):
                    reasons[(t, row["pitcher"])] = row["kind"]
        score, cur = (0, 0), {}
        recs = defaultdict(list)
        for e in g.events:
            if e["event"] == "pa" and e.get("outs_before") is not None:
                ob = e["outs_before"]
                outs, bases = int(ob.split()[0]), [c != "_" for c in ob.split()[-1]]
                rv = model.run_value(e["inning"], e["half"] == "top", outs, bases, score[1] - score[0])
                recs[(e["fielding"], e["pitcher"])].append((e["column"], rv, e["inning"]))
            score = (e["away_runs"], e["home_runs"])
        for (team, name), pas in recs.items():
            st = g.stats[name]
            started = lineups[team]["pitcher"] == name
            thrown = g.fatigue[name] - engine.enter(st["start"])
            stints.append(dict(team=team, pitcher=name, date=date, started=started, BF=len(pas),
                               pitches=thrown, entry_col=pas[0][0], entry_rv=pas[0][1],
                               mean_rv=float(np.mean([x[1] for x in pas])),
                               gassed_BF=sum(1 for x in pas if x[0] == "gassed"),
                               entry_inning=pas[0][2], why=reasons.get((team, name), "finished the game")))
        for t in (g.away.team, g.home.team):
            games.append(dict(team=t, arms=sum(1 for s in g.stats.values() if s["team"] == t),
                              nobody=sum(1 for row in (current[t].log or []) if row["kind"] == "nobody left")))
        current.clear()
        return g, lineups, steps

    P.manager_for, P.play_game, M.Planner.decide = manager_for, play_game, decide
    try:
        for s in range(1, n + 1):
            P.postseason(model, s)
    finally:
        P.manager_for, P.play_game, M.Planner.decide = orig_mgr, orig_play, orig_decide
    return pd.DataFrame(stints), pd.DataFrame(decisions), pd.DataFrame(games)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--postseasons", type=int, default=300)
    ap.add_argument("--variants", nargs=2, default=["horizon", "four"],
                    help="two of: horizon, four, value, derived")
    a = ap.parse_args()
    cards, wp = play.shared()
    model = M.Model(cards, wp)
    model.usage = usage.Usage(cards)
    model.run_value(1, True, 0, (False, False, False), 0)
    pd.set_option("display.width", 250)
    res = {}
    variants = {"horizon": ("B2 + horizon", lambda p: setattr(p, "horizon_c", True)),
                "four": ("four fixes", lambda p: None),
                "value": ("value price", lambda p: setattr(p, "value_price", True)),
                "derived": ("value derived", lambda p: (setattr(p, "value_price", True),
                                                       setattr(p, "value_mode", "derived")))}
    for key in a.variants:
        label, setup = variants[key]
        res[label] = collect(model, a.postseasons, setup)
        print(f"{label}: done", flush=True)
    n = a.postseasons

    print("\n=== team level, per game ===")
    rows = {}
    for label, (st, dec, gm) in res.items():
        for t, g in gm.groupby("team"):
            s = st[st["team"] == t]
            d = dec[dec["team"] == t]
            ch = d[d["changed"]]
            stuck = d[d["gassed"] & ~d["changed"]]
            rows[(t, label)] = {
                "games": len(g), "arms/game": g["arms"].mean(),
                "gassed BF/game": s["gassed_BF"].sum() / len(g),
                "changes: fresh options (mean)": ch["fresh"].mean(),
                "changes with 0 fresh options %": 100 * (ch["fresh"] == 0).mean(),
                "changes with 0 non-gassed options %": 100 * (ch["ready"] == 0).mean(),
                "gassed kept in (PAs)/game": len(stuck) / len(g),
                "  ...with nobody non-gassed %": 100 * (stuck["ready"] == 0).mean() if len(stuck) else np.nan,
            }
    print(pd.DataFrame(rows).T.to_string(float_format=lambda x: f"{x:.2f}"))

    print("\n=== per pitcher: apps, starts and gassed BF per simulated postseason (semifinal exits included); the rest per appearance ===")
    for t in ("SFF", "NYH", "LAQ", "BOS"):
        parts = []
        for label, (st, dec, gm) in res.items():
            s = st[st["team"] == t]
            g = s.groupby("pitcher")
            why = s.groupby(["pitcher", "why"]).size().unstack(fill_value=0)
            col = s.groupby(["pitcher", "entry_col"]).size().unstack(fill_value=0)
            tab = pd.DataFrame({
                "apps": g.size() / n, "starts": g["started"].sum() / n,
                "BF/app": g["BF"].mean(), "pitches/app": g["pitches"].mean(),
                "entry rv": g["entry_rv"].mean(), "mean rv": g["mean_rv"].mean(),
                "in fresh %": 100 * col.get("fresh", 0) / g.size(),
                "in fading %": 100 * col.get("fading", 0) / g.size(),
                "out gassed %": 100 * why.get("relieved gassed", 0) / g.size(),
                "out early %": 100 * why.get("early swap", 0) / g.size(),
                "finished %": 100 * why.get("finished the game", 0) / g.size(),
                "gassed BF": g["gassed_BF"].sum() / n,
            })
            tab.columns = pd.MultiIndex.from_product([[label], tab.columns])
            parts.append(tab)
        out = pd.concat(parts, axis=1).fillna(0)
        q = {n_: model.runs_per_inning(n_, "fresh") for n_ in out.index}
        out = out.loc[sorted(out.index, key=lambda x: q[x])]
        out.insert(0, ("card", "fresh r/inn"), [q[x] for x in out.index])
        print(f"\n{t}:\n" + out.to_string(float_format=lambda x: f"{x:.2f}"))

    print("\n=== gassed: each team's best arm gassed against its other arms (runs per inning) ===")
    for t in ("SFF", "NYH", "LAQ", "BOS"):
        arms = sorted(M.arms(model, t), key=lambda x: model.runs_per_inning(x, "fresh"))
        ace = arms[0]
        g_ace = model.runs_per_inning(ace, "gassed")
        worse_fresh = [x for x in arms[1:] if model.runs_per_inning(x, "fresh") > g_ace]
        worse_fad = [x for x in arms[1:] if model.runs_per_inning(x, "fading") > g_ace]
        print(f"  {t} {ace}: fresh {model.runs_per_inning(ace, 'fresh'):.2f}, fading "
              f"{model.runs_per_inning(ace, 'fading'):.2f}, gassed {g_ace:.2f}. Others worse FRESH than she is "
              f"gassed: {len(worse_fresh)} of {len(arms) - 1} ({', '.join(x.split()[-1] for x in worse_fresh)}); "
              f"worse FADING: {len(worse_fad)}")


if __name__ == "__main__":
    main()
