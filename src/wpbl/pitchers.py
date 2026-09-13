"""Pitchers, two ways: runs charged, and runs the defence could not touch.

    pixi run pitchers

RE24 per batter faced is what she actually allowed, relative to the base-out
state she walked into. For a pitcher this is the right accounting almost
without adjustment, because her plate appearances are consecutive: the interior
run-expectancy terms cancel between one batter and the next, so her total comes
out close to runs allowed minus the expectancy she inherited on entry. That is
also why the thin cells in the run-expectancy table barely matter here -- the
whole table moving only shifts every pitcher by about 0.017, against a spread
across pitchers of 0.50.

There is no context-neutral column here, and the omission is deliberate. For a
batter the base-out state is exogenous: her team-mates put those runners on, so
removing the situation isolates her. For a pitcher it is largely her own doing
-- walk the leadoff hitter and the next batter bats with a runner on because of
her -- so stripping the situation out would strip out her own responsibility
for the traffic. The pitcher's exogenous contaminant is not the situation, it
is the defence, and the tool for that is FIP.


WHAT IS CHARGED
---------------

Plate appearances, plus the three loose plays that are unambiguously the
pitcher's own action, with no scorer judgement assigning them elsewhere: wild
pitches, balks, and pitcher pickoffs -- a runner retired on the bases on a
throw from the pitcher, which the narrative identifies as "out at X p to Y".

Deliberately NOT charged:

    stolen bases, and catcher-thrown caught stealing. Twelve of the season's
    fifteen caught stealings came on a throw from the catcher, three on a
    pitcher pickoff. Denae Benites caught all fifteen of New York's games and
    threw out 35% of runners against a league rate of 14%, so crediting caught
    stealing to pitchers would be crediting them for her arm. Both sides of the
    running game are therefore left out rather than misattributed.

    passed balls. A passed ball is, by the scorer's own definition, a ball the
    catcher should have handled -- the same reasoning that keeps the running
    game out. Charging them here while excluding caught stealing would have the
    scheme contradict itself: catcher-driven events are the catcher's on one
    line and the pitcher's on the next. There are only 7, but at -0.349 apiece
    they are the costliest of the loose plays per event, so the exclusion is
    not merely cosmetic. Note the wild-pitch-to-passed-ball ratio here is
    9.6:1 against roughly 2-3:1 in the majors, which makes a passed-ball call
    an unusual and deliberate judgement when a scorer does make one.

Before this, only plate appearances were charged and 32 real runs -- 7% of the
league's scoring -- belonged to nobody.


FIP
---

Fielding Independent Pitching keeps only outcomes no fielder can affect:
strikeouts, walks, hit batters, home runs. It exists because a pitcher's
results on balls in play swing far more than her strikeout and walk rates do,
so the balls in play are mostly telling you about her defence. That matters
here: 69% of the plate appearances charged to a pitcher are balls in play, in a
league committing 3.6 errors a game.

The weights are re-derived from this league rather than imported. Standard FIP
uses (13*HR + 3*(BB+HBP) - 2*K)/IP because those are roughly the MLB run values
of those events times nine. Games here are seven innings, so everything is
expressed per seven, and ours come out:

    HR 11.0,  BB+HBP 2.8,  K -3.8     (MLB's, rescaled to seven: 10.1, 2.3, -1.6)

The home-run and walk weights land near the familiar ones; the strikeout weight
is more than twice MLB's. That follows from the run environment. An average
plate appearance is worth far more in a league scoring ~5.9 earned runs per
seven, so retiring a batter without letting the ball in play prevents more.

The constant sets league FIP equal to league ERA, so the number reads on an ERA
scale. Note that league ERA is 5.92 while RA/7 is 8.16 -- the 2.24-run gap is
unearned runs, which is itself a defence story.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd

from wpbl.batters import neutral_values, plate_appearances
from wpbl.markov import re_of, run_expectancy
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

BOOTSTRAP = 4000
SEED = 20260908
MIN_BF = 40         # about six innings; the natural break in this season's workloads
INNINGS = 7        # per seven innings: the regulation game here, matching ERA

# Loose plays that are the pitcher's own action, not the fielders'. A balk is
# identified by play_kind, not event_type: the feed leaves every balk's
# event_type as "unknown" and only the parser's own classification records it.
# Filtering on event_type alone silently charged none of the season's 17.
PITCHER_PLAYS = {"wild_pitch"}
PITCHER_KINDS = {"balk"}

# A runner retired on the bases is only the pitcher's when the pitcher made the
# throw. Of the season's seven such plays, two are pitcher pickoffs and five
# are not: three catcher throws, one retired by the right fielder, and one
# baserunner interference. Keying on play_kind alone credited the pitcher with
# all seven -- the same misattribution the running game and passed balls were
# excluded to avoid. The narrative names the thrower, so match on that.
PITCHER_THROW = re.compile(r"\bout at \w+ p to\b")


def charged() -> pd.DataFrame:
    """Every play charged to a pitcher, with its run value."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    players = pd.read_parquet(OUT_DIR / "players.parquet")
    person = players.set_index("player_id")["person_id"].to_dict()
    unique = players.drop_duplicates("person_id").set_index("person_id")
    re_table = run_expectancy()

    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["pitching_team_id", "pitcher_id"])
            .sort_values(["game_id", "sequence"]).copy())
    live["bases"] = (live["first_base"].notna().map({True: "1", False: "_"})
                     + live["second_base"].notna().map({True: "2", False: "_"})
                     + live["third_base"].notna().map({True: "3", False: "_"}))

    rows = []
    for _, half in live.groupby(["game_id", "inning", "half"], sort=False):
        records = list(half.sort_values("sequence").itertuples())
        for i, play in enumerate(records):
            event = str(play.event_type)
            is_pa = bool(play.is_plate_appearance)
            # A pickoff only counts when it actually retired the runner.
            pickoff = (play.play_kind == "baserunning_out"
                       and bool(PITCHER_THROW.search(str(play.narrative or ""))))
            balk = play.play_kind in PITCHER_KINDS
            if not (is_pa or event in PITCHER_PLAYS or pickoff or balk):
                continue
            nxt = records[i + 1] if i + 1 < len(records) else None
            after = (re_of(re_table, nxt.bases, int(nxt.outs_before))
                     if nxt is not None else 0.0)
            before = re_of(re_table, play.bases, int(play.outs_before))
            pid = person.get(play.pitcher_id, play.pitcher_id)
            rows.append({
                "person_id": pid,
                "pitcher": unique["person_name"].get(pid, play.pitcher_name),
                "tm": CODES.get(unique["team_name"].get(pid), "?"),
                "kind": ("plate appearance" if is_pa else
                         "pitcher pickoff" if pickoff else "balk" if balk else event),
                "is_pa": is_pa,
                # Flip the sign: positive is good for the pitcher.
                "value": -(after + play.runs_scored - before),
            })
    return pd.DataFrame(rows)


