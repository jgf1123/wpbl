"""What each batter's plate appearances were worth, two ways.

    pixi run batters
    pixi run batters --error=drop        # default is credit
    pixi run batters --hbp=split         # or pool (default) or drop

Two columns, and the gap between them is the point.

RE24 per plate appearance is what she actually contributed: the run expectancy
she handed her team when she was done, minus what she inherited, plus runs that
scored on the play. It is context-neutral with respect to score and inning --
its advantage over win probability added -- but not with respect to the bases.
Crediting the batter for the base-out state is the whole construction, so the
figure bundles her hitting with her team-mates' on-base ability and the luck of
when her hits happened to fall.

Context-neutral strips that out by linear weights: take the league-average run
value of each event type -- every single in the league pooled, bases empty and
bases loaded alike -- and re-score her plate appearances with the average
instead of what actually happened. Her outcome distribution is preserved; only
the timing is discarded. It is the classical wOBA/Batting-Runs construction,
with weights measured from this league rather than borrowed.

Sequencing does not persist, so context-neutral is the better guide to what a
batter will do next, and RE24 the better account of what she already did.


THE ATTRIBUTION DILEMMA
-----------------------

Two events are not clearly the batter's doing. The choice is recorded here
rather than buried in a constant, because it decides the middle of this table.

Reaching on an error. 54 plate appearances, 2.51% -- one in forty, and roughly
four to five times the major-league rate, because this league makes a lot of
errors. Two defensible treatments:

    credit  at its own run value, +0.547 (default). This is what RE24 does
            natively, and what the original wOBA does: Tango's construction
            carries a reached-base-on-error term. The familiar public formula
            omits it, which leaves it an at-bat with no numerator weight and
            so arithmetically an out -- but that omission is a data-
            availability compromise, not a judgement that the event is
            worthless. Reaching on an error is worth 97% of a single here
            (+0.547 against +0.566), a difference of -0.019 with a 95%
            interval of [-0.117, +0.079]: not distinguishable from a single.
    drop    remove the plate appearance from the rate entirely, on the view
            that it is the fielder's doing and cannot be attributed.

The evidence favours crediting. If reaching on an error were purely the
defence's doing, batters would differ only by chance -- and they differ by
more than that. Of the spread between batters, roughly half is real talent
rather than noise, with a stabilization point near 40 plate appearances, which
makes it better measured than batting average (90) or walk rate (119). It is
not a settled result: 18% of bootstrap resamples find no talent spread at all.
But "partly a batter skill" fits the data better than "not the batter's at
all", which is what dropping it would assert.

Hit by pitch. 74 plate appearances, 3.4% -- roughly triple the major-league
rate, and concentrated: five batters are above 11%. Crediting it is
conventional and consistent, since a walk and a hit batter put the same runner
on first and force runners identically; dropping HBP while crediting walks
cannot be justified. The two are therefore POOLED into one "free pass" weight
by default. Weighted separately they come out +0.455 and +0.389, a gap the
events cannot produce mechanically, so it is situational contamination of a
74-event weight rather than a real difference. Pooling gives n=348.

    pool    one weight for walk and HBP together (default)
    split   separate weights, as the raw event types come
    drop    remove HBP from the rate, for the view that it is pitcher wildness

Because reaching on an error is credited by default, both columns cover the
same plate appearances: RE24 keeps its ledger property, every plate
appearance's value is charged to someone, and the gap between the two columns
means sequencing alone rather than sequencing plus a difference in which plate
appearances each column saw.

More generally: a linear weight is only context-neutral if that event's mix of
situations matches the league's. Rare events -- home runs (57), HBP (74),
reached-on-error (54) -- do not have enough occurrences to guarantee that, so
their weights carry situational noise. Pooling is one fix; re-weighting each
event's situations to the league distribution would be a more thorough one and
is not done here.

Batters whose rating moves more than SENSITIVE across the option grid are
flagged, so a reader can see which figures rest on the judgement call.


Identity is keyed on person_id, not the per-game player_id: three people in
this league carry more than one player_id, and keying on the wrong one splits
a traded player in half.
"""

from __future__ import annotations

import itertools
import sys

import numpy as np
import pandas as pd

