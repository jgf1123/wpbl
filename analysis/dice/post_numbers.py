"""Player numbers quoted in the blog draft, read off the current cards.

    pixi run python analysis/dice/post_numbers.py

Reads `dice.cards()` rather than rebuilding: since v0.3.0 the module's own card
IS the eight-line card, so there is nothing left to reassemble. Note that 2B and
ROE are league bands now, identical on every card, so any rate combining them
with a player's own lines -- hits per ball in play, most obviously -- is part her
and part the league on the card side but all her on the raw side.
"""
import numpy as np
import pandas as pd

from wpbl import dice, tables
from wpbl.batters import plate_appearances

NAMED = ("Denae Benites", "Ashton Lansdell", "Kelsie Whitmore", "Alexia Jorge",
         "Caitlin Eynon", "Jamie Mackay", "Joely Leguizamon", "Andreanne Leblanc",
         "Skylar Kaplan", "Natsuki Yonetani", "Samaria Benitez")
LINES = dice.CARD_LINES
pd.set_option("display.width", 250)
pa = dice.plate_appearances()
players = tables.read("players", "training").drop_duplicates("person_id").set_index("person_id")
B = dice.cards("B")
names = [players["person_name"].get(i, i) for i in B.index]
X = pd.crosstab(pa["B"], pa["line"]).reindex(columns=LINES, fill_value=0).reindex(B.index).fillna(0)
n = X.sum(axis=1).to_numpy()
raw = X.to_numpy() / n[:, None]
cards = B.to_numpy()

lw = plate_appearances("training")
lw["line"] = lw["outcome"].map(dice.TO_LINE).fillna("OUT")
w = lw.groupby("line")["run_value"].mean().reindex(LINES).to_numpy()
L = X.sum().to_numpy() / X.to_numpy().sum()
wa = float(L @ w)
val = lambda M: 1000 * ((M - L) @ (w - wa))
reg = n >= 25
print(f"{int(reg.sum())} batters with 25+ PA; spread raw {val(raw)[reg].std(ddof=1):.0f}, "
      f"card {val(cards)[reg].std(ddof=1):.0f}\n")

print("=== runs above an average PA, x1000 (Table 3) ===")
rows = []
for nm in NAMED:
    i = names.index(nm)
    rows.append({"player": nm, "PA": int(n[i]), "season": round(val(raw[i])),
                 "card": round(val(cards[i])), "change": round(val(cards[i]) - val(raw[i]))})
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== every line, raw -> card (%) ===")
for nm in NAMED:
    i = names.index(nm)
    print(f"  {nm:18s} " + "  ".join(f"{l} {100 * raw[i, j]:.1f}->{100 * cards[i, j]:.1f}"
                                     for j, l in enumerate(LINES)))

j1b, j2b, jroe, jout = (LINES.index(l) for l in ("1B", "2B", "ROE", "OUT"))
bip = lambda r: (r[j1b] + r[j2b]) / (r[j1b] + r[j2b] + r[jroe] + r[jout])
print("\n=== hits per ball in play (1B+2B over balls in play) ===")
print(f"  {'league':18s} {bip(L):.3f}")
for nm in ("Denae Benites", "Kelsie Whitmore", "Ashton Lansdell"):
    i = names.index(nm)
    print(f"  {nm:18s} raw {bip(raw[i]):.3f}, card {bip(cards[i]):.3f}")

to = lambda r: r[:4].sum()
i = names.index("Denae Benites")
print(f"\nBenites true-outcome share: raw {100 * to(raw[i]):.1f}%, card {100 * to(cards[i]):.1f}%")
print(f"Benites 1B as a share of her balls in play: raw "
      f"{100 * raw[i, j1b] / (raw[i, j1b] + raw[i, jout]):.0f}%, card "
      f"{100 * cards[i, j1b] / (cards[i, j1b] + cards[i, jout]):.0f}%")

jhr = LINES.index("HR")
print(f"\nseason HR: actual {int((pa['line'] == 'HR').sum())}, cards {float((cards[:, jhr] * n).sum()):.1f}")
hr = X["HR"].to_numpy()
top = np.argsort(-hr)[:5]
print("most home runs: " + ", ".join(f"{names[i]} {int(hr[i])}" for i in top))
