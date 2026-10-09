"""Context-neutral runs per batter faced, for every pitcher, three ways.

    pixi run python analysis/dice/pitcher_runs.py
    pixi run python analysis/dice/pitcher_runs.py "Raine Padgham"

All three use one exact calculator: the dice game's half-inning from empty
bases, through engine.apply_line with the d12 enumerated, and running plays at
the table's 6 in 100. Runs/BF = E[runs per half-inning] / E[batters per
half-inning].

  raw      her actual line shares (8 lines), no smoothing
  card     her smoothed season card, dice.cards("P"), before rounding to cells
  printed  her printed fresh / fading / gassed cells mixed with the league
           batter on the d100 -- the game as played

The league comes out the same raw and printed (0.2065 on 39 games), which is
the check that the calculator and the printed league card agree.

With a name, it also prints why her card differs from her record: her raw
line against her card, her cohort and its shares, and her game log with the
runs scored while she pitched.

Written 1 Oct to check a ranking that put Padgham first on BOS. The card is
built as designed: her K rate is kept (k = 1), but out-vs-hit and HR-vs-1B take
the cohort outright (k = inf) and 2B is a league band, so her contact damage
(20 hits on 36 balls in play) never reaches the card. Raw 0.343, card 0.208.
"""
import sys

import numpy as np
import pandas as pd

from wpbl import dice, engine, tables
from wpbl.card_runs import LINES, from_shares, from_table
from wpbl.card_runs import runs_per_pa as runs_per_bf     # the one calculator, in src
from wpbl.play_wp import CARD_LINES, DICE_DIR, P_SPAN, faces, league_table


def everyone(pa, names):
    counts = pd.crosstab(pa["P"], pa["line"]).reindex(columns=LINES, fill_value=0)
    card = dice.cards("P")[LINES]
    usage = dice.usage(pa)["P"]
    lg = league_table()
    printed = pd.read_csv(DICE_DIR / "cards_pitchers.csv", comment="#", dtype=str).set_index("player")
    print(f"league: raw {runs_per_bf(from_shares(counts.sum().to_numpy())):.4f}, "
          f"printed league card {runs_per_bf(from_table(lg)):.4f}")
    rows = []
    for pid in counts.index:
        name = names.get(pid, pid)
        row = {"pitcher": name, "BF": int(counts.loc[pid].sum()), "usage": usage.get(pid, np.nan),
               "raw": runs_per_bf(from_shares(counts.loc[pid].to_numpy())),
               "card": runs_per_bf(from_shares(card.loc[pid].to_numpy()))}
        key = dice.plain_name(name)
        if key in printed.index:
            pr = printed.loc[key]
            row["team"] = pr["team"]
            for col in ("fresh", "fading", "gassed"):
                p_faces = faces(pr, CARD_LINES, f"{col} ", P_SPAN)
                row[col] = runs_per_bf(from_table(engine.Table.from_lines(p_faces, lg.b_line)))
        rows.append(row)
    out = pd.DataFrame(rows).sort_values(["team", "fading"])
    pd.set_option("display.width", 200)
    print(out.to_string(index=False, float_format=lambda x: f"{x:.3f}"))


def one(pa, names, who):
    pid = next(i for i, n in names.items() if who.lower() in str(n).lower())
    mine = pa[pa["P"] == pid]
    print(f"\n{names[pid]}: {len(mine)} BF")
    shares = lambda s: s.value_counts(normalize=True).reindex(LINES, fill_value=0)
    table = pd.DataFrame({"raw count": mine["line"].value_counts().reindex(LINES, fill_value=0),
                          "raw": shares(mine["line"]), "card": dice.cards("P").loc[pid, LINES],
                          "league": shares(pa["line"])})
    counts = pd.crosstab(pa["P"], pa["line"]).reindex(columns=dice.LINES, fill_value=0)
    share = dice.usage(pa)["P"].reindex(counts.index).fillna(0).to_numpy()
    X = counts.to_numpy().astype(float)
    for l in dice.FIXED:                     # cohorts are formed without the fixed bands
        X[:, dice.IX[l]] = 0
    coh = dice.cohorts(share, X.sum(1), np.zeros(len(X), bool))[list(counts.index).index(pid)]
    table["cohort"] = (counts.iloc[coh].sum() / counts.iloc[coh].sum().sum()).reindex(LINES)
    print(table.T.to_string(float_format=lambda x: f"{x:.3f}"))
    print("cohort:", ", ".join(str(names.get(i, i)) for i in counts.index[coh]),
          f"({int(X[coh].sum())} BF)")
    plays = tables.read("plays", "training")
    ids = tables.read("players", "training").query("person_id == @pid")["player_id"]
    pp = plays[plays["pitcher_id"].isin(ids)].assign(date=lambda d: d["game_date"].astype(str).str[:10])
    log = pp.groupby("date").agg(BF=("is_plate_appearance", "sum"), runs=("runs_scored", "sum"))
    print(log.to_string())
    print(f"runs while she pitched: {log['runs'].sum()} in {log['BF'].sum()} BF")


if __name__ == "__main__":
    pa = dice.plate_appearances()
    names = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")["person_name"]
    everyone(pa, names)
    if len(sys.argv) > 1:
        one(pa, names, sys.argv[1])