from wpbl.game_timeline import pooled_run_expectancy, re_of
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

BOOTSTRAP = 4000
SEED = 20260906
MIN_PA = 20
SENSITIVE = 0.10       # rating movement across the option grid worth flagging

# The feed labels reaching on an error "unknown", and drops one genuine out --
# an infield fly -- into the same bucket. Both are relabelled so the weights
# are not quietly contaminated.
REACHED = "reached_on_error"
FREE_PASS = "free_pass"
ERROR_CHOICES = ("credit", "drop")
HBP_CHOICES = ("pool", "split", "drop")


def option(name: str, choices: tuple[str, ...], argv: list[str]) -> str:
    for arg in argv:
        if arg.startswith(f"--{name}="):
            value = arg.split("=", 1)[1]
            if value not in choices:
                sys.exit(f"--{name} must be one of {', '.join(choices)}")
            return value
    return choices[0]


def classify(event_type: str, narrative: str) -> str:
    if event_type != "unknown":
        return event_type
    return "flyout" if "infield fly" in str(narrative or "").lower() else REACHED


def plate_appearances() -> pd.DataFrame:
    """One row per plate appearance, with the run value credited to the batter."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    players = pd.read_parquet(OUT_DIR / "players.parquet")
    person = players.set_index("player_id")["person_id"].to_dict()
    unique = players.drop_duplicates("person_id").set_index("person_id")
    re_table = pooled_run_expectancy()

    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["batting_team_id"])
            .sort_values(["game_id", "sequence"]).copy())
    live["bases"] = (live["first_base"].notna().map({True: "1", False: "_"})
                     + live["second_base"].notna().map({True: "2", False: "_"})
                     + live["third_base"].notna().map({True: "3", False: "_"}))

    rows = []
    for _, half in live.groupby(["game_id", "inning", "half"], sort=False):
        records = list(half.sort_values("sequence").itertuples())
        for i, play in enumerate(records):
            if not play.is_plate_appearance or pd.isna(play.batter_id):
                continue
            nxt = records[i + 1] if i + 1 < len(records) else None
            after = (re_of(re_table, nxt.bases, int(nxt.outs_before))
                     if nxt is not None else 0.0)
            before = re_of(re_table, play.bases, int(play.outs_before))
            pid = person.get(play.batter_id, play.batter_id)
            rows.append({
                "person_id": pid,
                "batter": unique["person_name"].get(pid, play.batter_name),
                "tm": CODES.get(unique["team_name"].get(pid), "?"),
                "event": classify(play.event_type, play.narrative),
                "run_value": after + play.runs_scored - before,
            })
    return pd.DataFrame(rows)


def neutral_values(frame: pd.DataFrame, error: str, hbp: str) -> pd.DataFrame:
    """The frame restricted to attributable plate appearances, with a linear
    weight attached to each. Weights are recomputed on whatever set survives,
    so they always describe the population being averaged."""
    kept = frame.copy()
    if hbp == "pool":
        kept["event"] = kept["event"].replace({"walk": FREE_PASS,
                                               "hit_by_pitch": FREE_PASS})
    elif hbp == "drop":
        kept = kept[kept["event"] != "hit_by_pitch"]
    if error == "drop":
        kept = kept[kept["event"] != REACHED]

    weights = kept.groupby("event")["run_value"].mean()
    return kept.assign(neutral=kept["event"].map(weights)), weights


def interval(values: np.ndarray, rng) -> tuple[float, float]:
    draws = values[rng.integers(0, len(values), size=(BOOTSTRAP, len(values)))].mean(axis=1)
    return float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def sensitivity(frame: pd.DataFrame, keep: set) -> pd.Series:
    """How far a batter's context-neutral rating moves across every option."""
    ratings = {}
    for error, hbp in itertools.product(ERROR_CHOICES, HBP_CHOICES):
        kept, _ = neutral_values(frame, error, hbp)
        kept = kept[kept["person_id"].isin(keep)]
        ratings[(error, hbp)] = kept.groupby("person_id")["neutral"].mean()
    grid = pd.DataFrame(ratings)
    return (grid.max(axis=1) - grid.min(axis=1)).rename("swing")


