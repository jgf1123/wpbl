"""Where a pitcher's capacity comes from, and why it is not a role (spec 7.4).

    pixi run python analysis/dice/capacity.py

The fatigue model carried `CAPACITY = {"start": 68, "relief": 31}` -- the median
outing by role. Two objections from the user (23 Sep), both of which this script
checks, and both of which hold:

  role is not a property of the arm     twenty-three of thirty-eight pitchers
                                        worked both ways, and some threw LONGER
                                        in relief than in any start

  the median is where the MANAGER       so it measures the decision, not the
  stopped                               limit; the arms a team wants to field
                                        are the ones pressing theirs

The second one has an obvious suspect that turns out to be innocent. A blowout
is where you would expect forced usage to live, so the script splits every
outing by whether the game was contested while she worked. It barely matters.
What matters is WHICH ARM: a team's top five by usage top out around 82 pitches
and everyone below them around 54. The distinction is between pitchers, not
between games.

Also here, because the fresh window turned out to rest on it: the league throws
133.9 pitches a team-game (median 133) over 6.82 innings of a SEVEN-inning game.
That is 19.5 an inning, not the 17.5 the spec used -- 17.5 is the PITCHER-inning
average, which includes relievers' partial innings, and a starter's first inning
is a complete one.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables

CONTESTED = 4       # runs; within this at entry AND at the final whistle
MIN_OUTINGS = 3     # below this a max is one outing, not a ceiling


def outings() -> pd.DataFrame:
    """Every appearance with its pitch count, postseason and excluded games too."""
    p = tables.read("pitching", "all")
    p = p[p["bf"] > 0].copy()
    p["pitches"] = p["pitches_est"]
    p["date"] = pd.to_datetime(p["game_date"])
    return p


def league_rate() -> None:
    """Pitches per team-game, per inning, and per plate appearance."""
    p = outings()
    g = p.groupby(["game_id", "team_id"]).agg(
        pitches=("pitches", "sum"), outs=("ip_outs", "sum"),
        bf=("bf", "sum"), arms=("person_id", "nunique"))
    inn = g["outs"] / 3
    print("=== the league's pitching, per team-game ===")
    print("  pitches   mean %.1f  median %.1f" % (g.pitches.mean(), g.pitches.median()))
    print("  innings   mean %.2f  median %.2f   <- a SEVEN-inning game"
          % (inn.mean(), inn.median()))
    print("  per inning %.1f   per PA %.2f   arms %.2f"
          % (g.pitches.sum() / inn.sum(), g.pitches.sum() / g.bf.sum(), g.arms.mean()))

    pl = tables.read("plays", "all")
    pl = pl[pl["is_plate_appearance"].astype(bool)].copy()
    pl["np"] = pl["n_pitches_est"].fillna(pl["n_pitches"])
    team_inn = pl.groupby(["game_id", "pitching_team_id", "inning"])["np"].sum()
    pit_inn = pl.groupby(["game_id", "pitcher_id", "inning"])["np"].sum()
    print("\n  per TEAM-inning     %.2f (SD %.2f)" % (team_inn.mean(), team_inn.std()))
    print("  per PITCHER-inning  %.2f (SD %.2f)  <- the spec's old 17.5, partials in"
          % (pit_inn.mean(), pit_inn.std()))

    st = tables.read("pitching_stints", "all")
    st = st[st["is_starter"].astype(bool)]
    f = pl.merge(st[["game_id", "pitcher_id"]], on=["game_id", "pitcher_id"])
    first = f[f["inning"] == 1].groupby(["game_id", "pitcher_id"])["np"].sum()
    print("  STARTER'S FIRST INNING  mean %.1f  median %.1f  over %d starts"
          % (first.mean(), first.median(), len(first)))
    print("  -> the fresh window is 20, measured, not 17 inferred from 17.5")


def roles() -> None:
    """How many arms worked both ways, and whether relief is really a smaller job."""
    p = outings()
    p["S"] = p["is_starter"].astype(bool)
    per = p.groupby("person_name").agg(app=("pitches", "size"), gs=("S", "sum"))
    swing = per[(per.gs > 0) & (per.gs < per.app)]
    print("\n=== role is not a property of the arm ===")
    print("  %d of %d pitchers worked both ways, %.0f%% of all outings"
          % (len(swing), len(per), 100 * per.loc[swing.index, "app"].sum() / per.app.sum()))
    rows = []
    for name in swing.index:
        q = p[p.person_name == name]
        rows.append((name, q[q.S]["pitches"].max(), q[~q.S]["pitches"].max()))
    d = pd.DataFrame(rows, columns=["name", "as_start", "as_relief"])
    longer = d[d.as_relief > d.as_start]
    print("  %d of them threw MORE in relief than in any start:" % len(longer))
    for r in longer.sort_values("as_relief", ascending=False).head(6).itertuples():
        print("    %-22s start %3.0f   relief %3.0f" % (r.name, r.as_start, r.as_relief))
    print("  a role median measures the manager's PLAN, not the arm")


def wanted_or_forced() -> None:
    """The blowout hypothesis (innocent) against the fringe-arm one (guilty)."""
    st = tables.read("pitching_stints", "all").copy()
    ls = tables.read("line_score", "all")
    tot = ls.groupby(["game_id", "team_id"])["runs"].sum().reset_index(name="final")
    pair = tot.merge(tot, on="game_id")
    pair = pair[pair.team_id_x != pair.team_id_y]
    pair["margin"] = (pair.final_x - pair.final_y).abs()
    st["final_margin"] = st.game_id.map(pair.groupby("game_id")["margin"].first())
    st["pit"] = st["pitches_est"]
    st["contested"] = (st.entry_score_diff.abs() <= CONTESTED) & (st.final_margin <= CONTESTED)
    st["S"] = st.is_starter.astype(bool)

    print("\n=== is it the GAME? (blowouts) -- no ===")
    for lab, S in (("start", True), ("relief", False)):
        for c in (True, False):
            q = st[(st.S == S) & (st.contested == c)]["pit"]
            print("  %-6s %-9s n=%3d  median %5.1f  p90 %3.0f"
                  % (lab, "contested" if c else "decided", len(q), q.median(), q.quantile(.9)))
    print("  the medians barely move: forced usage does not live in blowouts")

    p = outings()
    per = p.groupby(["team_name", "person_name"]).agg(
        app=("pitches", "size"), mx=("pitches", "max"),
        med=("pitches", "median"), bf=("bf", "sum")).reset_index()
    per = per[per.app >= MIN_OUTINGS]
    per["rank"] = per.groupby("team_name")["bf"].rank(ascending=False, method="first")
    print("\n=== is it the ARM? -- yes ===")
    print("  median per-arm ceiling, a team's top five by usage: %.0f pitches"
          % per[per["rank"] <= 5].mx.median())
    print("  median per-arm ceiling, everyone below them:        %.0f pitches"
          % per[per["rank"] > 5].mx.median())


def ceilings() -> None:
    """The per-arm capacity estimate, and how much of a max is real."""
    p = outings()
    per = p.groupby("person_name").agg(
        app=("pitches", "size"), mx=("pitches", "max"), med=("pitches", "median"))
    c = per[per.app >= MIN_OUTINGS]
    print("\n=== a ceiling is mostly a trait ===")
    print("  corr(max, her median outing) %.2f   corr(max, how often she pitched) %.2f"
          % (c.mx.corr(c.med), c.mx.corr(c.app)))
    b, a = np.polyfit(c.med, c.mx, 1)
    resid = c.mx - (a + b * c.med)
    print("  max = %.1f + %.2f x median    R2 %.2f   residual SD %.1f"
          % (a, b, 1 - resid.var() / c.mx.var(), resid.std()))
    print("  rounding to the nearest ten costs little against a residual SD of %.1f"
          % resid.std())

    from wpbl.engine import capacity
    caps = pd.Series(capacity())
    print("\n  the ladder the engine builds (spec 7.4):")
    for level, n in sorted(caps.value_counts().items()):
        print("    %3.0f  %s" % (level, "#" * int(n)))
    print("  median %.0f over %d arms" % (caps.median(), len(caps)))


def rest() -> None:
    """Whether a 100-pitch arm can clear her own capacity before she pitches again."""
    p = outings().sort_values(["person_id", "date"])
    starts = p[p.is_starter.astype(bool)].copy()
    gap = starts.groupby("person_id")["date"].diff().dt.days.dropna()
    print("\n=== does the top of the ladder clear? ===")
    print("  start to start: median %.0f days, mean %.2f, p25 %.0f"
          % (gap.median(), gap.mean(), gap.quantile(.25)))
    from wpbl.engine import ENTRY_COST, RECOVERY
    for cap in (50, 70, 100):
        print("  capacity %3d needs %.1f days at E=%d, R=%d"
              % (cap, (ENTRY_COST + cap) / RECOVERY, ENTRY_COST, RECOVERY))


def main() -> None:
    league_rate()
    roles()
    wanted_or_forced()
    ceilings()
    rest()


if __name__ == "__main__":
    main()
