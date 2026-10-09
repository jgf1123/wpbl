"""Does a later start to the late-season window change any usual lineup?

usage.Usage's window is the second half of each team's regular season (19-21
Aug) plus the postseason (weight 2). This rebuilds the weighted starts with
the regular-season part starting on a fixed date instead -- 22 Aug (after
Ibarra's move and Saiki's first game) and 27 Aug (Narasaki's first NYH game) --
and compares each team's usual lineup on two starter days.

Result (2026-10-08): 22 Aug changes nothing; 27 Aug only swaps BOS's Bryant
and Haas between 3B and DH (same nine, same runs). The window was kept (user).

    pixi run python analysis/manager/window_start.py
"""
import datetime as dt
from collections import defaultdict

from wpbl import manager as M, play, play_lineup, tables, usage

STARTERS = {"BOS": ["Kate Blunt", "Alli Schroder"], "LAQ": ["Ayami Sato", "Jamie Mackay"],
            "NYH": ["Emi Saiki", "Rakyung Kim"], "SFF": ["Jill Albayati", "Kelsie Whitmore"]}


def reweight(u, bat, st, start):
    """usage.Usage's window loop, the regular-season part from `start` (None = its midpoint)."""
    u.weight, u.weight_at = defaultdict(float), defaultdict(float)
    for team in usage.TEAMS.values():
        ts = st[st.team == team]
        reg = ts[~ts.is_postseason]
        dates = sorted(reg.game_date.unique())
        cut = start or dates[len(dates) // 2]
        window = [(reg[reg.game_date >= cut], 1.0), (ts[ts.is_postseason], usage.POST_WEIGHT)]
        total = sum(w * part.game_id.nunique() for part, w in window)
        for part, w in window:
            for r in part[part.pos != "P"].itertuples():
                u.weight[(team, r.card)] += w
                u.weight_at[(team, r.card, r.pos)] += w
        for name in usage.CONFLICT:
            mine = bat[(bat.card == name) & (bat.team == team)]
            if mine.empty:
                continue
            last = mine.game_date.max()
            played = bat[(bat.team == team) & (bat.game_date <= last)].game_id.nunique()
            before = st[(st.card == name) & (st.team == team) & (st.pos != "P") & (st.game_date <= last)]
            rate = before.game_id.nunique() / played
            u.weight[(team, name)] = rate * total
            for pos, n in before.pos.value_counts().items():
                u.weight_at[(team, name, pos)] = rate * total * n / len(before)


def main():
    cards, wp = play.shared()
    m = M.Model(cards, wp)
    m.usage = usage.Usage(cards)
    p_line = play_lineup.league_table().p_line

    def runs(names):
        blocks = {n: play_lineup.batter_blocks(p_line, m.bat_faces[n]) for n in names}
        return play_lineup.local_best(blocks, sorted(names, key=lambda n: -m.bat_score(n)), {})[1]

    names = {usage._norm(n): n for n in list(cards.batter) + list(cards.pitcher)}
    games = tables.read("games", "all")[["game_id", "is_postseason"]]
    bat = tables.read("batting", "all").merge(games, on="game_id")
    bat = bat.assign(card=bat.person_name.map(lambda n: names.get(usage._norm(n))),
                     team=bat.team_name.map(usage._team))
    st = bat[bat.in_starting_lineup == True]
    st = st.assign(pos=st.lineup_position.str.upper())

    reweight(m.usage, bat, st, None)                      # reproduces usage.Usage
    usual = {(t, s): M.usage_nine.__wrapped__(m, t, s, True) for t, ss in STARTERS.items() for s in ss}
    for start in (dt.date(2026, 8, 22), dt.date(2026, 8, 27)):
        reweight(m.usage, bat, st, start)
        print(f"== window from {start}")
        for (t, s), old in usual.items():
            new = M.usage_nine.__wrapped__(m, t, s, True)
            o, n = dict(old), dict(new)
            diff = ([f"{x.split()[-1]} {p} in" for x, p in new if x not in o]
                    + [f"{x.split()[-1]} out" for x in o if x not in n]
                    + [f"{x.split()[-1]} {o[x]}->{n[x]}" for x in o if x in n and o[x] != n[x]])
            print(f"  {t} {s.split()[-1]:9s} {runs([x for x, _ in old]):.3f} -> {runs([x for x, _ in new]):.3f}  "
                  f"{'; '.join(diff) or 'same'}")


if __name__ == "__main__":
    main()
