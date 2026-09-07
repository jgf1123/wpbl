"""Analysis 2b: conditioned on a change, who comes in.

    pixi run relievers

Two questions. Does the leverage a reliever is brought into track how good she
is? And are the pitchers a manager reaches for in tight spots the same ones the
rate stats say are best?

Quality is measured two ways, both deliberately leverage-neutral:

    RE24 per batter faced -- the expected-runs value of what she allowed,
        which knows the base-out state but not the score or the inning
    WHIP -- baserunners per inning, the plainest control measure

Win probability added is *not* used, though it exists in this project. It is
leverage-weighted by construction, so ranking pitchers by it and then asking
whether managers use the good ones in high leverage is circular.

Both come with bootstrap confidence intervals, resampled over the batters each
pitcher actually faced. At four to twenty innings apiece the point estimates
are far less informative than their width, and a ranking that ignores the
width is mostly ranking noise.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.game_timeline import pooled_run_expectancy, re_of
from wpbl.leverage import Leverage
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

BOOTSTRAP = 4000
MIN_BF = 20        # below this the interval is too wide to rank on at all
SEED = 20260901


def batter_values() -> pd.DataFrame:
    """Every batter faced, with the run value of the outcome charged to the
    pitcher, plus whether the batter reached (for WHIP)."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    people = pd.read_parquet(OUT_DIR / "players.parquet").set_index("player_id")["person_name"]
    re_table = pooled_run_expectancy()

    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["pitching_team_id", "pitcher_id"])
            .sort_values(["game_id", "sequence"]).copy())
    live["bases"] = (live["first_base"].notna().map({True: "1", False: "_"})
                     + live["second_base"].notna().map({True: "2", False: "_"})
                     + live["third_base"].notna().map({True: "3", False: "_"}))

    rows = []
    for _, half in live.groupby(["game_id", "inning", "half"], sort=False):
        half = half.sort_values("sequence")
        records = list(half.itertuples())
        for i, play in enumerate(records):
            if not play.is_plate_appearance:
                continue
            nxt = records[i + 1] if i + 1 < len(records) else None
            after = (re_of(re_table, nxt.bases, int(nxt.outs_before)) if nxt is not None else 0.0)
            before = re_of(re_table, play.bases, int(play.outs_before))
            rows.append({
                "pitcher_id": play.pitcher_id,
                "pitcher": people.get(play.pitcher_id, play.pitcher_name),
                "team": play.pitching_team_id,
                # Positive means the batting team gained, so a good pitcher is
                # negative; flipped below so higher is better for the pitcher.
                "run_value": after + play.runs_scored - before,
                "reached": bool(play.is_hit) or play.event_type in ("walk", "hit_by_pitch"),
            })
    return pd.DataFrame(rows)


def bootstrap_rates(values: pd.DataFrame, outs: int, rng) -> dict:
    """Resample the batters faced to get intervals on both rate stats."""
    n = len(values)
    rv = values["run_value"].to_numpy()
    reached = values["reached"].to_numpy().astype(float)
    innings = outs / 3

    idx = rng.integers(0, n, size=(BOOTSTRAP, n))
    re_draws = -rv[idx].mean(axis=1)                        # higher = better
    # WHIP scales the resampled reach rate onto the innings she actually threw.
    whip_draws = reached[idx].mean(axis=1) * n / innings if innings else np.full(BOOTSTRAP, np.nan)
    return {
        "re24_per_bf": -rv.mean(),
        "re24_lo": np.percentile(re_draws, 2.5),
        "re24_hi": np.percentile(re_draws, 97.5),
        "whip": reached.mean() * n / innings if innings else np.nan,
        "whip_lo": np.percentile(whip_draws, 2.5),
        "whip_hi": np.percentile(whip_draws, 97.5),
    }


