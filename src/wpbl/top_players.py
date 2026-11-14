"""Each team's ten most valuable players: runs above replacement over a 15-game season.

    pixi run top-players                 # the table
    pixi run top-players --raw           # no shrinkage
    pixi run top-players --boot 1000     # + game-resampling: P(top 10), intervals

Games: the 39 training games (regular season plus postseason, minus the
exhausted semifinal G3), for rates and for usage alike.

BATTERS
    rate      context-neutral linear-weights runs per PA (batters.py, errors
              credited, walks and HBP pooled as one free pass)
    PA        one league-wide number: one lineup spot, i.e. the league's team PA
              per 15 games divided by nine (user, 9 Nov; was the mean of each
              team's top-four batters' PA, which assumed a top 10 of six
              pitchers and four bats -- two-way players break that)
    running   steal runs per opportunity: her smoothed attempt rate
              (steal_ratings, K = 11) times the league run value of an attempt
              (success shows no per-runner spread), times her opportunities
              per PA, times the season PA
    replacement  pooled rate of the bottom X of league PA, players ordered by
              share of team PA while on the roster, averaged over cuts
              X +/- 2.5 points (one cut hinges on the two players at the line).
              X is the pitchers' X below, so both pools hold the same share of
              playing time (no natural break exists for batters)

PITCHERS
    rate      K + free-pass model. Her strikeout and free-pass (BB + HBP) rates
              are her own; every other plate appearance -- balls in play and
              home runs -- is priced at the league's average, because neither
              BABIP nor HR/BF shows per-pitcher spread beyond sampling noise in
              this season (chi-square ratio ~1, within team too). Valued per
              OUT: runs per BF over outs per BF under the same model, against
              replacement's runs per out
    usage     her actual outs, per 15 team games available; a one-outing
              pitcher keeps her actual outs (the team tried her once and moved on)
    replacement  pooled rates of every pitcher outside the regulars. Regular =
              top six on her team by share of team OUTS while on the roster,
              among pitchers with two or more outings. X = the share of league
              outs pitched by everyone else (~12%)

SHRINKAGE
    batters toward their usage group (regular or replacement), k = 50 PA;
    pitchers' K and free-pass rates toward a BF-weighted straight line in share
    of team outs, clamped between the replacement and regular means
    (k = 77 / 69 BF), so there is no step at the regular line
    (`--group-prior` restores the two-group target)

COMBINING
    one-way players take their one value; two-way players drop a negative side
    and sum what is left (both negative: the larger, i.e. less negative).

TEAM  the last team she appeared for.

RESAMPLING (--boot N)
    Games are drawn with replacement within strata -- each regular-season
    pairing (five games) and each postseason series -- so every team keeps its
    schedule. Each draw reruns everything above: the linear weights, both
    replacement pools and X, the season PA, the regulars, shrinkage, the
    two-way rule and the ranking. Held fixed: X at the user's 12.2% (else rare
    pitchers missing from a draw shrink it), the run-expectancy table behind
    each play's run value, the shrinkage constants, and each player's roster
    window. Shrinkage pins thin samples to their group, so their intervals
    describe the estimate's stability, not certainty about her talent.
"""
from __future__ import annotations

import sys
import time

import numpy as np
import pandas as pd
from scipy import stats

from wpbl import tables
from wpbl.batters import attributable, plate_appearances
from wpbl.markov import re_of, run_expectancy
from wpbl.parse import OUT_DIR
from wpbl.steal_ratings import K_ATTEMPT, events
from wpbl.usage_chart import CODES

SCOPE = "training"
SEASON_GAMES = 15
TOP_PA = None             # None: season PA = one lineup spot (team PA / 9, user 9 Nov);
                          # an int k: mean of each team's top-k batters' PA (old rule, k=4)
