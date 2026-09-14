"""Team defence: the runs each team's fielders saved, and where they came from.

    pixi run defense

FIP counts only what no fielder touches -- strikeouts, walks, hit batters, home
runs -- priced at this league's run values. Scaled so that league FIP equals
league runs allowed (not earned runs: unearned runs are exactly what a defence
is responsible for), the gap between a team's FIP and its runs allowed is
everything else:

    Defense/7 = FIP/7 - RA/7

That leftover is then split three ways, all per seven innings and measured
against league average, positive meaning runs saved:

    balls in play   opponents' contact outcomes -- every hit, error and out --
                    priced at their league-average run values, so this is what
                    the defence turned contact into, blind to when it happened
    running game    runs from stolen bases and caught stealing, priced on the
                    run-expectancy table
    timing          whatever is left: runs allowed beyond what the outcomes
                    alone predict, because hits arrived bunched or scattered

so that Defense/7 = balls in play + running game + timing exactly. Pitching
(league RA/7 minus FIP/7) is printed alongside for context; it is not defence.

Timing is the residual, so it inherits every other component's noise as well as
its own, and it holds more than luck: anything that changes how outcomes
cluster -- a tiring pitcher left in, say -- lands there too.

Intervals come from a cluster bootstrap over games. The linear weights and the
run-expectancy table are held fixed; FIP's constant is re-fit in every draw, as
it would be on a different season.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.batters import classify, contact, neutral_values, plate_appearances
from wpbl.markov import re_of, run_expectancy
from wpbl.parse import OUT_DIR
from wpbl.pitchers import fip_weights
from wpbl.usage_chart import CODES

INNINGS = 7
BOOTSTRAP = 2000
SEED = 20260914
COMPONENTS = ["pitching", "balls_in_play", "running", "timing", "defense", "saved"]
LABELS = {"pitching": "Pitching", "balls_in_play": "Balls in play", "running": "Running game",
          "timing": "Timing", "defense": "Defense/7", "saved": "Runs saved"}
# Per team-game quantities that the decomposition sums; kept as one array so a
# bootstrap draw is a single weighted sum rather than a re-aggregation.
FIELDS = ["outs", "hr", "bb", "hbp", "so", "r", "bip_value", "running", "bip", "hits", "roe"]


def team_games() -> pd.DataFrame:
    """One row per (game, fielding team) with everything the split needs."""
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    pitching = pitching[pitching["bf"] > 0]
    pitching = pitching.assign(tm=pitching["team_name"].map(CODES))
    base = pitching.groupby(["game_id", "tm"]).agg(
        outs=("ip_outs", "sum"), hr=("hr", "sum"), bb=("bb", "sum"), hbp=("hbp", "sum"),
        so=("so", "sum"), r=("r", "sum"))

    plays = pd.read_parquet(OUT_DIR / "plays.parquet").sort_values(["game_id", "sequence"])
    teams = (pd.read_parquet(OUT_DIR / "team_games.parquet")
             .drop_duplicates("team_id").set_index("team_id")["team_name"])
    plays["tm"] = plays["pitching_team_id"].map(teams).map(CODES)
    plays["bases"] = (plays["first_base"].notna().map({True: "1", False: "_"})
                      + plays["second_base"].notna().map({True: "2", False: "_"})
                      + plays["third_base"].notna().map({True: "3", False: "_"}))

    # Balls in play, priced at the context-neutral weights.
    _, weights = neutral_values(plate_appearances(), "credit", "pool")
    pa = plays[plays["is_plate_appearance"] & plays["batter_id"].notna()
               & (plays["outs_before"] < 3)].copy()
    pa["event"] = [classify(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
    pa["outcome"] = [contact(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
    in_play = pa[~pa["outcome"].isin(["strikeout", "home_run"])
                 & ~pa["event"].isin(["walk", "hit_by_pitch"])]
    contact_side = in_play.assign(
        value=in_play["outcome"].map(weights),
        hit=in_play["event"].isin(["single", "double", "triple"]),
        error=in_play["event"] == "reached_on_error",
    ).groupby(["game_id", "tm"]).agg(bip_value=("value", "sum"), bip=("value", "size"),
                                     hits=("hit", "sum"), roe=("error", "sum"))

    # The running game, priced on the run-expectancy table.
    table = run_expectancy()
    rows = []
    for _, half in plays.groupby(["game_id", "inning", "half"], sort=False):
        records = list(half.itertuples())
        for i, play in enumerate(records):
            if play.event_type not in ("stolen_base", "caught_stealing") or play.outs_before >= 3:
                continue
            nxt = records[i + 1] if i + 1 < len(records) else None
            after = re_of(table, nxt.bases, int(nxt.outs_before)) if nxt is not None else 0.0
            rows.append({"game_id": play.game_id, "tm": play.tm,
                         "running": after + play.runs_scored
                         - re_of(table, play.bases, int(play.outs_before))})
    running = pd.DataFrame(rows).groupby(["game_id", "tm"])["running"].sum()

    frame = base.join(contact_side).join(running).fillna(0.0)
    return frame[FIELDS]


def decompose(sums: np.ndarray, weights: dict) -> np.ndarray:
    """Components per team from summed FIELDS (teams x fields) -> (teams x COMPONENTS)."""
    col = {name: sums[:, i] for i, name in enumerate(FIELDS)}
    league = sums.sum(axis=0)
    lg = {name: league[i] for i, name in enumerate(FIELDS)}
    innings, league_innings = col["outs"] / 3, lg["outs"] / 3

    def raw_fip(c, ip):
        return (weights["hr"] * c["hr"] + weights["bb"] * (c["bb"] + c["hbp"])
                + weights["so"] * c["so"]) / ip

    league_ra = lg["r"] / league_innings * INNINGS
    constant = league_ra - raw_fip(lg, league_innings)
    fip = raw_fip(col, innings) + constant
    ra = col["r"] / innings * INNINGS
    defense = fip - ra
    balls = -(col["bip_value"] / innings - lg["bip_value"] / league_innings) * INNINGS
    running = -(col["running"] / innings - lg["running"] / league_innings) * INNINGS
    timing = defense - balls - running
    saved = defense * innings / INNINGS
    return np.column_stack([league_ra - fip, balls, running, timing, defense, saved])


def signed(value: float, digits: int = 2) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


def main() -> None:
    pd.set_option("display.width", 220)
    frame = team_games()
    weights, _, _ = fip_weights()
    teams = sorted(frame.index.get_level_values("tm").unique())
    games = sorted(frame.index.get_level_values("game_id").unique())

    # games x teams x fields; a team not in a game contributes zeros.
    cube = np.zeros((len(games), len(teams), len(FIELDS)))
    g_pos = {g: i for i, g in enumerate(games)}
    t_pos = {t: i for i, t in enumerate(teams)}
    for (game, tm), row in frame.iterrows():
        cube[g_pos[game], t_pos[tm]] = row.to_numpy()

    observed = decompose(cube.sum(axis=0), weights)
    rng = np.random.default_rng(SEED)
    draws = np.empty((BOOTSTRAP,) + observed.shape)
    for b in range(BOOTSTRAP):
        taken = np.bincount(rng.integers(0, len(games), len(games)), minlength=len(games))
        draws[b] = decompose(np.tensordot(taken, cube, axes=1), weights)
    lo, hi = np.percentile(draws, [2.5, 97.5], axis=0)

    totals = cube.sum(axis=0)
    fields = {name: i for i, name in enumerate(FIELDS)}
    babip = totals[:, fields["hits"]] / totals[:, fields["bip"]]
    roe = totals[:, fields["roe"]] / totals[:, fields["bip"]] * 100
    order = np.argsort(-observed[:, COMPONENTS.index("defense")])

    print(f"{len(games)} games; runs saved per {INNINGS} innings against league average, "
          f"higher is better; 95% intervals from resampling games\n")
    header = "".join(f"{LABELS[c]:>24s}" for c in COMPONENTS)
    print(f"  {'':4s}{header}{'BABIP':>8s}{'ROE%':>7s}")
    for t in order:
        cells = "".join(f"{observed[t, j]:+7.2f} [{lo[t, j]:+6.2f},{hi[t, j]:+6.2f}]"
                        for j in range(len(COMPONENTS)))
        print(f"  {teams[t]:4s}{cells}{babip[t]:8.3f}{roe[t]:7.1f}")

    identity = observed[:, 1] + observed[:, 2] + observed[:, 3] - observed[:, 4]
    print(f"\n  identity check, balls in play + running + timing - defense: "
          f"max |{np.abs(identity).max():.1e}|")
    clear = [(teams[t], LABELS[c]) for t in range(len(teams)) for j, c in enumerate(COMPONENTS[:4])
             if lo[t, j] > 0 or hi[t, j] < 0]
    print(f"  intervals clear of zero: {clear if clear else 'none'}")

    print("\n=== markdown for the post ===\n")
    print("| Team | Balls in play | Running game | Timing | Defense/7 |")
    print("|---|---|---|---|---|")
    for t in order:
        cells = [f"{signed(observed[t, j])} [{signed(lo[t, j])}, {signed(hi[t, j])}]"
                 for j in (1, 2, 3, 4)]
        print(f"| {teams[t]} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
