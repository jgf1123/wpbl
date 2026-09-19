"""Dice-game player cards: a smoothed outcome distribution for every batter and pitcher.

    pixi run dice

A card is eight lines -- K, BB, HBP, HR, 1B, 2B, ROE, Out -- summing to 100%.
Each player's raw record is too thin to print as it stands (a regular has ~75
plate appearances), so each card is pulled toward the record of a cohort of
players her team used about as much, by an amount chosen on held-out games.
dice_game_spec.md section 3 holds the design and the evidence for every choice.

HOW A CARD IS BUILT

Outcomes are split step by step; each step divides one group of outcomes in
two (or more), and is smoothed with its own constant k:

    step share = (her count + k * cohort share) / (her count at the step + k)

A card line is the product of the shares along its path, so a card sums to
100% by construction and a hole in one outcome can only be filled from within
its own step. k = inf means the step takes the cohort's split outright.

  batters: true outcomes (K, BB, HBP, HR) | in-park contact; then two-way
    splits in order of increasing k inside each branch --
    HBP | K+BB+HR;  HR | K+BB;  K | BB;  and  1B | rest;  out | 2B+ROE;  ROE | 2B
  pitchers, a four-step tree:
    K | not K;  BB / HBP / in play;  out / ROE / hit;  HR / 1B / 2B

The k values were chosen by cross-validation over game halves, scored on the
squared error of each plate appearance's expected run value; the tuning runs
are analysis, not part of this module.

COHORTS

Players are ranked by how much their team used them -- batters by the share of
team games started, pitchers by the share of team batters faced, both over
their tenure with each team (a traded player's tenure splits at her first game
for the new team). A player's cohort is her nearest neighbours in that ranking,
excluding herself, until they hold 300 plate appearances; tied players enter
together. Ranking by performance would be circular.

Benites and Whitmore (12 HR each, next best 5) are a named exception: at the
step that splits off home runs, each is smoothed toward the other plus Lansdell
and Mackay, and neither is in anyone else's cohort for that step.

Every line is floored at 1%; the lines raised to the floor take their extra
share from the other lines in proportion, so the card still sums to 100%.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import contact
from wpbl.parse import ALL_DIR
from wpbl.usage_chart import CODES

LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
IX = {line: i for i, line in enumerate(LINES)}
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR",
           "single": "1B", "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
MIN_RATE = 0.01
COHORT_PA = 300
SLUGGERS = ("Denae Benites", "Kelsie Whitmore")
SLUGGER_COHORT = SLUGGERS + ("Ashton Lansdell", "Jamie Mackay")
OUT_DIR = ALL_DIR.parent / "dice"

# A structure is a list of steps (group, [sub-groups]); groups are tuples of lines.
# k values sit on the tuning grid, powers of sqrt(2): 2 ** 5.5 is the "45" of the analysis.
PA = tuple(LINES)
CONTACT = ("HR", "1B", "2B", "ROE", "OUT")
TRUE_OUTCOMES = ("K", "BB", "HBP", "HR")
IN_PARK = ("1B", "2B", "ROE", "OUT")
BATTER_STEPS = [
    (PA, [TRUE_OUTCOMES, IN_PARK]),
    (TRUE_OUTCOMES, [("HBP",), ("K", "BB", "HR")]),
    (("K", "BB", "HR"), [("HR",), ("K", "BB")]),
    (("K", "BB"), [("K",), ("BB",)]),
    (IN_PARK, [("1B",), ("2B", "ROE", "OUT")]),
    (("2B", "ROE", "OUT"), [("OUT",), ("2B", "ROE")]),
    (("2B", "ROE"), [("ROE",), ("2B",)]),
]
BATTER_K = [2 ** 5.5, 2 ** 1, 2 ** 2.5, 2 ** 4, 2 ** 6, 2 ** 8, 2 ** 4]    # tto_c, 18 Sep
PITCHER_STEPS = [
    (PA, [("K",), ("BB", "HBP") + CONTACT]),
    (("BB", "HBP") + CONTACT, [("BB",), ("HBP",), CONTACT]),
    (CONTACT, [("OUT",), ("ROE",), ("HR", "1B", "2B")]),
    (("HR", "1B", "2B"), [("HR",), ("1B",), ("2B",)]),
]
PITCHER_K = [2 ** 5.5, 2 ** 8, 2 ** 7.5, np.inf]         # trees_cv, 18 Sep


def plate_appearances() -> pd.DataFrame:
    """Training plate appearances with their card line, batter and pitcher (person ids)."""
    plays = tables.read("plays", "training")
    players = tables.read("players", "training")
    games = tables.read("games", "all")
    person = players.set_index("player_id")["person_id"].to_dict()
    team = pd.concat([games.set_index("home_team_id")["home_team_name"],
                      games.set_index("away_team_id")["away_team_name"]]).groupby(level=0).first()
    pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
    pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
    pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
    pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
    pa["B_team"] = pa["batting_team_id"].map(team)          # names: postseason team ids differ
    pa["P_team"] = pa["pitching_team_id"].map(team)
    pa["date"] = pa["game_date"].astype(str).str[:10]
    return pa.reset_index(drop=True)


def tenure_share(frame, who, team, own, per_date) -> pd.Series:
    """own[person] / her team's per_date total over her tenure; a traded player's
    tenure with a team ends at her first game for the next one."""
    out = {}
    for pid, g in frame.groupby(who):
        firsts = g.groupby(team)["date"].min().sort_values()
        denom = 0.0
        for i, (t, first) in enumerate(firsts.items()):
            d = per_date.loc[t]
            lo = first if i > 0 else "0000"
            hi = firsts.iloc[i + 1] if i + 1 < len(firsts) else "9999"
            denom += float(d[(d.index >= lo) & (d.index < hi)].sum())
        out[pid] = own.get(pid, 0) / denom
    return pd.Series(out)


def usage(pa: pd.DataFrame) -> dict[str, pd.Series]:
    """Batters: share of team games started. Pitchers: share of team batters faced."""
    bat = tables.read("batting", "training").copy()
    bat["date"] = bat["game_date"].astype(str).str[:10]
    team_games = bat.drop_duplicates(["game_id", "team_name"]).groupby(["team_name", "date"]).size()
    starts = bat.groupby("person_id")["in_starting_lineup"].sum()
    return {"B": tenure_share(bat, "person_id", "team_name", starts, team_games),
            "P": tenure_share(pa, "P", "P_team", pa.groupby("P").size(), pa.groupby(["P_team", "date"]).size())}


def cohorts(share: np.ndarray, n: np.ndarray, exclude: np.ndarray) -> list[np.ndarray]:
    """For each player, the indices of her nearest neighbours by share (never herself,
    nobody in `exclude`), whole tie groups at a time, until they hold COHORT_PA."""
    out = []
    for i in range(len(share)):
        cand = np.flatnonzero((np.arange(len(share)) != i) & (n > 0) & ~exclude)
        dist = np.round(np.abs(share[cand] - share[i]), 12)
        take, got = [], 0.0
        for d in np.unique(dist):
            grp = cand[dist == d]
            take.extend(grp)
            got += n[grp].sum()
            if got >= COHORT_PA:
                break
        out.append(np.array(take, dtype=int))
    return out


def build(X: np.ndarray, names: list[str], share: np.ndarray, steps, ks) -> np.ndarray:
    """Cards (players x 8 lines) from counts X, smoothing each step toward the cohort."""
    n = X.sum(axis=1)
    slug = np.isin(names, SLUGGERS)
    everyone = cohorts(share, n, np.zeros(len(n), bool))
    no_sluggers = cohorts(share, n, slug) if slug.any() else everyone
    in_slug_cohort = np.isin(names, SLUGGER_COHORT)
    hr_step = next(s for s, (_, parts) in enumerate(steps) if ("HR",) in parts)

    prob = {PA: np.ones(len(n))}
    for s, ((group, parts), k) in enumerate(zip(steps, ks)):
        C = np.column_stack([X[:, [IX[l] for l in part]].sum(axis=1) for part in parts])
        T = np.zeros_like(C)
        for i in range(len(n)):
            if s == hr_step and slug[i]:
                take = np.flatnonzero(in_slug_cohort & (np.arange(len(n)) != i))
            else:
                take = (no_sluggers if s == hr_step else everyone)[i]
            tot = C[take].sum(axis=0)
            T[i] = tot / tot.sum() if tot.sum() > 0 else C.sum(axis=0) / C.sum()
        m = C.sum(axis=1, keepdims=True)
        share_s = T if np.isinf(k) else (C + k * T) / np.maximum(m + k, 1e-12)
        for j, part in enumerate(parts):
            prob[part] = prob[group] * share_s[:, j]
    return floor(np.column_stack([prob[(l,)] for l in LINES]))


def floor(cards: np.ndarray) -> np.ndarray:
    """Raise every line to at least MIN_RATE and take the excess from the other lines
    in proportion, so the card still sums to 100%. Dividing the whole card by its new
    sum would push the raised lines back under the floor."""
    cards = cards.copy()
    for row in cards:
        low = np.zeros(len(row), bool)
        while True:                       # raising one line can push another under
            low |= row < MIN_RATE
            row[low] = MIN_RATE
            free = 1.0 - MIN_RATE * low.sum()
            row[~low] *= free / row[~low].sum()
            if not (row[~low] < MIN_RATE).any():
                break
    return cards


def check(cards: np.ndarray) -> None:
    assert np.allclose(cards.sum(axis=1), 1.0), "a card does not sum to 100%"
    assert (cards >= MIN_RATE - 1e-12).all(), "a card line is below the 1% floor"


def main() -> None:
    pd.set_option("display.width", 220)
    pa = plate_appearances()
    shares = usage(pa)
    players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
    league = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
    print(f"{pa['game_id'].nunique()} training games, {len(pa)} plate appearances")
    print("league: " + "  ".join(f"{l} {100 * league[l]:.1f}%" for l in LINES))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for side, label, steps, ks, team_col in (("B", "batters", BATTER_STEPS, BATTER_K, "B_team"),
                                            ("P", "pitchers", PITCHER_STEPS, PITCHER_K, "P_team")):
        X = pd.crosstab(pa[side], pa["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        names = [players["person_name"].get(i, i) for i in ids]
        cards = build(X.to_numpy().astype(float), names, shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks)
        check(cards)
        last_team = pa.sort_values("date").groupby(side)[team_col].last()
        table = pd.DataFrame(100 * cards, columns=LINES, index=ids).round(1)
        table.insert(0, "PA" if side == "B" else "BF", X.sum(axis=1).to_numpy())
        table.insert(0, "team", [CODES.get(last_team.get(i), "?") for i in ids])
        table.insert(0, "player", names)
        table = table.sort_values(table.columns[2], ascending=False)       # most-used players first
        table.to_csv(OUT_DIR / f"cards_{label}.csv", index=False)
        hr_total = float((cards[:, IX["HR"]] * X.sum(axis=1).to_numpy()).sum())
        print(f"\n=== {label}: {len(table)} cards -> {OUT_DIR / f'cards_{label}.csv'} ===")
        if side == "B":
            print(f"home runs the cards produce over the same PAs: {hr_total:.1f} (actual {int(X['HR'].sum())})")
        print(table.head(12).to_string(index=False))
    print("\ncheck passed: every card sums to 100% and every line is at least 1%")


if __name__ == "__main__":
    main()