def entries(lev: Leverage) -> pd.DataFrame:
    """Every pitching change, with the leverage the incoming pitcher inherited."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    people = pd.read_parquet(OUT_DIR / "players.parquet").set_index("player_id")["person_name"]
    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["pitching_team_id", "pitcher_id"])
            .sort_values(["game_id", "sequence"]))
    faced = live[live["is_plate_appearance"]]

    rows = []
    for (game_id, team_id), side in faced.groupby(["game_id", "pitching_team_id"]):
        previous_last = None
        for (inning, half), half_block in side.groupby(["inning", "half"], sort=False):
            half_block = half_block.sort_values("sequence")
            order = list(dict.fromkeys(half_block["pitcher_id"]))
            for position, pitcher_id in enumerate(order):
                entry = half_block[half_block["pitcher_id"] == pitcher_id].iloc[0]
                mid = position > 0
                if not mid and (previous_last is None or pitcher_id == previous_last):
                    continue        # game opener, or simply carrying on
                bases = (("1" if pd.notna(entry["first_base"]) else "_")
                         + ("2" if pd.notna(entry["second_base"]) else "_")
                         + ("3" if pd.notna(entry["third_base"]) else "_"))
                diff = int(entry["home_score_before"] - entry["away_score_before"])
                rows.append({
                    "game_id": game_id, "team": team_id,
                    "pitcher_id": pitcher_id, "pitcher": people.get(pitcher_id, pitcher_id),
                    "inning": inning, "half": half, "mid_inning": mid,
                    "li": lev.state(inning, half, int(entry["outs_before"]), bases, diff),
                    "lead": diff if half == "top" else -diff,
                })
            previous_last = order[-1]
    return pd.DataFrame(rows)


def main() -> None:
    pd.set_option("display.width", 250)
    rng = np.random.default_rng(SEED)
    lev = Leverage()

    values = batter_values()
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    outs = pitching.groupby("person_id")["ip_outs"].sum()
    teams = pitching.groupby("person_id")["team_name"].last()

    quality = []
    for pid, group in values.groupby("pitcher_id"):
        if pid not in outs.index or len(group) < MIN_BF:
            continue
        stats = bootstrap_rates(group, int(outs[pid]), rng)
        quality.append({"pitcher_id": pid, "pitcher": group["pitcher"].iloc[0],
                        "tm": CODES.get(teams.get(pid), "?"),
                        "bf": len(group), "ip": round(outs[pid] / 3, 1), **stats})
    q = pd.DataFrame(quality)

    print(f"=== quality with bootstrap intervals ({BOOTSTRAP} resamples over batters faced) ===")
    print(f"    {len(q)} pitchers with at least {MIN_BF} batters faced\n")
    show = q.sort_values("re24_per_bf", ascending=False)
    print("  RE24 per batter faced -- runs prevented relative to the base-out state")
    print("  (higher is better; the interval is what matters at these samples)\n")
    for r in show.itertuples():
        width = r.re24_hi - r.re24_lo
        print(f"   {r.tm} {r.pitcher:22s} {r.ip:5.1f} IP {r.bf:4d} BF   "
              f"RE24/BF {r.re24_per_bf:+.3f}  [{r.re24_lo:+.3f}, {r.re24_hi:+.3f}]  width {width:.3f}"
              f"    WHIP {r.whip:.2f}  [{r.whip_lo:.2f}, {r.whip_hi:.2f}]")

    overlap = ((show["re24_lo"] <= show["re24_hi"].max())
               & (show["re24_hi"] >= show["re24_lo"].min())).all()
    best, worst = show.iloc[0], show.iloc[-1]
    separated = best["re24_lo"] > worst["re24_hi"]
    print(f"\n  best and worst intervals {'do not overlap' if separated else 'OVERLAP'} "
          f"-- {'a real difference' if separated else 'not even the extremes are separable'}")

    e = entries(lev)
    print(f"\n\n=== {len(e)} pitching changes, by leverage inherited ===")
    print(e.groupby("mid_inning").agg(
        n=("li", "size"), mean_li=("li", "mean"), median_li=("li", "median"),
        max_li=("li", "max")).round(2).to_string())

    merged = e.merge(q[["pitcher_id", "pitcher", "tm", "re24_per_bf", "whip", "ip"]],
                     on="pitcher_id", how="inner", suffixes=("", "_q"))
    print(f"\n  {len(merged)} of those went to a pitcher with enough work to rate")

    print("\n=== does a higher-leverage call go to a better pitcher? ===")
    for label, col, sign in [("RE24 per BF", "re24_per_bf", 1), ("WHIP", "whip", -1)]:
        r = np.corrcoef(merged["li"], merged[col] * sign)[0, 1]
        # Bootstrap the correlation over the entry decisions themselves.
        draws = []
        idx_pool = np.arange(len(merged))
        for _ in range(BOOTSTRAP):
            take = rng.integers(0, len(merged), len(merged))
            draws.append(np.corrcoef(merged["li"].to_numpy()[take],
                                     (merged[col] * sign).to_numpy()[take])[0, 1])
        lo, hi = np.percentile(draws, [2.5, 97.5])
        print(f"  leverage vs {label:12s} (oriented so higher = better): "
              f"r = {r:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]")

    print("\n=== manager's revealed order: mean leverage each pitcher is called into ===")
    trust = (merged.groupby(["tm", "pitcher"])
             .agg(calls=("li", "size"), mean_li=("li", "mean"),
                  re24=("re24_per_bf", "first"), whip=("whip", "first"), ip=("ip", "first"))
             .reset_index().sort_values(["tm", "mean_li"], ascending=[True, False]))
    for tm, block in trust.groupby("tm"):
        print(f"\n  {tm}")
        for r in block.itertuples():
            print(f"    {r.pitcher:22s} {r.calls:2d} calls  mean LI {r.mean_li:.2f}   "
                  f"RE24/BF {r.re24:+.3f}  WHIP {r.whip:.2f}  ({r.ip} IP)")

    load_summary(pitching)
    conditional_choice(e, q, rng)




# ---------------------------------------------------------------------------
# Availability: was the better arm even callable?
#
# The correlation above treats every change as a free choice among the whole
# staff, which it is not. A manager reaches for someone because the incumbent
# is spent, and by then the best arms may already be used or resting. That
# depletion attenuates any leverage-quality relationship: "down the list" is
# forced, not chosen. The fix is to score each call against the pool that was
# actually available at that moment rather than against the roster.

# Rest is not a binary. A pitcher who threw 15 pitches two days ago is
# available in a way one who threw 70 yesterday is not, so recent workload is
# measured in pitches over rolling windows rather than as "did she appear".
RECENT_WINDOWS = (1, 3, 5)      # days back
TIRED_PITCHES = 40              # in the last 3 days; calibrated below


def recent_load(pitching: pd.DataFrame) -> pd.DataFrame:
    """Pitches thrown in the days preceding each team-game, per pitcher.

    Built for every pitcher on the staff at every one of her team's games --
    including games she did not appear in -- because the question is what her
    arm had absorbed at the moment the manager was choosing, whether or not
    she ended up being called.
    """
    team_games = (pd.read_parquet(OUT_DIR / "team_games.parquet")
                  [["team_id", "game_id", "game_date"]].drop_duplicates())
    team_games["game_date"] = pd.to_datetime(team_games["game_date"])
    work = pitching[["team_id", "game_id", "person_id", "pitches", "game_date"]].copy()
    work["game_date"] = pd.to_datetime(work["game_date"])

    debut = work.groupby(["team_id", "person_id"])["game_date"].min()
    rows = []
    for (team_id, game_id, date) in team_games.itertuples(index=False):
        staff = [pid for (t, pid), first in debut.items() if t == team_id and first <= date]
        prior = work[(work["team_id"] == team_id) & (work["game_date"] < date)]
        for pid in staff:
            mine = prior[prior["person_id"] == pid]
            row = {"team_id": team_id, "game_id": game_id, "person_id": pid}
            for window in RECENT_WINDOWS:
                since = date - pd.Timedelta(days=window)
                row[f"pitches_{window}d"] = float(
                    mine.loc[mine["game_date"] >= since, "pitches"].sum())
            rows.append(row)
    return pd.DataFrame(rows)


def availability(pitching: pd.DataFrame) -> tuple[dict, dict]:
    """(team, game) -> staff on hand, and -> those carrying a heavy recent load."""
    load = recent_load(pitching)
    staff, tired = {}, {}
    for (team_id, game_id), block in load.groupby(["team_id", "game_id"]):
        staff[(team_id, game_id)] = set(block["person_id"])
        tired[(team_id, game_id)] = set(
            block.loc[block["pitches_3d"] >= TIRED_PITCHES, "person_id"])
    return staff, tired


def load_summary(pitching: pd.DataFrame) -> None:
    """How much recent work a pitcher was carrying when she was actually used."""
    load = recent_load(pitching)
    used = pitching[["team_id", "game_id", "person_id"]].assign(used=True)
    merged = load.merge(used, on=["team_id", "game_id", "person_id"], how="left")
    merged["used"] = merged["used"].fillna(False)

    print("\n\n=== recent workload when a pitcher was available ===")
    print("    share of available pitchers who were used, by pitches thrown recently\n")
    for window in RECENT_WINDOWS:
        col = f"pitches_{window}d"
        band = pd.cut(merged[col], [-0.1, 0.1, 20, 40, 70, 9999],
                      labels=["none", "1-20", "21-40", "41-70", "71+"])
        table = merged.groupby(band, observed=True).agg(
            available=("used", "size"), used=("used", "sum"), rate=("used", "mean")).round(3)
        print(f"  pitches in the last {window} day(s):")
        print(table.to_string())
        print()


def conditional_choice(entries_frame: pd.DataFrame, quality: pd.DataFrame,
                       rng) -> None:
    """Rank each call against the arms that were actually available for it."""
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    staff, tired = availability(pitching)
    rated = quality.set_index("pitcher_id")

    used_so_far: dict = {}
    for (game_id, team_id), block in pitching.groupby(["game_id", "team_id"]):
        used_so_far[(game_id, team_id)] = list(
            block.sort_values("appear_order")["person_id"])

    rows = []
    for call in entries_frame.itertuples():
        pool = staff.get((call.team, call.game_id), set())
        order = used_so_far.get((call.game_id, call.team), [])
        already = set(order[:order.index(call.pitcher_id)]) if call.pitcher_id in order else set()
        for label, exclude in (("roster", already),
                               ("rested", already | tired.get((call.team, call.game_id), set()))):
            options = [p for p in (pool - exclude) if p in rated.index]
            if call.pitcher_id not in rated.index or len(options) < 2:
                continue
            values = rated.loc[options, "re24_per_bf"]
            chosen = rated.loc[call.pitcher_id, "re24_per_bf"]
            rows.append({"rule": label, "li": call.li,
                         "pct": float((values < chosen).mean()),
                         "options": len(options),
                         "pool_best": float(values.max() - chosen)})
    frame = pd.DataFrame(rows)

    print("\n\n=== conditioning on who was actually available ===")
    print("    percentile = where the pitcher chosen ranked among the callable arms\n")
    for rule, block in frame.groupby("rule"):
        r = np.corrcoef(block["li"], block["pct"])[0, 1]
        draws = [np.corrcoef(block["li"].to_numpy()[t], block["pct"].to_numpy()[t])[0, 1]
                 for t in (rng.integers(0, len(block), len(block)) for _ in range(BOOTSTRAP))]
        lo, hi = np.percentile(draws, [2.5, 97.5])
        label = ("staff minus those already used this game" if rule == "roster"
                 else f"also minus anyone with {TIRED_PITCHES}+ pitches in the last 3 days")
        print(f"  {label}")
        print(f"    n={len(block)}  mean options {block['options'].mean():.1f}  "
              f"mean percentile chosen {block['pct'].mean():.2f}")
        print(f"    corr(leverage, percentile) = {r:+.3f}  95% CI [{lo:+.3f}, {hi:+.3f}]\n")

    print("=== is the pool depleted when leverage is high? ===")
    roster = frame[frame["rule"] == "roster"]
    r = np.corrcoef(roster["li"], roster["options"])[0, 1]
    print(f"  corr(leverage, number of arms still available) = {r:+.3f}")
    band = pd.cut(roster["li"], [0, 0.75, 1.25, 99], labels=["low", "avg", "high"])
    print(roster.groupby(band, observed=True).agg(
        n=("li", "size"), mean_options=("options", "mean"),
        mean_pct=("pct", "mean"), gap_to_best=("pool_best", "mean")).round(2).to_string())


if __name__ == "__main__":
    main()
