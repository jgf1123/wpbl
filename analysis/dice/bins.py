"""How wide does each bin have to be, and what fills the rest of it?

    pixi run python analysis/dice/bins.py

The mechanic: the d100 is cut into bins of fixed width. A bin carries a mixing
weight a -- read the pitcher's version of that bin with probability a, the
batter's otherwise. Within a bin, each card spreads that bin's width over the
lines the bin covers.

The width is not free. If a line lives in exactly one bin, then for every player
the bin's lines must total exactly the bin's width, which no fixed width can do
for everyone. So each bin needs a filler line whose share absorbs the slack, and
then:

    width >= max over players of (the owned lines' total)

or the filler goes negative and the card cannot be printed. This computes those
maxima from the real cards, checks the widths fit inside 100, and measures what
the scheme costs against reading each line at its own best weight.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import CARD_LINES, band_2b, cards, plate_appearances

pd.set_option("display.width", 240)
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
B, P = cards("B"), cards("P")
IX = {l: i for i, l in enumerate(CARD_LINES)}
TWO_B = band_2b(pa)

# best weight per line, from mixture_eight.py
ALPHA = {"K": 0.30, "BB": 0.70, "HBP": 0.20, "HR": 0.15,
         "1B": 0.30, "2B": None, "ROE": 0.85, "OUT": 0.35}

# candidate bins: owned lines grouped by how close their weights are, plus a filler
PLANS = {
    "3 bins (pitcher / batter / middle)": {
        "pitcher-leaning": (["BB", "ROE"], 0.75),
        "batter-leaning": (["HR", "HBP"], 0.18),
        "middle": (["K", "1B"], 0.32),
    },
    "2 bins (pitcher / rest)": {
        "pitcher-leaning": (["BB", "ROE"], 0.75),
        "rest": (["K", "HR", "HBP", "1B"], 0.28),
    },
    "4 bins (split the middle)": {
        "pitcher-leaning": (["BB", "ROE"], 0.75),
        "batter-leaning": (["HR", "HBP"], 0.18),
        "strikeouts": (["K"], 0.30),
        "singles": (["1B"], 0.30),
    },
}
FILLER = "OUT"

print(f"doubles take a fixed {100 * TWO_B:.2f}% band outside every bin.")
print(f"the filler line is {FILLER}: league {100 * (pa['line'] == 'OUT').mean():.1f}%, "
      f"card range {100 * min(B[FILLER].min(), P[FILLER].min()):.1f}"
      f"-{100 * max(B[FILLER].max(), P[FILLER].max()):.1f}%\n")

for plan_name, plan in PLANS.items():
    rows, total = [], 0.0
    ok = True
    for bin_name, (owned, a) in plan.items():
        mb = B[owned].sum(axis=1)
        mp = P[owned].sum(axis=1)
        width = max(mb.max(), mp.max())
        who = nm.get(mb.idxmax(), "?") if mb.max() >= mp.max() else nm.get(mp.idxmax(), "?")
        total += width
        rows.append({"bin": bin_name, "owns": "+".join(owned), "a": a,
                     "width needed": f"{100 * width:.1f}%",
                     "set by": who,
                     "league total of owned": f"{100 * sum((pa['line'] == l).mean() for l in owned):.1f}%",
                     "filler left, median": f"{100 * (width - np.median(np.r_[mb, mp])):.1f}%"})
    slack = 1 - TWO_B - total
    print(f"=== {plan_name} ===")
    print(pd.DataFrame(rows).to_string(index=False))
    print(f"  bins total {100 * total:.1f}% + doubles {100 * TWO_B:.1f}% "
          f"= {100 * (total + TWO_B):.1f}%; {FILLER}-only bin gets the remaining "
          f"{100 * slack:.1f}%" + ("" if slack > 0 else "   <-- DOES NOT FIT"))
    # does every player have enough OUT to fill every bin?
    short = 0
    for card in (B, P):
        need = sum(max(0.0, max(card[o].sum(axis=1).max(), 0)) for o, _ in plan.values())
        for i in range(len(card)):
            row = card.iloc[i]
            filler_needed = sum(width_ - row[o].sum() for (o, _), width_ in
                                zip(plan.values(), [max(B[o].sum(axis=1).max(), P[o].sum(axis=1).max())
                                                    for o, _ in plan.values()]))
            if row[FILLER] < filler_needed - 1e-9:
                short += 1
    print(f"  players whose {FILLER} line is too small to fill their bins: {short} of {len(B) + len(P)}\n")
