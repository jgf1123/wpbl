"""Dice-game player cards: a smoothed outcome distribution for every batter and pitcher.

    pixi run dice

A card is eight lines -- K, BB, HBP, HR, 1B, 2B, ROE, Out -- summing to 100%.
Each player's raw record is too thin to print as it stands (a regular has ~80
plate appearances), so each card is pulled toward the record of a cohort of
players her team used about as much, by an amount chosen on held-out games.
dice_game_spec.md section 3 holds the design and the evidence for every choice.

Two lines are not what they look like:

  2B   a fixed league band, the same on every card and on neither player's.
       A flat rate predicts held-out doubles better than the batter's own
       record (by 3.9 SE) and the pitcher is worse still, so doubles carry no
       player information worth printing.
  BB / HBP  separate lines, not one free pass. They were merged because runs
       cannot tell them apart (0.45 against 0.49), but that made the test blind
       to the difference that matters: asked whose card a line should be read
       from, walks want the pitcher and hit-by-pitches want the batter.

HOW A CARD IS BUILT

Outcomes are split step by step; each step divides one group of outcomes in
two (or more), and is smoothed with its own constant k:

    step share = (her count + k * cohort share) / (her count at the step + k)

A card line is the product of the shares along its path, so a card sums to
100% by construction and a hole in one outcome can only be filled from within
its own step. k = inf means the step takes the cohort's split outright.

  batters: true outcomes (K, BB, HBP, HR) | in-park contact (1B, ROE, Out);
    then two-way splits inside each branch --
    HR | K+BB+HBP;  K | BB+HBP;  BB | HBP;  and  1B | ROE+Out;  Out | ROE
  pitchers, a tree:
    K | not K;  BB+HBP | in play;  BB | HBP;  out / ROE / hit;  HR | 1B

Doubles sit outside both trees, so every step answers "given it was not a
double, what happened?" and the tree's shares are scaled by 1 - the band.

The k values were chosen by cross-validation over game halves, scored on the
squared error of each plate appearance's expected run value. Runs cannot see the
walk | HBP split (the two are worth almost the same), so its k was chosen on the
log-likelihood of held-out free passes; held-out pitch counts agree. The tuning
runs are analysis (analysis/dice/), not part of this module.

COHORTS

Players are ranked by how much their team used them -- batters by the share of
team games started, pitchers by the share of team batters faced, both over
their tenure with each team (a traded player's tenure splits at her first game
for the new team). A player's cohort is her nearest neighbours in that ranking,
excluding herself, until they hold 250 plate appearances; tied players enter
together, so the cohort she actually gets is usually larger than the target.
Ranking by performance would be circular.

Benites and Whitmore (12 HR each, next best 6) are a named exception: at the
step that splits off home runs, each is smoothed toward the other plus Lansdell
and Mackay, and neither is in anyone else's cohort for that step. It is a rule
about their hitting, so it applies only to the batter cards; Whitmore also
pitches, and her pitcher card is built like anyone else's.

The 1% floor is NOT applied to a card. A card is half of a matchup; the
distribution a d100 has to represent is the one left after a batter and a
pitcher are combined, and that is where `floor()` belongs. Flooring both the
cards and the result would floor twice.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.batters import contact
from wpbl.parse import ALL_DIR
from wpbl.usage_chart import CODES

LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]          # outcomes counted
IX = {line: i for i, line in enumerate(LINES)}
CARD_LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]      # lines printed on a card
TREE_LINES = [l for l in CARD_LINES if l != "2B"]   # 2B is a fixed band, built outside the tree
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR",
           "single": "1B", "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
MIN_RATE = 0.01
COHORT_PA = 250
SLUGGERS = ("Denae Benites", "Kelsie Whitmore")
SLUGGER_COHORT = SLUGGERS + ("Ashton Lansdell", "Jamie Mackay")
OUT_DIR = ALL_DIR.parent / "dice"

# A structure is a list of steps (group, [sub-groups]); groups are tuples of lines.
# k values sit on the tuning grid, powers of sqrt(2): 2 ** 5.5 is the "45" of the analysis.
PA = tuple(LINES)
FP = ("BB", "HBP")
CONTACT = ("HR", "1B", "ROE", "OUT")
TRUE_OUTCOMES = ("K", "BB", "HBP", "HR")
IN_PARK = ("1B", "ROE", "OUT")
NO_2B = tuple(l for l in LINES if l != "2B")
BATTER_STEPS = [
    (NO_2B, [TRUE_OUTCOMES, IN_PARK]),
    (TRUE_OUTCOMES, [("HR",), ("K",) + FP]),
    (("K",) + FP, [("K",), FP]),
    (FP, [("BB",), ("HBP",)]),
    (IN_PARK, [("1B",), ("ROE", "OUT")]),
    (("ROE", "OUT"), [("OUT",), ("ROE",)]),
]
# Runs cannot see BB | HBP (0.45 vs 0.49 a time), so a runs search leaves that step
# unidentified and returns a tie. Its k comes from split_k.py's log-likelihood instead.
BATTER_K = [2 ** 6, 2 ** 2, 2 ** 4, 2 ** 3, 2 ** 6, 2 ** 5.5]      # 21 Sep; step 4 from split_k
PITCHER_STEPS = [
    (NO_2B, [("K",), FP + CONTACT]),
    (FP + CONTACT, [FP, CONTACT]),
    (FP, [("BB",), ("HBP",)]),
    (CONTACT, [("OUT",), ("ROE",), ("HR", "1B")]),
    (("HR", "1B"), [("HR",), ("1B",)]),
]
PITCHER_K = [2 ** 5, 2 ** 10, 2 ** 4, np.inf, np.inf]              # 21 Sep; step 3 from split_k


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


def build(X: np.ndarray, names: list[str], share: np.ndarray, steps, ks,
          sluggers: tuple[str, ...] = (), two_b: float = 0.0) -> np.ndarray:
    """Cards (players x CARD_LINES) and each player's HBP share of free passes, from
    counts X (players x LINES), smoothing each step toward the cohort.

    `sluggers` names the players who take the exception at the home-run step. It is a
    batting rule, so callers pass it for batters only -- matching on name alone would
    otherwise catch a two-way player on her pitcher card as well."""
    X = X.copy()
    X[:, IX["2B"]] = 0.0                     # doubles are a fixed band for everyone
    n = X.sum(axis=1)
    slug = np.isin(names, sluggers)
    everyone = cohorts(share, n, np.zeros(len(n), bool))
    no_sluggers = cohorts(share, n, slug) if slug.any() else everyone
    in_slug_cohort = np.isin(names, SLUGGER_COHORT)
    hr_step = next(s for s, (_, parts) in enumerate(steps) if ("HR",) in parts)

    prob = {NO_2B: np.ones(len(n))}
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
    tree = np.column_stack([prob[(l,)] for l in TREE_LINES])
    tree *= (1.0 - two_b)                    # the tree covers everything that is not a double
    out = np.zeros((len(n), len(CARD_LINES)))
    for j, l in enumerate(CARD_LINES):
        out[:, j] = two_b if l == "2B" else tree[:, TREE_LINES.index(l)]
    return out


def floor(cards: np.ndarray) -> np.ndarray:
    """Raise every line to at least MIN_RATE, taking the excess from the other lines
    in proportion so the row still sums to 100%. Dividing the whole row by its new
    sum would push the raised lines back under the floor.

    This belongs at the END, once a batter and a pitcher have been combined -- that
    combined distribution is what a d100 has to represent. Flooring the cards as well
    would floor twice, and a line can only be rounded up once.
    """
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
    """Cards are not floored any more, so the only invariants left are these."""
    assert np.allclose(cards.sum(axis=1), 1.0), "a card does not sum to 100%"
    assert (cards >= -1e-12).all(), "a card line is negative"


@lru_cache(maxsize=2)
def cards(side: str = "B") -> pd.DataFrame:
    """Every card on one side of the ball, as probabilities indexed by person_id.

    `main()` prints and writes these; anything that needs a card to reason with
    -- a lineup, a simulated inning -- should call this instead of reading the
    csv back, which is keyed by name and rounded to a tenth of a percent.
    Cards are NOT floored: the 1% floor belongs after a batter and a pitcher have
    been combined.
    """
    pa = plate_appearances()
    steps, ks, slug = ((BATTER_STEPS, BATTER_K, SLUGGERS) if side == "B"
                       else (PITCHER_STEPS, PITCHER_K, ()))
    players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
    counts = pd.crosstab(pa[side], pa["line"]).reindex(columns=LINES, fill_value=0)
    ids = counts.index.to_numpy()
    names = [players["person_name"].get(i, i) for i in ids]
    built = build(counts.to_numpy().astype(float), names,
                  usage(pa)[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug,
                  two_b=float(band_2b(pa)))
    check(built)
    return pd.DataFrame(built, columns=CARD_LINES, index=ids)


def band_2b(pa: pd.DataFrame) -> float:
    """The fixed doubles band. Held-out games say a flat league rate predicts better
    than either card: the batter's own rate loses to it by 3.9 SE and the pitcher is
    worse still (analysis/dice/mixture_eight.py)."""
    return float((pa["line"] == "2B").mean())


def league_card(pa: pd.DataFrame) -> pd.Series:
    """The league's own line as a card, plus its HBP share of free passes.

    The same numbers serve as the average batter and the average pitcher: every
    plate appearance has one of each, so grouping the season by batter or by
    pitcher gives the same distribution. It is not the mean of the player cards,
    which differs on each side and is not what "average" should mean here --
    this card is the L that flat log5 divides by (section 4 of the spec), so a
    player who faces it keeps her own card exactly, which is the point of an
    average opponent.
    """
    share = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
    return pd.Series({l: share[l] for l in CARD_LINES})


CARD_VERSION = "v0.3.0"                 # keep in step with data/dice/dice_version.md
REPORT_TO = "https://github.com/jgf1123/wpbl/issues"


def provenance(pa: pd.DataFrame) -> list[str]:
    """Header lines written into every card file.

    A csv outlives the page that explains it: it gets downloaded, mailed and
    quoted months later. So the file has to say for itself which games it was
    built from, that it is a draft, what it is for, and where to report a card
    that looks wrong. Readers that do not want them: `read_csv(..., comment="#")`.
    """
    commit = "uncommitted"
    try:                                        # a stamp nobody can act on is worse than none
        import subprocess
        r = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                           text=True, cwd=ALL_DIR.parent.parent, timeout=10)
        dirty = subprocess.run(["git", "status", "--porcelain"], capture_output=True,
                               text=True, cwd=ALL_DIR.parent.parent, timeout=10)
        if r.returncode == 0:
            commit = r.stdout.strip() + (" + uncommitted changes" if dirty.stdout.strip() else "")
    except Exception:
        pass
    last = str(pa["date"].max())
    return [
        f"# WPBL dice-game player cards -- {CARD_VERSION}, NOT FINAL. "
        "What changed between versions: data/dice/dice_version.md.",
        f"# Built from {pa['game_id'].nunique()} games through {last} "
        f"({len(pa)} plate appearances); code {commit}.",
        "# These FORECAST how a player would do in games we have not seen. They do not",
        "# replay 2026: a card is pulled toward players her team used about as much, so it",
        "# will not match her season line, by design (dice_game_spec.md section 3).",
        f"# A card that looks wrong is worth reporting: {REPORT_TO}",
    ]


def main() -> None:
    pd.set_option("display.width", 220)
    pa = plate_appearances()
    shares = usage(pa)
    players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
    league = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
    print(f"{pa['game_id'].nunique()} training games, {len(pa)} plate appearances")
    print("league: " + "  ".join(f"{l} {100 * league[l]:.1f}%" for l in LINES))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = provenance(pa)
    two_b = band_2b(pa)
    print(f"doubles: a fixed {100 * two_b:.2f}% band for every player, off both cards")

    for side, label, steps, ks, team_col in (("B", "batters", BATTER_STEPS, BATTER_K, "B_team"),
                                            ("P", "pitchers", PITCHER_STEPS, PITCHER_K, "P_team")):
        slug = SLUGGERS if side == "B" else ()          # a hitting rule, not a pitching one
        X = pd.crosstab(pa[side], pa["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        names = [players["person_name"].get(i, i) for i in ids]
        cards = build(X.to_numpy().astype(float), names,
                      shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug,
                      two_b=two_b)
        check(cards)
        last_team = pa.sort_values("date").groupby(side)[team_col].last()
        table = pd.DataFrame(100 * cards, columns=CARD_LINES, index=ids).round(1)
        table.insert(0, "PA" if side == "B" else "BF", X.sum(axis=1).to_numpy())
        table.insert(0, "team", [CODES.get(last_team.get(i), "?") for i in ids])
        table.insert(0, "player", names)
        table = table.sort_values(table.columns[2], ascending=False)       # most-used players first
        out = OUT_DIR / f"cards_{label}.csv"
        with out.open("w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(stamp) + "\n")
            table.to_csv(fh, index=False, lineterminator="\n")
        hr_total = float((cards[:, CARD_LINES.index("HR")] * X.sum(axis=1).to_numpy()).sum())
        print(f"\n=== {label}: {len(table)} cards -> {out} ===")
        if side == "B":
            print(f"home runs the cards produce over the same PAs: {hr_total:.1f} (actual {int(X['HR'].sum())})")
        print(table.head(12).to_string(index=False))
    lg = league_card(pa)
    check(lg.to_numpy()[None, :])
    league = pd.DataFrame([["League average batter", "-", len(pa)],
                           ["League average pitcher", "-", len(pa)]],
                          columns=["player", "team", "PA/BF"])
    for col in CARD_LINES:
        league[col] = round(100 * lg[col], 1)
    out = OUT_DIR / "cards_league.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(stamp) + "\n")
        fh.write("# The two rows are identical by construction: every plate appearance has a\n"
                 "# batter and a pitcher, so the season's outcomes are one distribution. A\n"
                 "# player facing this card keeps her own card exactly under flat log5.\n")
        league.to_csv(fh, index=False, lineterminator="\n")
    print(f"\n=== league average -> {out} ===")
    print(league.to_string(index=False))
    print("\ncheck passed: every card sums to 100% and no line is negative "
          "(the 1% floor now applies after batter and pitcher are combined)")
    print("\n" + "\n".join(stamp))


if __name__ == "__main__":
    main()
