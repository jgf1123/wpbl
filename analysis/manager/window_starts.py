"""Late-season plus postseason starts by position and by player: the window behind the conventions' nine.

    pixi run python analysis/manager/window_starts.py
"""
import re, unicodedata
from wpbl import play, tables
cards, wp = play.shared()
def norm(s): return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower())
card_of = {norm(n): n for n in cards.batter}
TEAM = {"Boston": "BOS", "Los Angeles": "LAQ", "New York": "NYH", "San Francisco": "SFF"}
bat = tables.read("batting", "all"); g = tables.read("games", "all")
st = bat[bat.in_starting_lineup == True].merge(g[["game_id", "is_postseason"]], on="game_id")
st["card"] = st.person_name.map(lambda n: card_of.get(norm(n)))
st["team"] = st.team_name.map(lambda tn: next(v for k, v in TEAM.items() if tn.startswith(k)))
st["pos"] = st.lineup_position.str.upper()
for t in ["BOS", "LAQ", "NYH", "SFF"]:
    ts = st[st.team == t]; reg = ts[~ts.is_postseason]
    dates = sorted(reg.game_date.unique()); cut = dates[len(dates) // 2]
    late, post = reg[reg.game_date >= cut], ts[ts.is_postseason]
    import pandas as pd; pool = pd.concat([late, post])
    print(f"== {t}: late {late.game_id.nunique()} + postseason {post.game_id.nunique()} games")
    for p in play.POSITIONS + ("DH",):
        v = pool[pool.pos == p].card.value_counts()
        lv = late[late.pos == p].card.value_counts(); pv = post[post.pos == p].card.value_counts()
        lead = v.index[0].split()[-1]
        split = len(v) > 1 and v.iloc[0] < 1.5 * v.iloc[1]
        disagree = len(lv) and len(pv) and lv.index[0] != pv.index[0] and pv.iloc[0] > (pv.iloc[1] if len(pv) > 1 else 0)
        verdict = f"split: bats decide among {', '.join(n.split()[-1] for n in v.index[:2])}" if split else f"regular {lead}"
        print(f"  {p:3s} pooled " + ", ".join(f"{n.split()[-1]} {c}" for n, c in v.head(3).items()).ljust(34)
              + f" -> {verdict}" + ("   [late and postseason leaders differ]" if disagree else ""))

print("\n--- the nine by total starts in the window (late + postseason) ---")
import itertools
for t in ["BOS", "LAQ", "NYH", "SFF"]:
    ts = st[st.team == t]; reg = ts[~ts.is_postseason]
    dates = sorted(reg.game_date.unique()); cut = dates[len(dates) // 2]
    pool = pd.concat([reg[reg.game_date >= cut], ts[ts.is_postseason]])
    n = pool.game_id.nunique()
    tot = pool[pool.pos != "P"].card.value_counts()
    print(f"== {t} ({n} games): " + ", ".join(f"{k.split()[-1]} {v}" for k, v in tot.head(12).items()))
