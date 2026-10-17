"""Do runners advance more when the pitcher is tired? The Singles and Outs Tables,
first innings against later innings.

    pixi run python analysis/dice/fatigue_advance.py

User (12 Oct): more extra-base contact later in an outing suggests runners
advance more on singles and outs too; if so the Outs and Singles Tables (and the
d12 that was chosen to fit their average) need revisiting.

Every 2026 game, outings with a first inning and at least one later inning
(the removal inning kept, variant (B) of fatigue_shape.py). Where each runner
went is read by NAME, as advance.py does (`advance.witnessed`).

  singles, runner on 2nd     share where she scored, at 0-1 out and at 2 out
  singles, runner on 1st     share where she reached 3rd or scored
  outs in play, < 2 out      B / B+ / F+ / FB+ / other, with and without a
                             runner on 1st, as the Outs Table defines them

with the rulebook's d12 shares beside them (one face = 1/12 = 8.3%).
"""
import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.advance import occupants, witnessed
from wpbl.batters import contact
from wpbl.dice import TO_LINE
from wpbl.run_expectancy import HALF_KEY, _base_code, damaged_halves

raw = tables.read("plays", "all")
damaged = damaged_halves(raw, tables.read("line_score", "all"), tables.read("games", "all").set_index("game_id"))
raw = raw.assign(half_key=list(map(tuple, raw[HALF_KEY].values)))
raw = raw[~raw["half_key"].isin(damaged)].sort_values(["game_id", "sequence"])

# outing and inning-of-outing for every plate appearance
pa_rows = raw[(raw["play_kind"] == "plate_appearance") & (raw["outs_before"] < 3)]
inn = {}
for (g, pid), grp in pa_rows.groupby(["game_id", "pitcher_id"], sort=False):
    order = list(dict.fromkeys(grp["inning"]))
    for i in order:
        inn[(g, pid, i)] = (order.index(i) + 1, len(order))
both = {k[:2] for k, (n, tot) in inn.items() if n >= 2}

rows = []
for key, half in raw.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for i, play in enumerate(live):
        if play.play_kind != "plate_appearance" or i + 1 >= len(live):
            continue
        nxt = live[i + 1]
        if (play.game_id, play.pitcher_id) not in both:
            continue
        n, _ = inn.get((play.game_id, play.pitcher_id, play.inning), (None, None))
        if n is None:
            continue
        outcome = contact(play.event_type, play.narrative)
        line = TO_LINE.get(outcome, "OUT")
        before, after = occupants(play), occupants(nxt)
        outs_added = int(nxt.outs_before) - int(play.outs_before)
        dests, ambiguous, mismatch = witnessed(before, after, play.batter_name,
                                               int(play.runs_scored), outs_added)
        rows.append(dict(group="first" if n == 1 else "later", line=line, outcome=outcome,
                         outs=int(play.outs_before), bases=set(before), dests=dests,
                         outs_added=outs_added, ambiguous=ambiguous))
# the last play of a half-inning leads to its third out, which the next play cannot show;
# outs in play with fewer than 2 out never end the inning, so they are all observed
r = pd.DataFrame(rows)
print(f"{len(r)} plate appearances in {len(both)} outings with a first and a later inning\n")


def share(mask_num, mask_den):
    return f"{100 * mask_num.sum() / max(mask_den.sum(), 1):5.1f}% ({int(mask_num.sum())}/{int(mask_den.sum())})"


single = r["outcome"] == "single"
on2 = r["bases"].apply(lambda b: 2 in b)
on1 = r["bases"].apply(lambda b: 1 in b)
dest = lambda base: r["dests"].apply(lambda d: d.get(base, -1))
print("SINGLES                                   first innings      later innings     rulebook")
for label, outs_m, book in (("runner on 2nd scores, 0-1 out", r["outs"] < 2, 5 / 12),
                            ("runner on 2nd scores, 2 out", r["outs"] == 2, 8 / 12)):
    den = single & on2 & outs_m
    num = den & (dest(2) == 4)
    print(f"  {label:38s} " + "  ".join(share(num & (r["group"] == g), den & (r["group"] == g))
                                        for g in ("first", "later")) + f"   {100 * book:.1f}%")
for label, outs_m, book in (("runner on 1st to 3rd or home, 0-1 out", r["outs"] < 2, 2 / 12),
                            ("runner on 1st to 3rd or home, 2 out", r["outs"] == 2, 3 / 12)):
    den = single & on1 & outs_m
    num = den & (dest(1) >= 3)
    print(f"  {label:38s} " + "  ".join(share(num & (r["group"] == g), den & (r["group"] == g))
                                        for g in ("first", "later")) + f"   {100 * book:.1f}%")


def flavour(row):
    d, b = row["dests"], row["bases"]
    bat = d.get(0, 0)
    if 1 in b:
        r1 = d.get(1, -1)
        if row["outs_added"] == 2 and bat == 0 and r1 == 0:
            return "FB+"
        if row["outs_added"] == 1 and bat == 1 and r1 == 0:
            return "F+"
        if row["outs_added"] == 1 and bat == 0:
            held = all(d.get(x, -1) == x for x in b)
            moved = all(d.get(x, -1) > x for x in b)
            return "B" if held else "B+" if moved else "other"
        return "other"
    if row["outs_added"] == 1 and bat == 0:
        held = all(d.get(x, -1) == x for x in b)
        moved = all(d.get(x, -1) > x for x in b)
        return "B" if held else "B+" if moved else "other"
    return "other"


outs = r[(r["line"] == "OUT") & (r["outs"] < 2) & (r["bases"].apply(len) > 0)].copy()
outs["flavour"] = outs.apply(flavour, axis=1)
outs["on1"] = outs["bases"].apply(lambda b: 1 in b)
book = {False: {"B": 5, "B+": 7}, True: {"FB+": 2, "F+": 2, "B": 6, "B+": 2}}
for has1 in (False, True):
    print(f"\nOUTS IN PLAY, < 2 out, {'runner on 1st' if has1 else 'runners but none on 1st'}"
          f"       first innings      later innings     rulebook")
    sub = outs[outs["on1"] == has1]
    for f in (["B", "B+", "other"] if not has1 else ["FB+", "F+", "B", "B+", "other"]):
        cells = []
        for g in ("first", "later"):
            gg = sub[sub["group"] == g]
            cells.append(share(gg["flavour"] == f, gg["flavour"] == gg["flavour"]))
        bk = book[has1].get(f)
        print(f"  {f:38s} " + "  ".join(cells) + (f"   {100 * bk / 12:.1f}%" if bk else "      -"))
