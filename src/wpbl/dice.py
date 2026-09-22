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
FIXED = ("2B", "ROE")        # league bands: no real spread on either side
TREE_LINES = [l for l in CARD_LINES if l not in FIXED]
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
CONTACT = ("HR", "1B", "OUT")
TRUE_OUTCOMES = ("K", "BB", "HBP", "HR")
IN_PARK = ("1B", "OUT")
NO_FIXED = tuple(l for l in LINES if l not in FIXED)
BATTER_STEPS = [
    (NO_FIXED, [TRUE_OUTCOMES, IN_PARK]),
    (TRUE_OUTCOMES, [("HR",), ("K",) + FP]),
    (("K",) + FP, [("K",), FP]),
    (FP, [("BB",), ("HBP",)]),
    (IN_PARK, [("1B",), ("OUT",)]),
]
# --- the table ---------------------------------------------------------------
# One d100 roll resolves a plate appearance. The cells are split in fixed blocks:
#
#   00-32  read the PITCHER's card      33 cells
#   33-36  double                        4 cells   league band, on neither card
#   37-38  reached on error              2 cells   league band, on neither card
#   39-44  RUNNING PLAY                  6 cells   not a plate appearance at all
#   45-99  read the BATTER's card       55 cells
#
# Reading one card or the other IS the combination rule: it sums to 100% because
# exactly one card is read, needs no arithmetic, and beat log5, the additive
# shortcut and every zero-sum shift on held-out games (analysis/dice/mixture.py).
#
# The running-play block is the odd one out: a wild pitch, passed ball or balk
# advances every runner and the roll is TAKEN AGAIN, so those six cells do not
# resolve a plate appearance. A card is therefore a distribution over the 94
# cells that do, not over all 100 -- which is why the bands divide by PA_CELLS.
# With the bases empty the block is a plain reroll, about once every 43 plate
# appearances. Six cells, not the four the old "4.2% of rolls" implied: every
# one of the 117 running plays on record happened with a runner on, so the
# block is dead 39% of the time and has to be bigger to land the same rate
# (analysis/dice/running_plays.py).
P_CELLS, B_CELLS = 33, 55
BAND_CELLS = {"2B": 4, "ROE": 2}
RUN_CELLS = 6                                  # wild pitch / passed ball / balk
PA_CELLS = P_CELLS + B_CELLS + sum(BAND_CELLS.values())   # 94: the cells that end a PA
MIX_ALPHA = P_CELLS / (P_CELLS + B_CELLS)      # 0.375 exactly: the pitcher's share of the tree
# Runs cannot see BB | HBP (a walk is worth 0.45, an HBP 0.49), so that step's k is
# fitted on log loss (spec 9.0); every other k is fitted on runs at MIX_ALPHA. The
# two interact -- mixing is itself shrinkage -- so they were fitted together by
# coordinate descent from six starts, all converging here (joint_runs.py).
BATTER_K = [2 ** 4, 2 ** 1, 2 ** 4, 2 ** 1.5, 2 ** 5.5]   # step 4: split_k_final
PITCHER_STEPS = [
    (NO_FIXED, [("K",), FP + CONTACT]),
    (FP + CONTACT, [FP, CONTACT]),
    (FP, [("BB",), ("HBP",)]),
    (CONTACT, [("OUT",), ("HR", "1B")]),
    (("HR", "1B"), [("HR",), ("1B",)]),
]
PITCHER_K = [2 ** 0, 2 ** 6, 2 ** 1.5, np.inf, np.inf]    # step 3: split_k_final


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
          sluggers: tuple[str, ...] = (), bands: dict | None = None) -> np.ndarray:
    """Cards (players x CARD_LINES) and each player's HBP share of free passes, from
    counts X (players x LINES), smoothing each step toward the cohort.

    `sluggers` names the players who take the exception at the home-run step. It is a
    batting rule, so callers pass it for batters only -- matching on name alone would
    otherwise catch a two-way player on her pitcher card as well."""
    bands = bands or {}
    X = X.copy()
    for l in FIXED:                          # fixed bands: same on every card
        X[:, IX[l]] = 0.0
    n = X.sum(axis=1)
    slug = np.isin(names, sluggers)
    everyone = cohorts(share, n, np.zeros(len(n), bool))
    no_sluggers = cohorts(share, n, slug) if slug.any() else everyone
    in_slug_cohort = np.isin(names, SLUGGER_COHORT)
    hr_step = next(s for s, (_, parts) in enumerate(steps) if ("HR",) in parts)

    prob = {NO_FIXED: np.ones(len(n))}
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
    tree *= (1.0 - sum(bands.values()))      # the tree covers what the bands do not
    out = np.zeros((len(n), len(CARD_LINES)))
    for j, l in enumerate(CARD_LINES):
        out[:, j] = bands[l] if l in bands else tree[:, TREE_LINES.index(l)]
    return out