LINEUP = 9
TOP_PITCHERS = 6          # per team, by share of team outs on the roster (user, 8 Nov)
MIN_OUTINGS = 2           # a one-try pitcher can't be a regular and isn't scaled up
X_SPREAD = 0.025          # batter baseline averaged over cuts X +/- this (user, 8 Nov)
SMOOTH_PRIOR = "--group-prior" not in sys.argv   # pitcher shrinkage target: line in share (user, 8 Nov)
TOP_N = 10
POSTSEASON_FROM = "2026-09-07"
SEED = 20261108
# Shrinkage pseudo-counts, method of moments on these games (8 Nov): batter
# neutral runs/PA true SD ~0.09 against 0.63 per PA -> ~50 PA; pitcher K true
# SD 0.037 -> 77 BF; free pass 0.043 -> 69 BF. Each player shrinks toward her
# usage group (regular or replacement). `--raw` turns shrinkage off.
RAW = "--raw" in sys.argv
K_BAT, K_PK, K_PFP = (0.0, 0.0, 0.0) if RAW else (50.0, 77.0, 69.0)

# Availability overrides: date windows a player was unavailable, read by the user.
# Albayati batted through 21 Aug and returned to start semifinal G2 on 11 Sep
# (user's injury reading, 8 Nov): out for SFF's 7 games 22 Aug - 9 Sep.
UNAVAILABLE = {"Jill Albayati": ("2026-08-22", "2026-09-10")}
# Saiki: the lower of the roster-games and rotation-starts scale-ups (user, 8 Nov).
STARTS_CAPPED = {"Emi Saiki"}


# ======================================================================
# data: everything per game, loaded once
# ======================================================================

def load() -> dict:
    bat = tables.read("batting", SCOPE)
    pit = tables.read("pitching", SCOPE)
    bat["pa"] = bat[["ab", "bb", "hbp", "sf", "sh"]].sum(axis=1)
    for d in (bat, pit):
        d["team"] = d["team_name"].map(CODES)
    tg = bat.groupby(["team", "game_id"]).agg(date=("game_date", "first"), pa=("pa", "sum"))
    tg = tg.join(pit.groupby(["team", "game_id"])[["bf", "ip_outs"]].sum()).reset_index()

    # Roster windows: first to last appearance for that team, any role, minus
    # override windows. A fact about the roster, so fixed under resampling.
    span = bat.groupby(["person_id", "person_name", "team"])["game_date"].agg(["min", "max"]).reset_index()
    rows = []
    for r in span.itertuples():
        g = tg[(tg.team == r.team) & (tg.date >= r.min) & (tg.date <= r.max)]
        if r.person_name in UNAVAILABLE:
            lo, hi = (pd.Timestamp(d).date() for d in UNAVAILABLE[r.person_name])
            g = g[(g.date < lo) | (g.date > hi)]
        rows += [(r.person_id, r.team, gid) for gid in g.game_id]
    avail = pd.DataFrame(rows, columns=["person_id", "team", "game_id"]).merge(
        tg[["team", "game_id", "pa", "bf", "ip_outs"]], on=["team", "game_id"])
    last_team = span.sort_values("max").groupby("person_id").last()["team"]

    pas = attributable(plate_appearances(SCOPE), "credit", "pool")[
        ["person_id", "game_id", "outcome", "run_value"]]

    plays = tables.read("plays", SCOPE).sort_values(["game_id", "sequence"])
    plays = plays[plays.outs_before < 3].copy()
    plays["bases"] = (plays.first_base.notna().map({True: "1", False: "_"})
                      + plays.second_base.notna().map({True: "2", False: "_"})
                      + plays.third_base.notna().map({True: "3", False: "_"}))
    re_t = run_expectancy()
    steals = []
    for _, half in plays.groupby(["game_id", "inning", "half"], sort=False):
        rec = list(half.itertuples())
        for i, pl in enumerate(rec):
            if pl.event_type in ("stolen_base", "caught_stealing"):
                nxt = rec[i + 1] if i + 1 < len(rec) else None
                after = re_of(re_t, nxt.bases, int(nxt.outs_before)) if nxt is not None else 0.0
                steals.append((pl.game_id, after + pl.runs_scored
                               - re_of(re_t, pl.bases, int(pl.outs_before))))
    steals = pd.DataFrame(steals, columns=["game_id", "value"])
    opps = events()[0][["game_id", "person_id", "attempt"]].copy()
    opps["attempt"] = opps["attempt"].astype(float)

    # Strata: each regular-season pairing, and each postseason series.
    pairs = tg.groupby("game_id").agg(teams=("team", lambda s: "-".join(sorted(s))),
                                      date=("date", "first"))
    post = pairs.date >= pd.Timestamp(POSTSEASON_FROM).date()
    pairs["stratum"] = pairs.teams + np.where(post, " post", " reg")

    return dict(bat=bat[["person_id", "team", "game_id", "pa"]],
                pit=pit[["person_id", "team", "game_id", "bf", "ip_outs", "so", "bb",
                         "hbp", "gs", "r"]],
                tg=tg, avail=avail, last_team=last_team, pas=pas, steals=steals,
                opps=opps, strata=pairs.stratum,
                names=bat.drop_duplicates("person_id").set_index("person_id")["person_name"])