def main() -> None:
    pd.set_option("display.width", 250)
    error = option("error", ERROR_CHOICES, sys.argv[1:])
    hbp = option("hbp", HBP_CHOICES, sys.argv[1:])
    rng = np.random.default_rng(SEED)

    frame = plate_appearances()
    kept, weights = neutral_values(frame, error, hbp)
    sizes = frame.groupby("person_id").size()
    keep = set(sizes[sizes >= MIN_PA].index)
    swing = sensitivity(frame, keep)

    print(f"{len(frame)} plate appearances.  --error={error}  --hbp={hbp}")
    print(f"  RE24 always uses every plate appearance (it is a ledger).")
    print(f"  context-neutral uses {len(kept)} of them.\n")
    print("=== linear weights ===")
    counts = kept["event"].value_counts()
    for event, weight in weights.sort_values(ascending=False).items():
        n = counts.get(event, 0)
        print(f"   {event:18s}{weight:+7.3f}   n={n:4d}")

    rows = []
    for pid, group in frame.groupby("person_id"):
        if pid not in keep:
            continue
        mine = kept[kept["person_id"] == pid]
        if mine.empty:
            continue
        actual = group["run_value"].to_numpy()
        matched = mine["run_value"].to_numpy()      # same PAs the neutral uses
        neutral = mine["neutral"].to_numpy()
        lo, hi = interval(actual, rng)
        nlo, nhi = interval(neutral, rng)
        rows.append({"tm": group["tm"].iloc[0], "batter": group["batter"].iloc[0],
                     "pa": len(group), "re24": actual.sum(),
                     "situational": actual.mean(), "lo": lo, "hi": hi,
                     "neutral": neutral.mean(), "nlo": nlo, "nhi": nhi,
                     "gap": matched.mean() - neutral.mean(),
                     "swing": float(swing.get(pid, 0.0))})
    table = pd.DataFrame(rows).sort_values("neutral", ascending=False)

    print(f"\n\n=== {len(table)} batters with at least {MIN_PA} plate appearances ===")
    print("    runs CREATED per plate appearance -- positive is good; a batter's")
    print("    +0.20 means she added a fifth of a run. A pitcher's +0.20 in the")
    print("    pitcher table means the opposite physical thing, a fifth of a run")
    print("    PREVENTED. Both tables read downward from best to worst.")
    print("    sorted by context-neutral.  * interval clear of zero.")
    print(f"    ! rating moves more than {SENSITIVE:.2f} across the attribution options\n")
    print(f"  {'':4s}{'batter':21s}{'PA':>4s}{'RE24':>7s}"
          f"{'situational':>13s}{'':10s}{'neutral':>9s}{'':10s}{'gap':>7s}")
    for row in table.itertuples():
        s = "*" if (row.lo > 0 or row.hi < 0) else " "
        n = "*" if (row.nlo > 0 or row.nhi < 0) else " "
        flag = "!" if row.swing > SENSITIVE else " "
        print(f"{flag} {row.tm:4s}{row.batter:21s}{row.pa:4d}{row.re24:+7.1f}"
              f"{row.situational:+8.3f}{s} [{row.lo:+.2f},{row.hi:+.2f}]"
              f"{row.neutral:+8.3f}{n} [{row.nlo:+.2f},{row.nhi:+.2f}]"
              f"{row.gap:+7.3f}")

    flagged = table[table["swing"] > SENSITIVE]
    print(f"\n  intervals clear of zero: situational "
          f"{int(((table['lo'] > 0) | (table['hi'] < 0)).sum())}, context-neutral "
          f"{int(((table['nlo'] > 0) | (table['nhi'] < 0)).sum())} of {len(table)}")
    print(f"  the two orderings agree at spearman "
          f"{np.corrcoef(table['situational'].rank(), table['neutral'].rank())[0, 1]:+.3f}")
    print(f"\n  {len(flagged)} batters flagged as sensitive to the attribution choice:")
    for row in flagged.sort_values("swing", ascending=False).itertuples():
        print(f"    {row.batter:21s} neutral {row.neutral:+.3f}, "
              f"moves {row.swing:.3f} across the options")


if __name__ == "__main__":
    main()