def to_cells(card: np.ndarray, block: int, weights: np.ndarray,
             floor_one: bool) -> np.ndarray:
    """A card's tree lines as whole d100 cells summing to `block`.

    Nearest first, then the shortfall or surplus is spent wherever it leaves the
    card's RUN VALUE closest to the unrounded card -- not on the largest line,
    which would let Out absorb every rounding error the way it used to absorb
    the mixing offset.

    `floor_one` gives every line at least one cell. It is used for PITCHERS only.
    A line at zero on both cards cannot happen at all, and on the batter side the
    fix is ruinous: 42 of 67 batters are owed under a tenth of a cell of home
    runs, so flooring them inflates the league by 16%. Pitcher cards take the
    cohort's mix on several steps, so they sit near league rates and only five
    entries in the whole set round to zero -- flooring those costs 2%, and closes
    every hole on its own, because pitcher + batter is then always at least one.
    """
    p = card[:, [CARD_LINES.index(l) for l in TREE_LINES]]
    exact = p / p.sum(axis=1, keepdims=True) * block
    cells = np.maximum(np.rint(exact).astype(int), 1 if floor_one else 0)
    low = 1 if floor_one else 0
    for i in range(len(cells)):
        while cells[i].sum() != block:
            step = 1 if cells[i].sum() < block else -1
            best, err = None, np.inf
            for j in range(len(TREE_LINES)):
                if step < 0 and cells[i, j] <= low:
                    continue
                c = cells[i].copy()
                c[j] += step
                e = abs(float((c - exact[i]) @ weights))
                if e < err:
                    best, err = c, e
            cells[i] = best
    return cells


def line_weights() -> np.ndarray:
    """Run value of each tree line, for deciding where rounding hurts least."""
    from wpbl.batters import plate_appearances as _pa
    lw = _pa("training").copy()
    lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
    return lw.groupby("line")["run_value"].mean().reindex(TREE_LINES).to_numpy()


def ranges(cells: np.ndarray, start: int) -> list[str]:
    """Cell numbers each line owns, as a player reads them off the card."""
    out, at = [], start
    for n in cells:
        if n == 0:
            out.append("-")
        elif n == 1:
            out.append(f"{at:02d}")
        else:
            out.append(f"{at:02d}-{at + n - 1:02d}")
        at += int(n)
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
                  bands=bands(pa))
    check(built)
    return pd.DataFrame(built, columns=CARD_LINES, index=ids)


def bands(pa: pd.DataFrame) -> dict[str, float]:
    """The fixed league bands: doubles and reached-on-error.

    Neither has real spread worth printing. Doubles: a flat league rate beats the
    batter's own record by 3.9 SE and the pitcher is worse still. Errors: no real
    spread on EITHER side -- both method-of-moments k are infinite -- so the
    pitcher's apparent edge was his cohort's usage tier, not his own fielders
    (analysis/dice/line_owner.py).

    The printed levels are whole cells, 4 and 2, against the measured 4.54% and
    2.22%. They divide by PA_CELLS, not by 100: the six running-play cells do not
    end a plate appearance, so a card is a distribution over the 94 that do. That
    puts doubles at 4/94 = 4.26% and errors at 2/94 = 2.13%. Flat levels in this
    region score no worse than the measured rate and nominally better (flat 4%
    -0.007, SE 0.490; flat 5% -0.151, SE 0.348; errors at 2% -0.236, SE 0.308),
    and marking a bonus group of doublers is worse at every size
    (analysis/dice/band_two_level.py)."""
    return {l: BAND_CELLS[l] / PA_CELLS for l in FIXED}


