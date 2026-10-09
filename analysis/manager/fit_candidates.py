"""Candidates to fill a team's weak position from the other three teams
(lineup_post.md, Part 4): everyone except each team's own top player at the
position, ranked by innings there over the whole season (regular season and
postseason), with starts, current role and bat (runs a game in one slot of an
otherwise average lineup, against the bench bat; lineup_value.slot).

A CF hole is ranked by CF innings alone: CFs also play LF, but most LFs never
played CF, so an LF can fill CF only if the receiving team's LF can move over.
LF innings are printed for reference.

    pixi run python analysis/manager/fit_candidates.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lineup_value as L                                 # noqa: E402
from wpbl import manager as M, positions, tables, usage   # noqa: E402

HOLES = [("BOS", "ss", "SS"), ("LAQ", "cf", "CF"), ("NYH", "cf", "CF")]


def main():
    m, u, cards = L.m, L.u, L.cards
    bench_bat = L.slot(L.REPL)
    lineup = {t: {n for s in share for n, _ in M.usage_nine(m, t, s)} for t, (_, _, _, share) in L.ENV.items()}
    outs = positions.field_outs("all")
    bat = tables.read("batting", "all")
    card = {usage._norm(n): n for n in cards.batter}
    inn = {}
    for r in bat.drop_duplicates("person_id").itertuples():
        n = card.get(usage._norm(r.person_name))
        if n and r.person_id in outs:
            inn[n] = outs[r.person_id]
    ip = lambda o: f"{o // 3}.{o % 3}"

    def role(t, n):
        return "SP" if n in u.starters[t] else ("regular" if n in lineup[t] else "bench")

    for t, key, pos in HOLES:
        rows = []
        for other in L.ENV:
            if other == t:
                continue
            top = max(cards.team_batters(other), key=lambda b: u.starts_at[(b, pos)])
            for b in cards.team_batters(other):
                o = inn.get(b, {}).get(key, 0)
                if b != top and o > 0:
                    rows.append((o, b, other))
        rows.sort(reverse=True)
        print(f"\n{t} {pos}: each team's top {pos} excluded")
        for o, b, other in rows[:8]:
            lf = f"  LF {ip(inn[b].get('lf', 0))}" if key == "cf" else ""
            print(f"   {b:20s} {other} {role(other, b):8s} {pos} {ip(o):>6s}{lf}  starts {u.starts_at[(b, pos)]:2d}"
                  f"  bat vs bench {L.slot(L.E.blk(b)) - bench_bat:+.2f}")


if __name__ == "__main__":
    main()