def fip_weights() -> tuple[dict, float, float]:
    """Run values per nine innings for the three true outcomes, plus the
    constant that puts league FIP on league ERA."""
    frame = plate_appearances()
    _, weights = neutral_values(frame, "drop", "pool")
    per_nine = {"hr": weights["home_run"] * INNINGS,
                "bb": weights["free_pass"] * INNINGS,
                "so": weights["strikeout"] * INNINGS}

    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    pitching = pitching[pitching["bf"] > 0]
    innings = pitching["ip_outs"].sum() / 3
    raw = (per_nine["hr"] * pitching["hr"].sum()
           + per_nine["bb"] * (pitching["bb"].sum() + pitching["hbp"].sum())
           + per_nine["so"] * pitching["so"].sum()) / innings
    league_era = pitching["er"].sum() / innings * INNINGS
    return per_nine, league_era - raw, league_era


def fip_of(row, per_nine: dict, constant: float) -> float:
    innings = row["ip_outs"] / 3
    if innings <= 0:
        return np.nan
    raw = (per_nine["hr"] * row["hr"]
           + per_nine["bb"] * (row["bb"] + row["hbp"])
           + per_nine["so"] * row["so"]) / innings
    return raw + constant


def interval(values: np.ndarray, rng) -> tuple[float, float]:
    draws = values[rng.integers(0, len(values), size=(BOOTSTRAP, len(values)))].mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def fip_interval(row, per_game: dict, constant: float, rng) -> tuple[float, float]:
    """A 95% interval for one pitcher's FIP, from resampling her own batters
    faced. FIP counts only four outcomes, so a plate-appearance bootstrap is a
    multinomial draw over home runs, free passes, strikeouts, and everything
    else -- no play-by-play needed."""
    bf = int(row["bf"])
    counts = np.array([row["hr"], row["bb"] + row["hbp"], row["so"]], dtype=float)
    share = np.append(counts, max(bf - counts.sum(), 0.0)) / bf
    draws = rng.multinomial(bf, share, size=BOOTSTRAP)
    raw = (per_game["hr"] * draws[:, 0] + per_game["bb"] * draws[:, 1]
           + per_game["so"] * draws[:, 2]) / (row["ip_outs"] / 3)
    low, high = np.percentile(raw + constant, [2.5, 97.5])
    return float(low), float(high)