def league_card(pa: pd.DataFrame) -> pd.Series:
    """The league's own line as a card, plus its HBP share of free passes.

    The same numbers serve as the average batter and the average pitcher: every
    plate appearance has one of each, so grouping the season by batter or by
    pitcher gives the same distribution. It is not the mean of the player cards,
    which differs on each side and is not what "average" should mean here.
    (The original argument was a log5 identity -- the league card is the L a
    matchup divides by, so a player facing it keeps her own card exactly. That
    no longer applies under the mixture of section 4, where facing the league
    card shrinks her toward league by the mixing weight. The definition stands
    on the one-distribution argument alone.)
    """
    share = pa["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
    return pd.Series({l: share[l] for l in CARD_LINES})


CARD_VERSION = "v0.5.0"                 # keep in step with data/dice/dice_version.md
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
    band = bands(pa)
    W_LINE = line_weights()
    print("fixed bands, off both cards: " + ", ".join(f"{l} {100 * v:.2f}%" for l, v in band.items()))

    for side, label, steps, ks, team_col in (("B", "batters", BATTER_STEPS, BATTER_K, "B_team"),
                                            ("P", "pitchers", PITCHER_STEPS, PITCHER_K, "P_team")):
        slug = SLUGGERS if side == "B" else ()          # a hitting rule, not a pitching one
        X = pd.crosstab(pa[side], pa["line"]).reindex(columns=LINES, fill_value=0)
        ids = X.index.to_numpy()
        names = [players["person_name"].get(i, i) for i in ids]
        cards = build(X.to_numpy().astype(float), names,
                      shares[side].reindex(ids).fillna(0.0).to_numpy(), steps, ks, slug,
                      bands=band)
        check(cards)
        last_team = pa.sort_values("date").groupby(side)[team_col].last()
        block = P_CELLS if side == "P" else B_CELLS
        start = 0 if side == "P" else P_CELLS + sum(BAND_CELLS.values()) + RUN_CELLS
        cells = to_cells(cards, block, W_LINE, floor_one=(side == "P"))
        assert (cells.sum(axis=1) == block).all(), "a card does not fill its block"
        if side == "P":
            assert (cells >= 1).all(), "a pitcher card has an empty line"
        table = pd.DataFrame(cells, columns=[f"{l} cells" for l in TREE_LINES], index=ids)
        for j, l in enumerate(TREE_LINES):
            table[l] = [r[j] for r in (ranges(c, start) for c in cells)]
        table = table[[c for l in TREE_LINES for c in (f"{l} cells", l)]]
        table.insert(0, "PA" if side == "B" else "BF", X.sum(axis=1).to_numpy())
        table.insert(0, "team", [CODES.get(last_team.get(i), "?") for i in ids])
        table.insert(0, "player", names)
        table = table.sort_values(table.columns[2], ascending=False)       # most-used players first
        out = OUT_DIR / f"cards_{label}.csv"
        with out.open("w", encoding="utf-8", newline="") as fh:
            fh.write("\n".join(stamp) + "\n")
            table.to_csv(fh, index=False, lineterminator="\n")
        drift = np.abs((cells / 100 - cards[:, [CARD_LINES.index(l) for l in TREE_LINES]]
                        * (block / 100) / cards[:, [CARD_LINES.index(l) for l in TREE_LINES]]
                        .sum(axis=1, keepdims=True)) @ W_LINE)
        hr_total = float((cards[:, CARD_LINES.index("HR")] * X.sum(axis=1).to_numpy()).sum())
        print(f"\n  cells: {block} per card, "
              f"mean rounding cost {1000 * drift.mean():.2f} x1e-3 runs, "
              f"worst {1000 * drift.max():.2f}")
        print(f"\n=== {label}: {len(table)} cards -> {out} ===")
        if side == "B":
            print(f"home runs the cards produce over the same PAs: {hr_total:.1f} (actual {int(X['HR'].sum())})")
        print(table.head(12).to_string(index=False))
    lg = league_card(pa)
    check(lg.to_numpy()[None, :])
    league = pd.DataFrame([["League average batter", "-", len(pa)],
                           ["League average pitcher", "-", len(pa)]],
                          columns=["player", "team", "PA/BF"])
    # Both a percentage and a cell count: the percentages are the league's own
    # rates, handy for checking what is typical; the cells are what a stand-in
    # card would actually print for a player who has none.
    lg_cells = {"B": to_cells(lg.to_numpy()[None, :], B_CELLS, W_LINE, False)[0],
                "P": to_cells(lg.to_numpy()[None, :], P_CELLS, W_LINE, True)[0]}
    for col in CARD_LINES:
        league[f"{col} %"] = round(100 * lg[col], 2)
    for j, l in enumerate(TREE_LINES):
        league[f"{l} cells"] = [lg_cells["B"][j], lg_cells["P"][j]]
        league[l] = [ranges(lg_cells["B"], P_CELLS + sum(BAND_CELLS.values()) + RUN_CELLS)[j],
                     ranges(lg_cells["P"], 0)[j]]
    for l, n in BAND_CELLS.items():
        league[f"{l} cells"] = n
        league[l] = ranges([n], P_CELLS + sum(
            BAND_CELLS[k] for k in BAND_CELLS if list(BAND_CELLS).index(k)
            < list(BAND_CELLS).index(l)))[0]
    out = OUT_DIR / "cards_league.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        fh.write("\n".join(stamp) + "\n")
        fh.write("# The two rows are identical by construction: every plate appearance has a\n"
                 "# batter and a pitcher, so the season's outcomes are one distribution. A\n"
                 "# player facing this card is shrunk toward it by the mixing weight.\n")
        league.to_csv(fh, index=False, lineterminator="\n")
    print(f"\n=== league average -> {out} ===")
    print(league.to_string(index=False))
    print("\ncheck passed: every card sums to 100% and no line is negative "
          "(the 1% floor now applies after batter and pitcher are combined)")
    print("\n" + "\n".join(stamp))


if __name__ == "__main__":
    main()