# ======================================================================
# the rating, for any per-game weighting
# ======================================================================

def evaluate(D: dict, w: pd.Series, X_fixed: float | None = None) -> tuple[pd.DataFrame, dict]:
    """Ratings with game g counted w[g] times (all ones = the real season).
    X_fixed holds the playing-time cut at the user's chosen value; resampling
    otherwise drops rare one- and two-outing pitchers from some draws, which
    shrinks X (12.2% -> ~10.9% on average) and drags the batter baseline down."""
    def wt(df):
        return df.game_id.map(w).fillna(0.0).to_numpy()
    names = D["names"]

    # availability under this weighting
    av = D["avail"].assign(wt=wt(D["avail"]))
    for c in ("pa", "bf", "ip_outs"):
        av[c] = av[c] * av.wt
    av = av.groupby(["person_id", "team"]).agg(games=("wt", "sum"), team_pa=("pa", "sum"),
                                                team_bf=("bf", "sum"),
                                                team_outs=("ip_outs", "sum")).reset_index()

    # ---------------- pitcher usage: regulars and X ----------------
    P = D["pit"].assign(wt=wt(D["pit"]))
    P = P[P.wt > 0]
    for c in ("bf", "ip_outs", "so", "bb", "hbp", "gs", "r"):
        P[c] = P[c] * P.wt
    pg = (P.groupby(["person_id", "team"])
          .agg(bf=("bf", "sum"), outs=("ip_outs", "sum"), so=("so", "sum"), bb=("bb", "sum"),
               hbp=("hbp", "sum"), gs=("gs", "sum"), r=("r", "sum"),
               outings=("game_id", "nunique"))      # a repeated game is still one try
          .reset_index().merge(av, on=["person_id", "team"]))
    pg = pg[(pg.bf > 0) & (pg.team_outs > 0)].copy()
    pg["share"] = pg.outs / pg.team_outs
    outings = pg.groupby("person_id")["outings"].sum()
    eligible = pg.person_id.map(outings) >= MIN_OUTINGS
    pg["rank"] = np.nan
    pg.loc[eligible, "rank"] = (pg[eligible].groupby("team")["share"]
                                .rank(ascending=False, method="first"))
    regular_ids = set(pg[pg["rank"] <= TOP_PITCHERS].person_id)
    X = 1 - pg[pg.person_id.isin(regular_ids)].outs.sum() / pg.outs.sum()
    if X_fixed is not None:
        X = X_fixed

    # ---------------- linear weights ----------------
    V = D["pas"].assign(wt=wt(D["pas"]))
    V = V[V.wt > 0].copy()
    V["wrv"] = V.run_value * V.wt
    by_out = V.groupby("outcome")[["wrv", "wt"]].sum()
    weights = by_out.wrv / by_out.wt
    V["neutral"] = V.outcome.map(weights)
    V["wn"] = V.neutral * V.wt

    # ---------------- batters ----------------
    B = D["bat"].assign(wt=wt(D["bat"]))
    B["pa"] = B.pa * B.wt
    u = B.groupby(["person_id", "team"])["pa"].sum().reset_index().merge(av, on=["person_id", "team"])
    u = u[(u.pa > 0) & (u.games > 0)].copy()
    u["share"] = u.pa / u.team_pa
    u["pa15"] = u.pa * SEASON_GAMES / u.games
    u["rank"] = u.groupby("team")["share"].rank(ascending=False, method="first").astype(int)
    if TOP_PA is None:
        tg = D["tg"].assign(wt=wt(D["tg"]))
        tg["wpa"] = tg.pa * tg.wt
        t = tg.groupby("team")[["wpa", "wt"]].sum()
        season_pa = t.wpa / t.wt * SEASON_GAMES / LINEUP
        PA = t.wpa.sum() / t.wt.sum() * SEASON_GAMES / LINEUP
    else:
        season_pa = u[u["rank"] <= TOP_PA].groupby("team")["pa15"].mean()
        PA = season_pa.mean()
    bs = u.groupby("person_id").agg(pa=("pa", "sum"), share=("share", "max")).sort_values("share")
    cum = bs.pa.cumsum() / bs.pa.sum()
    below = cum <= X
    repl_b = set(bs.index[below])
    b_line = (bs.share[below].max(), bs.share[~below].min())

    per = V.groupby("person_id")[["wt", "wn"]].sum().rename(columns={"wt": "pa", "wn": "total"})
    grid = np.linspace(X - X_SPREAD, X + X_SPREAD, 11)

    def pool_rate(ids):
        q = per[per.index.isin(ids)]
        return q.total.sum() / q.pa.sum()
    pool_rates = [pool_rate(bs.index[cum <= x]) for x in grid]
    repl_rate = float(np.mean(pool_rates))
    reg = per[~per.index.isin(repl_b)]
    reg_rate = reg.total.sum() / reg.pa.sum()
    rates = per.copy()
    prior = np.where(rates.index.isin(repl_b), repl_rate, reg_rate)
    rates["raw_rate"] = rates.total / rates.pa
    rates["rate"] = (rates.total + K_BAT * prior) / (rates.pa + K_BAT)

    # running
    S = D["steals"].assign(wt=wt(D["steals"]))
    per_attempt = (S.value * S.wt).sum() / S.wt.sum()
    O = D["opps"].assign(wt=wt(D["opps"]))
    O["att"] = O.attempt * O.wt
    run = O.groupby("person_id").agg(opps=("wt", "sum"), att=("att", "sum"))
    league_att = run.att.sum() / run.opps.sum()
    run["att_rate"] = (run.att + K_ATTEMPT * league_att) / (run.opps + K_ATTEMPT)
    rr = run[run.index.isin(repl_b)]
    repl_att = rr.att.sum() / rr.opps.sum()
    rates = rates.join(run[["opps", "att_rate"]]).fillna({"opps": 0, "att_rate": league_att})
    rates["opp_per_pa"] = rates.opps / rates.pa
    rates["run_rate"] = (rates.att_rate - repl_att) * per_attempt * rates.opp_per_pa
    rates["bat_runs"] = (rates.rate - repl_rate) * PA
    rates["base_runs"] = rates.run_rate * PA
    rates["batting"] = rates.bat_runs + rates.base_runs

    # ---------------- pitchers ----------------
    w_k, w_fp = weights["strikeout"], weights["free_pass"]
    other = V[~V.outcome.isin(["strikeout", "free_pass"])]
    w_other = other.wrv.sum() / other.wt.sum()
    pp = pg.groupby("person_id").agg(bf=("bf", "sum"), outs=("outs", "sum"), so=("so", "sum"),
                                     bb=("bb", "sum"), hbp=("hbp", "sum"), gs=("gs", "sum"),
                                     games=("games", "sum"), outings=("outings", "sum"),
                                     share=("share", "max"))
    rp = pp[~pp.index.isin(regular_ids)]
    rg = pp[pp.index.isin(regular_ids)]
    k_r, fp_r = rp.so.sum() / rp.bf.sum(), (rp.bb.sum() + rp.hbp.sum()) / rp.bf.sum()
    k_g, fp_g = rg.so.sum() / rg.bf.sum(), (rg.bb.sum() + rg.hbp.sum()) / rg.bf.sum()

    def allowed(k, fp):
        return k * w_k + fp * w_fp + (1 - k - fp) * w_other
    repl_allowed = allowed(k_r, fp_r)
    isreg = pp.index.isin(regular_ids)
    pp["raw_k"] = pp.so / pp.bf
    pp["raw_fp"] = (pp.bb + pp.hbp) / pp.bf
    if SMOOTH_PRIOR:
        # Shrinkage target = a BF-weighted straight line in her share of team
        # outs. The two-group target jumped at the regular line (a fringe arm
        # crossing it went from walks .263 to .143 and her value 4-5x); the line
        # meets both group means at the ends with no step. k is NOT re-fit around
        # the line: free-pass k would rise 69 -> 133 (541 on log share), letting
        # usage rather than her record set her rate, and value = rate x usage.
        Xs = np.c_[np.ones(len(pp)), pp.share.to_numpy()]
        Wt = pp.bf.to_numpy()
        A = Xs.T @ (Xs * Wt[:, None])
        k_target = Xs @ np.linalg.solve(A, Xs.T @ (Wt * pp.raw_k.to_numpy()))
        fp_target = Xs @ np.linalg.solve(A, Xs.T @ (Wt * pp.raw_fp.to_numpy()))
        # Clamped between the two group means (user, 8 Nov): the line only fills
        # the gap between replacement and regular. Unclamped it kept falling for
        # the busiest arms (Schiano's walk target .086 against a regular mean of
        # .143), crediting usage itself -- counted twice, as value = rate x usage.
        k_target = np.clip(k_target, min(k_r, k_g), max(k_r, k_g))
        fp_target = np.clip(fp_target, min(fp_r, fp_g), max(fp_r, fp_g))
    else:
        k_target, fp_target = np.where(isreg, k_g, k_r), np.where(isreg, fp_g, fp_r)
    pp["k_target"], pp["fp_target"] = k_target, fp_target
    pp["k"] = (pp.so + K_PK * k_target) / (pp.bf + K_PK)
    pp["fp"] = (pp.bb + pp.hbp + K_PFP * fp_target) / (pp.bf + K_PFP)
    pp["saved_per_bf"] = repl_allowed - allowed(pp.k, pp.fp)

    # Per OUT, not per BF: a team gives a pitcher innings, and an efficient
    # pitcher covers them with fewer batters. Under the K + free-pass model her
    # outs per BF are her K rate plus her other PAs at the league's outs per
    # non-K, non-free-pass PA (her own ball-in-play luck stays out, as in the
    # rate), and her runs per BF are the league's plus her linear-weight
    # difference from the league.
    lg_bf, lg_k = P.bf.sum(), P.so.sum()
    lg_fp = P.bb.sum() + P.hbp.sum()
    r_lg = P.r.sum() / lg_bf
    o_other = (P.ip_outs.sum() - lg_k) / (lg_bf - lg_k - lg_fp)
    lg_allowed = allowed(lg_k / lg_bf, lg_fp / lg_bf)

    def runs_per_out(k, fp):
        return (r_lg + allowed(k, fp) - lg_allowed) / (k + (1 - k - fp) * o_other)
    repl_rpo = runs_per_out(k_r, fp_r)
    pp["saved_per_out"] = repl_rpo - runs_per_out(pp.k, pp.fp)
    pp["outs_per_bf"] = pp.outs / pp.bf

    scale = np.where(pp.outings >= MIN_OUTINGS, SEASON_GAMES / pp.games, 1.0)
    pp["bf15"] = pp.bf * scale
    pp["outs15"] = pp.outs * scale
    pg["gs15"] = pg.gs * SEASON_GAMES / pg.games
    max_gs15 = pg[eligible].gs15.max()
    for pid in pp.index:
        if names.get(pid) in STARTS_CAPPED and pp.at[pid, "gs"] > 0:
            alt = pp.at[pid, "outs"] / pp.at[pid, "gs"] * max_gs15
            pp.at[pid, "outs15_roster"] = pp.at[pid, "outs15"]
            pp.at[pid, "outs15_starts"] = alt
            if alt < pp.at[pid, "outs15"]:
                pp.at[pid, "bf15"] *= alt / pp.at[pid, "outs15"]
                pp.at[pid, "outs15"] = alt
    pp["ip15"] = pp.outs15 / 3
    pp["per_bf_runs"] = pp.saved_per_bf * pp.bf15
    pp["pitching"] = pp.saved_per_out * pp.outs15

    # ---------------- combine ----------------
    out = pd.DataFrame(index=sorted(set(rates.index) | set(pp.index)))
    out["name"] = out.index.map(names)
    out["team"] = out.index.map(D["last_team"])
    out = out.join(rates[["pa", "raw_rate", "rate", "bat_runs", "base_runs", "batting"]])
    out = out.join(pp[["bf", "bf15", "ip15", "outs_per_bf", "raw_k", "k", "raw_fp", "fp",
                       "k_target", "fp_target",
                       "saved_per_bf", "saved_per_out", "per_bf_runs", "pitching"]])
    out["regular_p"] = out.index.isin(regular_ids)
    out["repl_b"] = out.index.isin(repl_b)
    b, p = out.batting.to_numpy(), out.pitching.to_numpy()
    both = ~np.isnan(b) & ~np.isnan(p)
    pos = np.where(b > 0, b, 0) + np.where(p > 0, p, 0)
    out["runs"] = np.where(both, np.where((b > 0) | (p > 0), pos, np.fmax(b, p)),
                           np.where(np.isnan(b), p, b))

    info = dict(PA=PA, season_pa=season_pa, X=X, b_line=b_line, grid=grid, pool_rates=pool_rates,
                repl_rate=repl_rate, reg_rate=reg_rate, repl_b=repl_b,
                repl_pa=float(per[per.index.isin(repl_b)].pa.sum()),
                single_cut=pool_rate(repl_b), league_rate=V.wn.sum() / V.wt.sum(),
                league_att=league_att, repl_att=repl_att, per_attempt=per_attempt,
                n_steals=float(S.wt.sum()), w_k=w_k, w_fp=w_fp, w_other=w_other,
                pg=pg, pp=pp, regular_ids=regular_ids, rp=rp, rg=rg, k_r=k_r, fp_r=fp_r,
                k_g=k_g, fp_g=fp_g, repl_allowed=repl_allowed, allowed=allowed,
                max_gs15=max_gs15, r_lg=r_lg, o_other=o_other, repl_rpo=repl_rpo)
    return out, info


