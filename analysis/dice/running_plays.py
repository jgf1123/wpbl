"""Wild pitches, passed balls and balks: does the rate belong on a card?

    pixi run python analysis/dice/running_plays.py

Spec section 6 calls these one league line at about 4% of rolls, but the d100
table has no cell for them (section 4), so they have to go somewhere. If the
rate differs between pitchers for real, the line belongs on the pitcher's card;
if it does not, it joins 2B and ROE as a fixed band.

The opportunity is a PITCH THROWN WITH A RUNNER ON. The feed only records one of
these plays when a runner actually advances, so a wild pitch with the bases empty
is invisible -- which suits the game, where the line only does anything with
runners on. Base state is taken at the start of the plate appearance.

Each event has a different plausible owner, so they are measured apart:
  wild pitch    the pitcher, partly the catcher who blocks it
  passed ball   the catcher, by definition
  balk          the pitcher, and possibly the umpire

There is no umpire in any table, so the umpire theory cannot be tested directly.
It has an implication that can be: if one umpire called balks far more freely,
balks would bunch into her games. That is testable as overdispersion across games
against a Poisson process with the same mean.
"""
import numpy as np
import pandas as pd

from wpbl import tables

pd.set_option("display.width", 220)
MIN_OPP = 100                      # pitches with a runner on, for the spread test
rng = np.random.default_rng(20260921)

plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
nm = players.drop_duplicates("person_id").set_index("person_id")["person_name"]

plays = plays.copy()
plays["P"] = plays["pitcher_id"].map(person).fillna(plays["pitcher_id"])
plays["kind"] = np.where(plays["play_kind"] == "balk", "balk", plays["event_type"])
EVENTS = ["wild_pitch", "passed_ball", "balk"]

# --- opportunities: pitches thrown during a PA that began with a runner on ---
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pitches = pa["n_pitches"].fillna(pa["n_pitches_est"]).fillna(0)
pa = pa.assign(pitches=pitches)
on = pa["runners_on"].fillna(0) > 0
opp = pa[on].groupby("P")["pitches"].sum()
ev = plays[plays["kind"].isin(EVENTS)]

print(f"training games {plays['game_id'].nunique()}")
print(f"running plays: " + ", ".join(f"{k} {int((ev['kind'] == k).sum())}" for k in EVENTS)
      + f"  (total {len(ev)})")
print(f"pitches thrown with a runner on: {opp.sum():.0f}")
print(f"league rate: {100 * len(ev) / opp.sum():.2f}% of such pitches")
pa_on = int(on.sum())
print(f"  ... or {100 * len(ev) / pa_on:.1f}% of the {pa_on} plate appearances that "
      f"began with a runner on")


def real_spread(counts, n, label):
    """How much of the spread between players survives binomial sampling noise."""
    keep = n >= MIN_OPP
    x, m = counts[keep].to_numpy(float), n[keep].to_numpy(float)
    if keep.sum() < 4:
        print(f"  {label}: only {int(keep.sum())} qualify; not measurable")
        return
    L = x.sum() / m.sum()
    r = x / m
    obs = float(((r - L) ** 2).mean())
    noise = float((L * (1 - L) / m).mean())
    boots = []
    for _ in range(4000):
        i = rng.integers(0, len(m), len(m))
        boots.append(float(((r[i] - L) ** 2).mean()) - float((L * (1 - L) / m[i]).mean()))
    lo, hi = np.percentile(boots, [5, 95])
    print(f"  {label}: {int(keep.sum())} with {MIN_OPP}+ opportunities, league {100 * L:.2f}%")
    print(f"      observed SD {100 * np.sqrt(obs):.2f}, chance alone {100 * np.sqrt(noise):.2f}, "
          f"real SD {100 * np.sqrt(max(obs - noise, 0)):.2f} "
          f"(90% {100 * np.sqrt(max(lo, 0)):.2f} to {100 * np.sqrt(max(hi, 0)):.2f})")


print("\n=== does the rate differ between PITCHERS for real? ===")
for label, kinds in (("all three", EVENTS), ("wild pitch", ["wild_pitch"]),
                     ("balk", ["balk"]), ("wild pitch + balk", ["wild_pitch", "balk"])):
    c = ev[ev["kind"].isin(kinds)].groupby("P").size().reindex(opp.index).fillna(0)
    real_spread(c, opp, label)

# --- catchers: one per team-game from the box score ---
fld = tables.read("fielding", "training")
cat = fld[fld["position"].astype(str).str.lower() == "c"]
key = cat.set_index(["game_id", "team_id"])["person_id"].to_dict()
# a running play is charged to the catcher of the PITCHING team in that game
ev_c = ev.assign(C=[key.get((g, t)) for g, t in zip(ev["game_id"], ev["pitching_team_id"])])
pa_c = pa[on].assign(C=[key.get((g, t)) for g, t in zip(pa[on]["game_id"], pa[on]["pitching_team_id"])])
opp_c = pa_c.groupby("C")["pitches"].sum()
print(f"\n=== ... and between CATCHERS? ({cat['person_id'].nunique()} caught this season) ===")
for label, kinds in (("passed ball", ["passed_ball"]), ("wild pitch", ["wild_pitch"]),
                     ("wild pitch + passed ball", ["wild_pitch", "passed_ball"])):
    c = ev_c[ev_c["kind"].isin(kinds)].groupby("C").size().reindex(opp_c.index).fillna(0)
    real_spread(c, opp_c, label)

print("\n=== do balks bunch into particular games? (the umpire theory) ===")
per_game = ev[ev["kind"] == "balk"].groupby("game_id").size()
g = plays["game_id"].nunique()
counts = per_game.reindex(plays["game_id"].unique()).fillna(0).to_numpy()
mean, var = counts.mean(), counts.var(ddof=1)
print(f"  {int(counts.sum())} balks over {g} games: mean {mean:.2f}, variance {var:.2f} "
      f"(a Poisson process has variance = mean)")
sim = rng.poisson(mean, size=(20000, g)).var(axis=1, ddof=1)
print(f"  games with 2+ balks: {int((counts >= 2).sum())} actual, "
      f"{rng.poisson(mean, size=(20000, g)).__ge__(2).sum(axis=1).mean():.1f} expected under Poisson")
print(f"  P(a Poisson process is this clustered or more) = {(sim >= var).mean():.3f}")
print("  distribution: " + ", ".join(f"{int(k)} balks in {int(v)} games"
                                     for k, v in pd.Series(counts).value_counts().sort_index().items()))
