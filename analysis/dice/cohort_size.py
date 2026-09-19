"""Minimum cohort size per card line (N >= 4k), and how many neighbours that spans."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 220)
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE"]
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs")

for side, col, floor in (("pitchers", "pitcher_id", 40), ("batters", "batter_id", 25)):
    pid = pa[col].map(person).fillna(pa[col])
    x = pd.crosstab(pid, pa["line"])
    n = x.sum(axis=1)
    L = x.sum() / n.sum()
    qual = n >= floor
    rows = []
    for line in LINES:
        r = x[line] / n
        obs = float(np.var(r[qual], ddof=1))
        noise = float((L[line] * (1 - L[line]) / n[qual]).mean())
        tau2 = obs - noise
        k = L[line] * (1 - L[line]) / tau2 if tau2 > 0 else np.inf
        rows.append({"line": line, "league %": round(100 * L[line], 1),
                     "real spread SD (pts)": round(100 * np.sqrt(max(tau2, 0)), 2),
                     "k": round(k) if np.isfinite(k) else "inf (no real spread)",
                     "min cohort 4k": round(4 * k) if np.isfinite(k) else "-"})
    t = pd.DataFrame(rows)
    print(f"\n=== {side}: {int(qual.sum())} with {floor}+ used for the spread; {len(n)} in all, {int(n.sum())} PAs ===")
    print(t.to_string(index=False))

    # how many neighbours (by PA order, excluding the player) make up a cohort of a given size
    order = n.sort_values()
    sizes = sorted({v for v in t["min cohort 4k"] if v != "-"})
    print(f"  neighbours needed to reach each cohort size, excluding the player herself:")
    picks = {"fewest PA": order.index[0], "median PA": order.index[len(order) // 2],
             "3rd most": order.index[-3], "most PA": order.index[-1]}
    for label, who in picks.items():
        pos = list(order.index).index(who)
        cells = []
        for size in sizes:
            # grow a window outward from her position, alternating sides, until it holds `size` PAs
            lo, hi, got, count = pos - 1, pos + 1, 0, 0
            while got < size and (lo >= 0 or hi < len(order)):
                take_hi = hi < len(order) and (lo < 0 or (count % 2 == 0))
                j = hi if take_hi else lo
                got += order.iloc[j]; count += 1
                if take_hi: hi += 1
                else: lo -= 1
            cells.append(f"{size} PA -> {count}")
        print(f"    {label} ({name.get(who, who)}, {int(order[who])} PA): " + "; ".join(cells))