# ======================================================================
# reporting
# ======================================================================

def heterogeneity(x: np.ndarray, n: np.ndarray) -> tuple[float, int, float]:
    p = x.sum() / n.sum()
    chi = float(((x - n * p) ** 2 / (n * p * (1 - p))).sum())
    return chi, len(x) - 1, stats.chi2.sf(chi, len(x) - 1)


def report(D: dict, out: pd.DataFrame, I: dict) -> None:
    names, tg, pg, pp = D["names"], D["tg"], I["pg"], I["pp"]
    print(f"games: {SCOPE} ({tg.game_id.nunique()} games); team games {tg.groupby('team').size().to_dict()}")
    print("\n=== BATTERS ===")
    rule = (f"one lineup spot (team PA / {LINEUP})" if TOP_PA is None
            else f"mean over teams of top-{TOP_PA} PA")
    print(f"season PA = {rule} per {SEASON_GAMES} games: "
          + ", ".join(f"{t} {v:.1f}" for t, v in I["season_pa"].items()) + f"  ->  {I['PA']:.1f}")
    print(f"X = {I['X']:.1%} of league outs outside each team's top {TOP_PITCHERS}; batter line at "
          f"share of team PA {I['b_line'][0]:.3f} | {I['b_line'][1]:.3f}")
    print("batter pool rate by cut: " + "  ".join(f"{x:.1%} {r:+.3f}" for x, r in zip(I["grid"], I["pool_rates"]))
          + f"  -> mean {I['repl_rate']:+.4f} (single cut at X: {I['single_cut']:+.4f})")
    print(f"replacement batters: {len(I['repl_b'])} players, {I['repl_pa']:.0f} PA, {I['repl_rate']:+.4f} runs/PA; "
          f"regulars {I['reg_rate']:+.4f}; league {I['league_rate']:+.4f}"
          f"  -> a regular-average bat is worth {(I['reg_rate'] - I['repl_rate']) * I['PA']:+.1f} runs")
    print(f"shrinkage: batters k={K_BAT:.0f} PA, pitchers K k={K_PK:.0f} / FP k={K_PFP:.0f} BF"
          f"{'  (RAW: off)' if RAW else ''}")
    print(f"steals: league attempt {I['league_att']:.3f}/opp, replacement {I['repl_att']:.3f}/opp, "
          f"{I['per_attempt']:+.3f} runs per attempt ({I['n_steals']:.0f} attempts)")

    print("\n=== PITCHERS ===")
    print(f"weights: K {I['w_k']:+.3f}  free pass {I['w_fp']:+.3f}  everything else {I['w_other']:+.3f}")
    for t, g in pg[pg.person_id.isin(I["regular_ids"])].sort_values("rank").groupby("team"):
        print(f"  regulars {t}: " + ", ".join(f"{names[i]} {s:.3f}" for i, s in zip(g.person_id, g.share)))
    single = pp[pp.outings < MIN_OUTINGS]
    print("  one-outing (replacement, not scaled): "
          + ", ".join(f"{names[i]} {int(b)} BF" for i, b in single.bf.items()))
    rp, rg, allowed = I["rp"], I["rg"], I["allowed"]
    print(f"replacement pitchers: {len(rp)} players, {int(rp.bf.sum())} BF, K {I['k_r']:.3f}  "
          f"FP {I['fp_r']:.3f}  ->  {I['repl_allowed']:+.4f} runs/BF")
    print(f"regular pitchers: {len(I['regular_ids'])} players, {int(rg.bf.sum())} BF, K {I['k_g']:.3f}  "
          f"FP {I['fp_g']:.3f}  ->  {allowed(I['k_g'], I['fp_g']):+.4f} runs/BF")
    q = pp[pp.bf >= 40]
    for lab, x in (("BB/BF", q.bb), ("HBP/BF", q.hbp), ("BB+HBP/BF", q.bb + q.hbp), ("K/BF", q.so)):
        chi, dof, pv = heterogeneity(x.values, q.bf.values)
        print(f"  spread check {lab:10s} chi2/df {chi / dof:.2f}  p={pv:.3f}  ({len(q)} pitchers, 40+ BF)")
    for pid in pp.index[pp.index.map(names).isin(STARTS_CAPPED)]:
        r = pp.loc[pid]
        print(f"  {names[pid]}: roster scale {r.outs15_roster / 3:.1f} IP, starts scale "
              f"{r.outs15_starts / 3:.1f} IP (max {I['max_gs15']:.1f} starts/15 g)  -> {r.ip15:.1f}")
    print(f"per-out model: league {I['r_lg']:.3f} runs/BF, {I['o_other']:.3f} outs per non-K non-FP PA; "
          f"replacement {I['repl_rpo'] * 21:.2f} runs per 7 IP")

    print("\n=== TOP 10 PER TEAM (runs above replacement, 15 games) ===")
    cols = ["name", "pa", "raw_rate", "rate", "bat_runs", "base_runs", "bf", "ip15",
            "raw_k", "k", "raw_fp", "fp", "pitching", "runs"]
    f3 = lambda x: "" if pd.isna(x) else f"{x:.3f}"
    s3 = lambda x: "" if pd.isna(x) else f"{x:+.3f}"
    f1 = lambda x: "" if pd.isna(x) else f"{x:+.1f}"
    f0 = lambda x: "" if pd.isna(x) else f"{x:.0f}"
    fmt = {"raw_rate": s3, "rate": s3, "raw_k": f3, "k": f3, "raw_fp": f3, "fp": f3,
           "bat_runs": f1, "base_runs": f1, "pitching": f1, "runs": f1,
           "pa": f0, "bf": f0, "ip15": lambda x: "" if pd.isna(x) else f"{x:.1f}"}
    for t, g in out.groupby("team"):
        g = g.sort_values("runs", ascending=False)
        print(f"\n{t}  ({len(g)} players appeared; top 10 sum {g.runs.head(TOP_N).sum():+.1f})")
        print(g[cols].head(TOP_N + 3).to_string(index=False, formatters=fmt, na_rep=""))
    path = OUT_DIR.parent / "top_players.csv"
    out.sort_values(["team", "runs"], ascending=[True, False]).to_csv(path)
    print(f"\nwrote {path}")


