"""Card eligibility by starts at the position; batting-only vs 2+3 vs regulars nines in exact runs; late-season roles.

    pixi run python analysis/manager/conventions_measured.py
"""
import re, unicodedata, collections
import pandas as pd
from wpbl import manager as M, play, play_lineup, tables
cards, wp = play.shared(); m = M.Model(cards, wp)
def norm(s): return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode().lower())
card_of = {norm(n): n for n in cards.batter}
TEAM = {"Boston": "BOS", "Los Angeles": "LAQ", "New York": "NYH", "San Francisco": "SFF"}
def code(tn): return next(v for k, v in TEAM.items() if tn.startswith(k))
bat = tables.read("batting", "all")
st = bat[bat.in_starting_lineup == True].copy()
st["card"] = st.person_name.map(lambda n: card_of.get(norm(n)))
st["team"] = st.team_name.map(code); st["pos"] = st.lineup_position.str.upper()
miss = st[st.card.isna()].person_name.unique()
print("unmatched names:", list(miss))
starts = st.groupby(["card", "pos"]).size()           # any team: traded players keep positions
# 1. how eligibilities are spread
elig = [(n, p) for n in cards.batter for p in cards.positions(n) if p != "P"]
cnt = [int(starts.get((n, p), 0)) for n, p in elig]
bins = collections.Counter("0" if c == 0 else "1" if c == 1 else "2" if c == 2 else "3-4" if c < 5 else "5-9" if c < 10 else "10+" for c in cnt)
print("card eligibilities by starts there:", dict(sorted(bins.items())))
print("removed by a 3-start threshold (1-2 starts):")
for t in ["BOS","LAQ","NYH","SFF"]:
    print(f"  {t}: " + ", ".join(f"{n.split()[-1]} {p}({int(starts.get((n,p),0))})" for n, p in elig
                               if cards.batter[n]["team"] == t and starts.get((n,p),0) < 3))
# 2. lineups
p_line = play_lineup.league_table().p_line
def runs(nine):
    names = [n for n, _ in nine]
    blocks = {n: play_lineup.batter_blocks(p_line, m.bat_faces[n]) for n in names}
    return play_lineup.local_best(blocks, sorted(names, key=lambda n: -m.bat_score(n)), {})[1]
def assign(team, starter, ok):
    bats = [b for b in cards.team_batters(team) if b != starter]
    best = {frozenset(): (0.0, ())}
    for pos in play.POSITIONS + ("DH",):
        nxt = {}
        for used, (tot, picks) in best.items():
            for b in bats:
                if b in used or not ok(b, pos): continue
                key, cand = used | {b}, (tot + m.bat_score(b), picks + ((b, pos),))
                if key not in nxt or cand[0] > nxt[key][0]: nxt[key] = cand
        best = nxt
    return max(best.values(), key=lambda x: x[0])[1] if best else None
fat = {n: -30 for n in cards.pitcher}
for t in ["BOS","LAQ","NYH","SFF"]:
    s = M.pick_starter(m, t, fat)
    ts = st[st.team == t]
    most = {p: ts[ts.pos == p].card.value_counts() for p in play.POSITIONS + ("DH",)}
    lock = {p: next((n for n in most[p].index if n != s and n in cards.batter and cards.batter[n]["team"] == t), None)
            for p in ("C", "SS", "CF")}
    bats_only = lambda b, p: p == "DH" or p in cards.positions(b)
    two_three = lambda b, p: (b == lock[p]) if p in lock and lock[p] else (p == "DH" or (p in cards.positions(b) and starts.get((b, p), 0) >= 3))
    # regulars: most-started at each position, greedy in order of how settled the position is
    reg, used = [], set()
    for p in sorted(play.POSITIONS + ("DH",), key=lambda p: -most[p].iloc[0] if len(most[p]) else 0):
        n = next((n for n in most[p].index if n not in used and n != s and n in cards.batter and cards.batter[n]["team"] == t), None)
        reg.append((n, p)); used.add(n)
    nines = ts.groupby("game_id").card.apply(lambda x: frozenset(x))
    modal = nines.value_counts()
    print(f"\n== {t} (starter {s}; {len(nines)} games; most common exact nine started {modal.iloc[0]} times, "
          f"{len(modal)} different nines)")
    for label, nine in (("bats only", assign(t, s, bats_only)), ("2+3", assign(t, s, two_three)), ("regulars", reg)):
        if not nine or any(n is None for n, _ in nine):
            print(f"  {label:10s} no legal nine"); continue
        print(f"  {label:10s} {runs(nine):5.2f} runs  " + ", ".join(f"{n.split()[-1]} {p}" for n, p in nine))
# 3. roles from the last 10 team-games
pit = tables.read("pitching", "all"); pit["team"] = pit.team_name.map(code)
print("\nlate-season roles (last 10 team-games, postseason included): starts / relief outings")
for t in ["BOS","LAQ","NYH","SFF"]:
    tp = pit[pit.team == t]
    last = sorted(tp.game_id.unique(), key=lambda g: tp[tp.game_id == g].game_date.iloc[0])[-10:]
    r = tp[tp.game_id.isin(last)].groupby("person_name").agg(GS=("is_starter", "sum"), app=("game_id", "nunique"))
    r["RP"] = r.app - r.GS
    print(f"  {t}: " + "; ".join(f"{n} {int(a.GS)}/{int(a.RP)}" for n, a in r.sort_values(["GS","RP"], ascending=False).iterrows()))
