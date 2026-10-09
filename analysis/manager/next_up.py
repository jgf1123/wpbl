"""Who comes in when a team loses one regular, and how far down the roster.

Each team's players ranked by weighted late-season starts (not at P), the
order the usual lineup uses (manager.usage_nine). For every regular on every
starter's day: take her off the roster, rebuild the usual lineup, and print
whoever comes in if she is not the first player outside the nine, or if no
one left can play the position (an emergency fielder, as in player_loss.py).
Lists the positions where a team must reach past its next player
(lineup_post.md, Part 3, Table 4).

    pixi run python analysis/manager/next_up.py
"""
from wpbl import manager as M, play, usage

STARTERS = {"BOS": ["Kate Blunt", "Paloma Benach", "Alli Schroder"],
            "LAQ": ["Ayami Sato", "Michelle Roche", "Jamie Mackay"],
            "NYH": ["Emi Saiki", "Rakyung Kim"],
            "SFF": ["Jill Albayati", "Niki Eckert", "Kelsie Whitmore"]}


def main():
    cards, wp = play.shared()
    m = M.Model(cards, wp)
    u = m.usage = usage.Usage(cards)
    raw = M.usage_nine.__wrapped__                       # uncached: the roster changes
    short = lambda n: n.split()[-1]
    team_batters, positions = cards.team_batters, cards.positions
    for t, days in STARTERS.items():
        print(f"== {t}")
        for s in days:
            pool = [b for b in team_batters(t) if b != s]
            ranked = sorted(pool, key=lambda b: (-u.weight[(t, b)], -m.bat_score(b)))
            rank = {b: i + 1 for i, b in enumerate(ranked)}
            nine = raw(m, t, s, True)
            first_out = next(b for b in ranked if b not in dict(nine))
            print(f"  {short(s)} days: first player outside the nine {short(first_out)} (#{rank[first_out]})")
            for lost, pos in nine:
                if lost == s:
                    continue
                cards.team_batters = lambda tt, lost=lost: [b for b in team_batters(tt) if b != lost]
                emergency = ""
                try:
                    new = raw(m, t, s, True)
                except ValueError:                        # no legal nine: anyone may play one position
                    for q in play.POSITIONS:
                        cards.positions = lambda n, q=q: list(positions(n)) + [q]
                        try:
                            new = raw(m, t, s, True)
                            emergency = f" EMERGENCY {q}"
                            break
                        except ValueError:
                            continue
                finally:
                    cards.team_batters, cards.positions = team_batters, positions
                ins = [(n, p) for n, p in new if n not in dict(nine)]
                if emergency or any(n != first_out for n, _ in ins):
                    print(f"    lose {short(lost)} ({pos}): in "
                          + ", ".join(f"{short(n)} #{rank[n]} at {p}" for n, p in ins) + emergency)


if __name__ == "__main__":
    main()