def pitcher_table(frame: pd.DataFrame, rng, weights=None) -> pd.DataFrame:
    """One row per qualified pitcher: RE24 in total and per batter faced with an
    interval, FIP with an interval, and FIP restated as runs saved per batter
    faced so both measures sit on one axis.

    That restatement divides by the LEAGUE's batters per inning rather than the
    pitcher's own, so a row means the same thing in every row: a pitcher whose
    defence turns more batters into outs should not have her FIP stretched for
    it, since escaping the defence is the whole point of the measure."""
    per_game, constant, league_era = weights if weights else fip_weights()
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    pitching = pitching[pitching["bf"] > 0]
    per_inning = pitching["bf"].sum() / (pitching["ip_outs"].sum() / 3)
    totals = pitching.groupby("person_id").agg(
        ip_outs=("ip_outs", "sum"), hr=("hr", "sum"), bb=("bb", "sum"),
        hbp=("hbp", "sum"), so=("so", "sum"), er=("er", "sum"), r=("r", "sum"),
        bf=("bf", "sum"))
    totals["fip"] = totals.apply(lambda r: fip_of(r, per_game, constant), axis=1)
    totals["era"] = totals["er"] / (totals["ip_outs"] / 3) * INNINGS

    rows = []
    for pid, group in frame.groupby("person_id"):
        pa = group[group["is_pa"]]
        if pid not in totals.index or len(pa) < MIN_BF:
            continue
        values = group["value"].to_numpy()
        # Per batter faced means the loose plays' runs over the batters, not a
        # mean over every charged play: averaging wild pitches in as extra
        # "trials" would dilute the rate of exactly the pitchers who threw them.
        per_batter = len(values) / len(pa)
        lo, hi = (x * per_batter for x in interval(values, rng))
        t = totals.loc[pid]
        fip_low, fip_high = fip_interval(t, per_game, constant, rng)

        def saved(fip: float) -> float:
            return (league_era - fip) / (INNINGS * per_inning)

        rows.append({"tm": group["tm"].iloc[0], "pitcher": group["pitcher"].iloc[0],
                     "ip": t["ip_outs"] / 3, "bf": int(t["bf"]),
                     "re24_bf": values.sum() / len(pa), "lo": lo, "hi": hi,
                     "total": values.sum(), "era": t["era"], "fip": t["fip"],
                     "fip_lo": fip_low, "fip_hi": fip_high,
                     "fip_bf": saved(t["fip"]), "fip_bf_lo": saved(fip_high),
                     "fip_bf_hi": saved(fip_low),
                     "k9": t["so"] / (t["ip_outs"] / 3) * INNINGS,
                     "bb9": (t["bb"] + t["hbp"]) / (t["ip_outs"] / 3) * INNINGS})
    return pd.DataFrame(rows).sort_values("fip")


