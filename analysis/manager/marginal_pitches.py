"""What 30 pitches are worth: the marginal pitches of a 7-day window, and the
leverage they are thrown in (real 2026 games, postseason included).

    pixi run python analysis/manager/marginal_pitches.py

A warm-up spends 30 pitches some arm cannot throw later; in a busy stretch the
team's marginal arm throws them instead. So, for every team and every date it
played, take the plate appearances its pitchers faced in the 7 days ending that
date:

  quality    the pitcher's card, fading column: runs a league lineup scores per
             pitch (runs per inning / pitches per inning, exact chain)
  marginal   the window's 30 pitches from its weakest arms (by that quality)
  leverage   the leverage index at each plate appearance (leverage.py, mid-inning
             included; an average half-inning start = 1.00)

Cost of 30 pitches = 30 x (marginal quality - the window's average quality)
x the marginal pitches' leverage x win probability per run at leverage 1.
"""
import re
import unicodedata

import numpy as np
import pandas as pd

from wpbl import manager as M, play, tables
from wpbl.leverage import Leverage, half_inning_starts


WINDOW_DAYS, MARGINAL = 7, 30
BANDS = [0, 0.5, 1.0, 2.0, np.inf]
LABELS = ["<0.5", "0.5-1", "1-2", "2+"]


def norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore")
                  .decode().lower())


cards, wp = play.shared()
model = M.Model(cards, wp)
card_of = {norm(n): n for n in cards.pitcher}


def per_pitch(name):
    """Runs per pitch off her fading column, league lineup."""
    D, E = model.chain(name, "fading", (M.LEAGUE,) * 9)
    return float(D[0] @ np.arange(M.MAX_RUNS)) / float(E[0])


lev = Leverage()
plays = tables.read("plays", "all")
pa = plays[plays["is_plate_appearance"] & (plays["outs_before"] < 3)].dropna(
    subset=["pitching_team_id", "pitcher_name"]).copy()
pit = tables.read("pitching", "all")
team_name = pit.drop_duplicates("team_id").set_index("team_id")["team_name"]
code = {"Boston": "BOS", "Los Angeles": "LAQ", "New York": "NYH", "San Francisco": "SFF"}
pa["team"] = pa["pitching_team_id"].map(team_name).map(
    lambda t: next(v for k, v in code.items() if str(t).startswith(k)))
pa["card"] = pa["pitcher_name"].map(lambda n: card_of.get(norm(n)))
pa["pitches"] = pa["n_pitches"].where(pa["n_pitches"].notna() & (pa["n_pitches"] > 0),
                                      pa["n_pitches_est"]).astype(float)
bases = (pa["first_base"].notna().map({True: "1", False: "_"})
         + pa["second_base"].notna().map({True: "2", False: "_"})
         + pa["third_base"].notna().map({True: "3", False: "_"}))
diff = (pa["home_score_before"] - pa["away_score_before"]).astype(int)
pa["li"] = [lev.state(int(i), h, int(o), b, int(d)) for i, h, o, b, d in
            zip(pa["inning"], pa["half"], pa["outs_before"], bases, diff)]
pa["rv"] = [model.run_value(int(i), h == "top", int(o), [c != "_" for c in b], int(d)) for i, h, o, b, d in
            zip(pa["inning"], pa["half"], pa["outs_before"], bases, diff)]
pa["date"] = pd.to_datetime(pa["game_date"])
nocard = pa["card"].isna()
print(f"{len(pa)} plate appearances, {pa['pitches'].sum():.0f} pitches; "
      f"{nocard.sum()} by pitchers without a card ({', '.join(sorted(pa.loc[nocard, 'pitcher_name'].unique()))}), left out")
pa = pa[~nocard]
pa["q"] = pa["card"].map({n: per_pitch(n) for n in pa["card"].unique()})

# win probability per run at leverage 1: the average swing of one run over the
# season's half-inning starts, in the dice game's team-neutral model
starts = half_inning_starts()
swing = [(wp.top(r.inning, r.diff + 1) - wp.top(r.inning, r.diff - 1)) / 2 if r.half == "top"
         else (wp.bottom(r.inning, r.diff + 1) - wp.bottom(r.inning, r.diff - 1)) / 2
         for r in starts.itertuples() if r.inning <= 7]
wp_per_run = float(np.mean(swing))
print(f"win probability per run at an average half-inning start: {wp_per_run:.3f}\n")

