"""The usual lineup (nine first: most weighted late-season starts, then
positions) against a position-first lineup: at each position the player with
the most weighted late-season starts there, conflicts settled by the most total
starts at the assigned positions, DH a position like any other. Exact runs,
best order, on two starter days per team.

Result (2026-10-08): position-first bats 0.02-0.20 runs a game better
(weighted), mostly by giving DH to a player the team used there (De Leija,
Gutierrez) instead of a leftover fielder; it drops players who moved around
(Eynon, Perez on Kim days). The usual lineup was kept (user).

    pixi run python analysis/manager/position_first.py
"""
from wpbl import manager as M, play, play_lineup, usage

STARTERS = {"BOS": ["Kate Blunt", "Alli Schroder"], "LAQ": ["Ayami Sato", "Jamie Mackay"],
            "NYH": ["Emi Saiki", "Rakyung Kim"], "SFF": ["Jill Albayati", "Kelsie Whitmore"]}


def main():
    cards, wp = play.shared()
    m = M.Model(cards, wp)
    u = m.usage = usage.Usage(cards)
    p_line = play_lineup.league_table().p_line

    def runs(names):
        blocks = {n: play_lineup.batter_blocks(p_line, m.bat_faces[n]) for n in names}
        return play_lineup.local_best(blocks, sorted(names, key=lambda n: -m.bat_score(n)), {})[1]

    for t, starters in STARTERS.items():
        for s in starters:
            usual = M.usage_nine(m, t, s)
            two_way = any(p == "P" for _, p in usual)
            spots = list(play.POSITIONS) + ([] if two_way else ["DH"])
            pool = [b for b in cards.team_batters(t) if b != s]
            best = {frozenset(): (0.0, ())}
            for pos in spots:
                nxt = {}
                for used, (tot, picks) in best.items():
                    for b in pool:
                        if b in used:
                            continue
                        v = tot + u.weight_at[(t, b, pos)] + 1e-3 * u.weight[(t, b)]
                        if used | {b} not in nxt or v > nxt[used | {b}][0]:
                            nxt[used | {b}] = (v, picks + ((b, pos),))
                best = nxt
            first = list(max(best.values(), key=lambda x: x[0])[1]) + ([(s, "P")] if two_way else [])
            diff = [f"{p}: {next((x for x, q in usual if q == p), '-').split()[-1]} -> {n.split()[-1]}"
                    for n, p in first if next((x for x, q in usual if q == p), None) != n]
            print(f"{t} {s.split()[-1]:9s} usual {runs([n for n, _ in usual]):.3f}  "
                  f"position-first {runs([n for n, _ in first]):.3f}  {'; '.join(diff) or 'same'}")


if __name__ == "__main__":
    main()
