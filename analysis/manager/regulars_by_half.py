"""Most-started player at each position: full season, first half, second half, postseason.

    pixi run python analysis/manager/regulars_by_half.py
"""
import re, unicodedata
import pandas as pd
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
def top(df, p, k=2):
    v = df[df.pos == p].card.value_counts().head(k)
    return ", ".join(f"{n.split()[-1]} {c}" for n, c in v.items()) or "-"
for t in ["BOS", "LAQ", "NYH", "SFF"]:
    ts = st[st.team == t]
    reg = ts[~ts.is_postseason]
    dates = sorted(reg.game_date.unique())
    cut = dates[len(dates) // 2]
    first, second, post = reg[reg.game_date < cut], reg[reg.game_date >= cut], ts[ts.is_postseason]
    n = lambda d: d.game_id.nunique()
    print(f"\n== {t}: regular season {n(reg)} games, split at {cut} ({n(first)} / {n(second)}); postseason {n(post)}")
    print(f"  {'pos':3s} | {'full season':28s} | {'first half':24s} | {'second half':24s} | postseason")
    for p in play.POSITIONS + ("DH",):
        print(f"  {p:3s} | {top(ts, p):28s} | {top(first, p):24s} | {top(second, p):24s} | {top(post, p)}")
