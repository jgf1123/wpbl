"""What losing one player costs a team's batting (trade, injury).

For each player in any of her team's conventions nines, she is taken off the
roster and the lineup rebuilt two ways:
  conventions  usage_nine without her (rule 5: the next by window starts,
               positions by window starts, 2+ eligibility)
  best         the best nine by exact runs under 2+ starts (lineup_value.py)
Loss = expected runs a game with her minus without her, starter days weighted
by start share; a lost starter's starts go to the team's other starters in
proportion. Her value = runs a game she adds over a replacement (bench) bat in
her own slot, on the days she bats (P included). Depth = loss - value:
positive means the team's real backup is worse than a bench bat.

The best response is compared with the best nine with her, so the loss does
not include the gain from reshuffling (lineup_value.py, part 1). If no one
left can play a position on a day, anyone may play it (flagged EMERGENCY).

Batting only: losing a two-way player also loses an arm, not counted here.

    pixi run python analysis/manager/player_loss.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import lineup_value as L                                 # noqa: E402
from wpbl import manager as M                             # noqa: E402

E, m, cards = L.E, L.m, L.cards
L.TOP = 50
_team_batters = cards.team_batters
_usage_nine = M.usage_nine.__wrapped__                    # uncached: the roster changes


def without(lost):
    cards.team_batters = (lambda t: [b for b in _team_batters(t) if b != lost]) if lost else _team_batters


_positions = cards.positions


def day_runs(team, starter, lost):
    """(conventions runs, best runs, best's rank, players in, emergency position) on a
    starter's day without `lost`."""
    without(lost)
    must = L.MUST
    L.MUST = {t: s - {lost} for t, s in must.items()}
    emergency = ''
    try:
        try:
            nine = _usage_nine(m, team, starter, True)
        except ValueError:                           # no legal nine: a position no one left can play
            for pos in L.FIELD:                      # let anyone play one position, the first that works
                cards.positions = (lambda q: lambda n: list(_positions(n)) + [q])(pos)
                try:
                    nine = _usage_nine(m, team, starter, True)
                    emergency = pos
                    break
                except ValueError:
                    continue
            else:
                raise
        conv = E.runs([n for n, _ in nine])
        best, _, rank = L.best_nine(team, starter, nine, "2+")
    finally:
        without(None)
        cards.positions = _positions
        L.MUST = must
    old = dict(M.usage_nine(m, team, starter))
    ins = [f"{n.split()[-1]} {p}" for n, p in nine if n not in old]
    return conv, max(best, conv), rank, ins, emergency


_best_with = {}


def best_with(team, starter):
    if (team, starter) not in _best_with:
        nine = M.usage_nine(m, team, starter)
        _best_with[(team, starter)] = max(L.best_nine(team, starter, nine, "2+")[0], E.runs([n for n, _ in nine]))
    return _best_with[(team, starter)]


def value(team, share, player):
    """Runs a game she adds over a bench bat in her slot, by start share."""
    v = 0.0
    for starter, w in share.items():
        names = [n for n, _ in M.usage_nine(m, team, starter)]
        if player in names:
            rest = [n for n in names if n != player]
            v += w * (E.runs(names) - L.runs_with(rest + ["~"], {"~": L.REPL}))
    return v


def main():
    for team, (_, _, _, share) in L.ENV.items():
        base = sum(w * E.runs([n for n, _ in M.usage_nine(m, team, s)]) for s, w in share.items())
        base_best = sum(w * best_with(team, s) for s, w in share.items())
        players = []
        for s in share:
            for n, _ in M.usage_nine(m, team, s):
                if n not in players:
                    players.append(n)
        print(f"\n== {team}: conventions {base:.3f}, best {base_best:.3f} runs a game (weighted)", flush=True)
        rows = []
        for p in players:
            sh = {s: w for s, w in share.items() if s != p}
            tot = sum(sh.values())
            sh = {s: w / tot for s, w in sh.items()}
            conv = best = 0.0
            worst_rank = 0
            ins, emerg = set(), ''
            for s, w in sh.items():
                c, b, rank, i, e = day_runs(team, s, p)
                conv += w * c
                best += w * b
                worst_rank = max(worst_rank, rank)
                ins |= set(i)
                emerg = emerg or e
            loss_c, loss_b = base - conv, base_best - best
            val = value(team, share, p)
            dg, ds = L.wins(team, -loss_c)
            days = sum(w for s, w in share.items() if p in dict(M.usage_nine(m, team, s)))
            arm = " (arm not counted)" if p in cards.pitcher and p not in M.DISFAVORED else ""
            rows.append((loss_c, p, f"  {p:20s} bats {100 * days:3.0f}% of days  loss conv {loss_c:+.3f} "
                         f"({100 * dg:+.1f} games, {100 * ds:+.1f} series), best {loss_b:+.3f}  "
                         f"value {val:+.3f}  depth {loss_c - val:+.3f}  (best rank #{worst_rank}){arm}"
                         f"{' EMERGENCY ' + emerg if emerg else ''}\n      in: {', '.join(sorted(ins))}"))
        for _, _, line in sorted(rows, reverse=True):
            print(line, flush=True)


if __name__ == "__main__":
    main()