rows, band_all, band_marg = [], [], []
for team, tp in pa.groupby("team"):
    for day in sorted(tp["date"].unique()):
        w = tp[(tp["date"] > day - pd.Timedelta(days=WINDOW_DAYS)) & (tp["date"] <= day)]
        w = w.sort_values("q", ascending=False)                 # weakest arms first
        take = np.minimum(w["pitches"].to_numpy(),
                          np.maximum(0, MARGINAL - (w["pitches"].cumsum() - w["pitches"]).to_numpy()))
        if take.sum() < MARGINAL:
            continue
        avg_q = float(np.average(w["q"], weights=w["pitches"]))
        mq = float(np.average(w["q"], weights=take))
        mli = float(np.average(w["li"], weights=take))
        mrv = float(np.average(w["rv"], weights=take))
        arms = w.loc[take > 0, "card"].unique()
        rows.append({"team": team, "date": day, "pitches": w["pitches"].sum(), "games": w["game_id"].nunique(),
                     "avg_q": avg_q, "marg_q": mq, "marg_li": mli, "marg_rv": mrv,
                     "all_rv": float(np.average(w["rv"], weights=w["pitches"])),
                     "all_li": float(np.average(w["li"], weights=w["pitches"])),
                     "arms": ", ".join(a.split()[-1] for a in arms)})
        band_all.append(pd.cut(w["li"], BANDS, labels=LABELS, right=False).value_counts(normalize=True))
        cut = pd.cut(w["li"], BANDS, labels=LABELS, right=False)
        band_marg.append(pd.Series(take, index=cut).groupby(level=0, observed=False).sum() / take.sum())

r = pd.DataFrame(rows)
r["cost_wp"] = MARGINAL * (r["marg_q"] - r["avg_q"]) * r["marg_li"] * wp_per_run
r["cost_rv"] = MARGINAL * (r["marg_q"] - r["avg_q"]) * r["marg_rv"] * model.run_scale
pd.set_option("display.width", 200)
print("per team, averaged over its windows (quality = runs per pitch, fading card, league lineup):")
summary = r.groupby("team").agg(windows=("date", "size"), games=("games", "mean"), pitches=("pitches", "mean"),
                                avg_q=("avg_q", "mean"), marg_q=("marg_q", "mean"),
                                all_li=("all_li", "mean"), marg_li=("marg_li", "mean"),
                                cost_wp=("cost_wp", "mean"), all_rv=("all_rv", "mean"),
                                marg_rv=("marg_rv", "mean"), cost_rv=("cost_rv", "mean"))
print(summary.round(4).to_string())
print(f"\nall windows: cost of 30 marginal pitches {100 * r['cost_wp'].mean():.2f} WP points "
      f"(median {100 * r['cost_wp'].median():.2f}, 10-90% {100 * r['cost_wp'].quantile(.1):.2f} to "
      f"{100 * r['cost_wp'].quantile(.9):.2f})")
print(f"run-value index (one run at an average start = {model.run_scale:.4f} WP): cost of 30 marginal "
      f"pitches {100 * r['cost_rv'].mean():.2f} WP points (median {100 * r['cost_rv'].median():.2f}, "
      f"10-90% {100 * r['cost_rv'].quantile(.1):.2f} to {100 * r['cost_rv'].quantile(.9):.2f})")
share2 = float((pa["li"] >= 2).mean())
print(f"\nplate appearances at spread index 2.0+: {100 * share2:.1f}%; the run-value index at the same "
      f"share: {pa['rv'].quantile(1 - share2):.2f}")
for q in (0.90, 0.95, 0.97):
    print(f"  run-value index, {int(100 * q)}th percentile of plate appearances: {pa['rv'].quantile(q):.2f}")
print("\nshare of pitches by leverage band, averaged over windows:")
print(pd.DataFrame({"all pitches": pd.concat(band_all, axis=1).mean(axis=1),
                    "marginal 30": pd.concat(band_marg, axis=1).mean(axis=1)}).round(3).to_string())
print("\nwho throws the marginal pitches (windows in which she does):")
arms = pd.Series(", ".join(r["arms"]).split(", ")).value_counts()
for team in sorted(r["team"].unique()):
    t_arms = pd.Series(", ".join(r.loc[r["team"] == team, "arms"]).split(", ")).value_counts().head(5)
    print(f"  {team}: " + ", ".join(f"{a} {c}" for a, c in t_arms.items()))
