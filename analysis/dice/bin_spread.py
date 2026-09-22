"""What does each bin actually hold, across every card -- not just the average one?

    pixi run python analysis/dice/bin_spread.py

The bin tables printed so far were the layout of a league-average player. Every
card has its own boundaries, so a bin that is one line on the average card can be
two or three on a real one. That spread is the cost of one weight per bin: the
weight is fitted across whatever mixture of lines the bin holds league-wide.
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.dice import CARD_LINES, bands, cards, plate_appearances

pd.set_option("display.width", 240)
NBIN = 10
ORDER = ["HR", "1B", "OUT", "HBP", "K", "BB"]
pa = plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
nm = players["person_name"]
IX = {l: i for i, l in enumerate(CARD_LINES)}
ORD_I = [IX[l] for l in ORDER]


def shares(card):
    p = card[:, ORD_I]
    p = p / p.sum(axis=1, keepdims=True)
    edges = np.cumsum(p, axis=1)
    lo = np.concatenate([np.zeros((len(p), 1)), edges[:, :-1]], axis=1)
    out = np.zeros((len(p), NBIN, len(ORD_I)))
    for j in range(NBIN):
        a, b = j / NBIN, (j + 1) / NBIN
        out[:, j, :] = np.clip(np.minimum(edges, b) - np.maximum(lo, a), 0, None) * NBIN
    return out


B, P = cards("B"), cards("P")
allc = np.vstack([B.to_numpy(), P.to_numpy()])
names = [nm.get(i, i) for i in list(B.index) + list(P.index)]
S = shares(allc)
print(f"{len(allc)} cards ({len(B)} batters, {len(P)} pitchers), "
      f"bands set aside: {', '.join(f'{k} {100 * v:.2f}%' for k, v in bands(pa).items())}\n")

rows = []
for j in range(NBIN):
    s = S[:, j, :]
    dom = s.argmax(axis=1)
    main = np.bincount(dom, minlength=len(ORDER)).argmax()
    pure = int((s[:, main] > 0.999).sum())
    rows.append({"bin": j + 1,
                 "usual line": ORDER[main],
                 "cards where it is that line alone": f"{pure}/{len(allc)}",
                 "its share: median": f"{100 * np.median(s[:, main]):.0f}%",
                 "10th pct": f"{100 * np.percentile(s[:, main], 10):.0f}%",
                 "lines appearing at all": ", ".join(
                     ORDER[i] for i in range(len(ORDER)) if (s[:, i] > 0.005).mean() > 0.05)})
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== bin 10 in detail ===")
s10 = S[:, 9, :]
d = pd.DataFrame(100 * s10, columns=ORDER, index=names).round(1)
d = d.loc[:, (d > 0.05).any()]
print(f"  cards whose bin 10 is walks alone: {int((s10[:, ORDER.index('BB')] > 0.999).sum())}"
      f" of {len(allc)}")
print(f"  walk share of bin 10: median {100 * np.median(s10[:, ORDER.index('BB')]):.0f}%, "
      f"range {100 * s10[:, ORDER.index('BB')].min():.0f}-"
      f"{100 * s10[:, ORDER.index('BB')].max():.0f}%")
print("\n  the six cards whose bin 10 is least like walks:")
print(d.assign(_s=s10[:, ORDER.index("BB")]).sort_values("_s").head(6).drop(columns="_s").to_string())
