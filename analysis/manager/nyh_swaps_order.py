"""NYH one-swap run gains from the conventions nine, and best vs real-style vs by-bat batting orders for every team.

    pixi run python analysis/manager/nyh_swaps_order.py
"""
import re, unicodedata, itertools
import pandas as pd
from wpbl import manager as M, play, play_lineup, tables, usage
cards, wp = play.shared(); m = M.Model(cards, wp); m.usage = usage.Usage(cards)
p_line = play_lineup.league_table().p_line
blocks = {}
def blk(n):
    if n not in blocks:
        blocks[n] = play_lineup.batter_blocks(p_line, m.bat_faces[n])
    return blocks[n]
def runs(order):
    return play_lineup.expected_runs({n: blk(n) for n in order}, list(order))
def best(names):
    return play_lineup.local_best({n: blk(n) for n in names}, sorted(names, key=lambda n: -m.bat_score(n)), {})

print("== 1. NYH: one swap at a time, runs per 7 innings, best order each")
fat = {n: -30 for n in cards.pitcher}
for st in ("Emi Saiki", "Rakyung Kim"):
    conv = [n for n, _ in M.usage_nine(m, "NYH", st)]
    bats = [n for n, _ in M.best_nine(m, "NYH", st)]
    ins, outs = [n for n in bats if n not in conv], [n for n in conv if n not in bats]
    base = best(conv)[1]
    print(f"  starter {st}: conventions {base:.3f}, batting-only {best(bats)[1]:.3f}   "
          f"(conventions play {[o.split()[-1] for o in outs]}, batting-only {[i.split()[-1] for i in ins]})")
    for o in outs:
        for i in ins:
            nine = [i if n == o else n for n in conv]
            print(f"    {i.split()[-1]:10s} for {o.split()[-1]:12s} {best(nine)[1] - base:+.3f}")

print("\n== 2. batting order, conventions nine, rested starter")
def norm(s): return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower())
names = {norm(n): n for n in cards.batter}
g = tables.read("games", "all")[["game_id", "is_postseason"]]
b = tables.read("batting", "all").merge(g, on="game_id")
b = b[b.in_starting_lineup == True]
b = b.assign(card=b.person_name.map(lambda n: names.get(norm(n))),
             team=b.team_name.map(lambda t: next(v for k, v in usage.TEAMS.items() if t.startswith(k))))
for t in ["BOS", "LAQ", "NYH", "SFF"]:
    tb = b[b.team == t]; reg = tb[~tb.is_postseason]
    dates = sorted(reg.game_date.unique()); cut = dates[len(dates) // 2]
    w = pd.concat([reg[reg.game_date >= cut].assign(w=1.0), tb[tb.is_postseason].assign(w=2.0)])
    spot = (w.lineup_spot * w.w).groupby(w.card).sum() / w.w.groupby(w.card).sum()
    st = M.usage_starter(m, t, fat)
    nine = [n for n, _ in M.usage_nine(m, t, st)]
    real = sorted(nine, key=lambda n: spot.get(n, 9.5))
    bybat = sorted(nine, key=lambda n: -m.bat_score(n))
    bo, br = best(nine)
    print(f"  {t} ({st}): best {br:.3f}   real-style {runs(real):.3f}   by bat {runs(bybat):.3f}")
    print(f"     best:       " + ", ".join(n.split()[-1] for n in bo))
    print(f"     real-style: " + ", ".join(f"{n.split()[-1]}({spot.get(n, float('nan')):.1f})" for n in real))
