"""Post numbers from the free-pass cards (wpbl.dice), 8-line run values via the d10 split."""
import numpy as np
import pandas as pd
from wpbl import tables, dice
from wpbl.batters import plate_appearances

L8 = dice.LINES
pa = dice.plate_appearances()
shares = dice.usage(pa)
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
X = pd.crosstab(pa["B"], pa["line"]).reindex(columns=L8, fill_value=0)
ids = X.index.to_numpy()
names = [players["person_name"].get(i, i) for i in ids]
c7, hs = dice.build(X.to_numpy().astype(float), names, shares["B"].reindex(ids).fillna(0.0).to_numpy(),
                    dice.BATTER_STEPS, dice.BATTER_K, dice.SLUGGERS)
fp = c7[:, 1]
cards = np.column_stack([c7[:, 0], fp * (1 - hs), fp * hs, c7[:, 2:]])     # back to 8 lines
n = X.sum(axis=1).to_numpy()
raw = X.to_numpy() / n[:, None]
lw = plate_appearances("training")
lw["line"] = lw["outcome"].map(dice.TO_LINE).fillna("OUT")
w = lw.groupby("line")["run_value"].mean().reindex(L8).to_numpy()
L = X.sum().to_numpy() / X.to_numpy().sum()
wa = float(L @ w)
val = lambda M: 1000 * ((M - L) @ (w - wa))
reg = n >= 25
print(f"spread: raw {val(raw)[reg].std(ddof=1):.0f}, card {val(cards)[reg].std(ddof=1):.0f}")
for nm in ("Denae Benites", "Ashton Lansdell", "Kelsie Whitmore", "Alexia Jorge", "Caitlin Eynon", "Jamie Mackay",
           "Joely Leguizamon", "Andreanne Leblanc", "Natsuki Yonetani"):
    i = names.index(nm)
    print(f"{nm:18s} raw {val(raw[i]):4.0f} card {val(cards[i]):4.0f} change {val(cards[i]) - val(raw[i]):+4.0f} | "
          + " ".join(f"{l} {100 * raw[i, j]:.1f}->{100 * cards[i, j]:.1f}" for j, l in enumerate(L8)))
bip = lambda r: (r[4] + r[5]) / (r[4] + r[5] + r[6] + r[7])
for nm in ("Denae Benites", "Kelsie Whitmore"):
    i = names.index(nm)
    print(f"{nm}: hits per ball in the park raw {bip(raw[i]):.3f}, card {bip(cards[i]):.3f}")
i = names.index("Denae Benites")
to = lambda r: r[0] + r[1] + r[2] + r[3]
print(f"Benites true-outcome share: raw {100 * to(raw[i]):.1f}, card {100 * to(cards[i]):.1f}")
print(f"card HR total {float((cards[:, 3] * n).sum()):.1f}")