# ======================================================================
# resampling
# ======================================================================

def draw(strata: pd.Series, rng) -> pd.Series:
    """Per-game multiplicities: within each stratum, as many games as it holds,
    drawn with replacement."""
    counts = pd.Series(0.0, index=strata.index)
    for _, games in strata.groupby(strata):
        picks = rng.choice(games.index.to_numpy(), size=len(games), replace=True)
        for g in picks:
            counts[g] += 1
    return counts


def bootstrap(D: dict, base: pd.DataFrame, n: int, X: float) -> None:
    rng = np.random.default_rng(SEED)
    runs = np.full((len(base), n), np.nan)
    top = np.zeros((len(base), n), dtype=bool)
    rank = np.full((len(base), n), np.nan)
    idx = {pid: i for i, pid in enumerate(base.index)}
    t0 = time.time()
    for b in range(n):
        out, _ = evaluate(D, draw(D["strata"], rng), X_fixed=X)
        out = out.dropna(subset=["runs"])
        out["rk"] = out.groupby("team")["runs"].rank(ascending=False, method="first")
        rows = [idx[p] for p in out.index]
        runs[rows, b] = out.runs.to_numpy()
        rank[rows, b] = out.rk.to_numpy()
        top[rows, b] = (out.rk <= TOP_N).to_numpy()
        if b in (0, 9, 49) or (b + 1) % 100 == 0:
            print(f"  draw {b + 1}/{n}  {time.time() - t0:.0f}s", flush=True)
    present = ~np.isnan(runs)
    res = base[["name", "team", "runs"]].copy()
    res["base_rank"] = base.groupby("team")["runs"].rank(ascending=False, method="first")
    res["present"] = present.mean(axis=1)
    res["p_top10"] = top.sum(axis=1) / n          # absent from a draw = not in its top 10
    with np.errstate(all="ignore"):
        res["lo"] = np.nanpercentile(runs, 5, axis=1)
        res["median"] = np.nanmedian(runs, axis=1)
        res["hi"] = np.nanpercentile(runs, 95, axis=1)
        res["rank_lo"] = np.nanpercentile(rank, 5, axis=1)
        res["rank_hi"] = np.nanpercentile(rank, 95, axis=1)
    print(f"\n=== RESAMPLING: {n} draws, games within strata, X held at {X:.1%} "
          f"({time.time() - t0:.0f}s) ===")
    print("  runs: 90% interval;  rank: 90% interval within team;  P(top 10) over all draws")
    for t, g in res.groupby("team"):
        # Ranked by the point estimate; P(top 10) is how settled the place is.
        # Not ranked by P: fringe arms' long upper tails (draws where they cross
        # into the regulars) lift their P above better-rated players (user, 8 Nov).
        g = g.sort_values("runs", ascending=False).head(TOP_N + 2)
        print(f"\n{t}  (expected top-10 places filled by these players: {g.p_top10.sum():.1f})")
        show = g.assign(
            runs=g.runs.map("{:+.1f}".format),
            interval=[f"[{a:+5.1f}, {c:+5.1f}]" for a, c in zip(g.lo, g.hi)],
            rank=[f"{int(r)}" for r in g.base_rank],
            rank90=[f"{int(a)}-{int(c)}" for a, c in zip(g.rank_lo, g.rank_hi)],
            P=g.p_top10.map("{:.2f}".format))
        print(show[["name", "runs", "interval", "rank", "rank90", "P"]].to_string(index=False))
    path = OUT_DIR.parent / "top_players_boot.csv"
    res.sort_values(["team", "runs"], ascending=[True, False]).to_csv(path)
    print(f"\nwrote {path}")


def main() -> None:
    pd.set_option("display.width", 220)
    pd.set_option("display.max_rows", 300)
    D = load()
    w = pd.Series(1.0, index=D["strata"].index)
    out, info = evaluate(D, w)
    report(D, out, info)
    if "--boot" in sys.argv:
        n = int(sys.argv[sys.argv.index("--boot") + 1])
        bootstrap(D, out.dropna(subset=["runs"]), n, info["X"])


if __name__ == "__main__":
    main()