def main() -> None:
    pd.set_option("display.width", 250)
    rng = np.random.default_rng(SEED)

    frame = charged()
    per_nine, constant, league_era = fip_weights()

    print(f"{len(frame)} plays charged to pitchers "
          f"({int(frame['is_pa'].sum())} plate appearances, "
          f"{int((~frame['is_pa']).sum())} loose plays)")
    print("  charged:     plate appearances, wild pitches, balks, pitcher pickoffs")
    print("  not charged: passed balls, the running game, and runners caught off")
    print("               base by anyone but the pitcher -- all the catcher's or")
    print("               the fielders', not the pitcher's")
    print()
    print("  loose plays, and what they were worth to the pitchers charged:")
    loose = frame[~frame["is_pa"]].groupby("kind")["value"].agg(["size", "sum"])
    print(loose.round(2).to_string())

    print(f"\n=== WPBL FIP weights, re-derived ===")
    print(f"   per {INNINGS} innings; MLB's standard 13 / 3 / -2 is per nine")
    print(f"   HR      {per_nine['hr']:+6.2f}   (MLB standard {13 * INNINGS / 9:5.1f})")
    print(f"   BB+HBP  {per_nine['bb']:+6.2f}   (MLB standard {3 * INNINGS / 9:5.1f})")
    print(f"   K       {per_nine['so']:+6.2f}   (MLB standard {-2 * INNINGS / 9:5.1f})")
    print(f"   constant {constant:+.3f}, so league FIP = league ERA = {league_era:.2f}")

    table = pitcher_table(frame, rng, (per_nine, constant, league_era))

    print(f"\n\n=== {len(table)} pitchers with at least {MIN_BF} batters faced ===")
    print("    RE24/BF: runs PREVENTED per batter faced -- positive is good; a")
    print("    pitcher's +0.20 means she saved a fifth of a run. A batter's +0.20 in")
    print("    the batter table means the opposite physical thing, a fifth of a run")
    print("    CREATED. Both tables read downward from best to worst.")
    print("    * = interval clear of zero")
    print(f"    FIP: on an ERA scale, LOWER is better, league {league_era:.2f}\n")
    print(f"  {'':4s}{'pitcher':21s}{'IP':>6s}{'RE24/BF':>9s}{'':16s}"
          f"{'ERA':>7s}{'FIP':>7s}{f'K/{INNINGS}':>6s}{f'BB/{INNINGS}':>6s}")
    for row in table.itertuples():
        star = "*" if (row.lo > 0 or row.hi < 0) else " "
        # Baseball notation: the digit after the point is outs, so 4 2/3 is "4.2".
        outs = round(row.ip * 3)
        print(f"  {row.tm:4s}{row.pitcher:21s}{f'{outs // 3}.{outs % 3}':>6s}{row.re24_bf:+9.3f}{star}"
              f" [{row.lo:+.2f},{row.hi:+.2f}]{row.era:7.2f}{row.fip:7.2f}"
              f"{row.k9:6.1f}{row.bb9:6.1f}")

    rank = np.corrcoef(table["re24_bf"].rank(), (-table["fip"]).rank())[0, 1]
    print(f"\n  RE24/BF vs FIP agree at spearman {rank:+.3f} "
          f"(FIP negated, so both point the same way)")
    print(f"  RE24/BF vs ERA: {np.corrcoef(table['re24_bf'].rank(), (-table['era']).rank())[0, 1]:+.3f}")
    table = table.assign(gap=(-table["fip"]).rank() - table["re24_bf"].rank())
    print("\n  biggest disagreements (FIP likes her more than RE24 does, and the reverse):")
    for row in pd.concat([table.nlargest(3, "gap"), table.nsmallest(3, "gap")]).itertuples():
        verdict = "FIP higher on her" if row.gap > 0 else "RE24 higher on her"
        print(f"    {row.pitcher:21s} RE24/BF {row.re24_bf:+.3f}  FIP {row.fip:5.2f}  "
              f"ERA {row.era:5.2f}   {verdict} by {abs(row.gap):.0f} places")


if __name__ == "__main__":
    main()
