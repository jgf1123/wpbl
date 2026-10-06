"""Where each team could most easily improve: one bench player in for one
regular, from the conventions nine, scored by exact runs over 7 innings against
the league pitcher, best order.

Runs depend only on which nine bat, so positions decide legality alone. For
each (in, out) the script finds the legal assignment that moves the fewest
incumbents ("moves": 0 is a straight swap). An incumbent may always keep the
position the conventions gave her; any other spot needs eligibility under the
tier: 2+ starts there (the conventions), 1+ start, or the card.

Flags (the change touches an arm in the lineup):
  P-out   the two-way starter batting at P sits; the team gains a DH
  P-in    on a DH day, today's starter bats at P instead (the DH spot goes)
  RP-out  a role reliever playing the field comes out
  RP-in   a role reliever comes in to play the field
  SP-out / SP-in  the same for a role starter not pitching today
Disfavored arms (manager.DISFAVORED) never pitch, so they are not flagged.

    pixi run python analysis/manager/easy_gains.py
"""
import csv
import sys
from pathlib import Path

from wpbl import manager as M, play, play_lineup, usage

cards, wp = play.shared()
m = M.Model(cards, wp)
m.usage = u = usage.Usage(cards)
p_line = play_lineup.league_table().p_line
_blocks = {}


def blk(n):
    if n not in _blocks:
        _blocks[n] = play_lineup.batter_blocks(p_line, m.bat_faces[n])
    return _blocks[n]


_runs = {}


def runs(names):
    key = frozenset(names)
    if key not in _runs:
        _runs[key] = play_lineup.local_best({n: blk(n) for n in names},
                                            sorted(names, key=lambda n: -m.bat_score(n)), {})[1]
    return _runs[key]


def ok(name, pos, tier):
    if pos == "DH":
        return True
    if pos not in cards.positions(name):
        return False
    need = {"2+": 2, "1+": 1, "card": 0}[tier]
    return u.starts_at[(name, pos)] >= need


def assign(players, spots, home, tier):
    """Fewest incumbents off their home spot; None if no legal assignment."""
    best = [None]

    def go(i, used, moves, picks):
        if best[0] is not None and moves >= best[0][0]:
            return
        if i == len(spots):
            best[0] = (moves, dict(picks))
            return
        pos = spots[i]
        for p in players:
            if p in used:
                continue
            stays = home.get(p) == pos
            if not stays and not ok(p, pos, tier):
                continue
            picks[pos] = p
            go(i + 1, used | {p}, moves + (p in home and not stays), picks)
            del picks[pos]

    go(0, frozenset(), 0, {})
    return best[0]


# one case per distinct (nine, DH or not); Benach = Blunt, Roche = Sato, Eckert = Albayati
CASES = [("BOS", "Alli Schroder"), ("BOS", "Kate Blunt"),
         ("LAQ", "Jamie Mackay"), ("LAQ", "Ayami Sato"),
         ("NYH", "Emi Saiki"), ("NYH", "Rakyung Kim"),
         ("SFF", "Kelsie Whitmore"), ("SFF", "Jill Albayati")]


def arm_role(team, n, starter):
    if n == starter or n not in cards.pitcher or n in M.DISFAVORED:     # disfavored arms never pitch
        return None
    return "SP" if n in u.starters[team] else "RP"


def main():
    rows = []
    for team, starter in CASES:
        nine = M.usage_nine(m, team, starter)
        home = {n: p for n, p in nine if p != "P"}
        two_way = any(p == "P" for _, p in nine)
        base = runs([n for n, _ in nine])
        bench = [b for b in cards.team_batters(team) if b != starter and b not in dict(nine)]
        print(f"\n== {team}, {starter} starts: conventions {base:.3f}")
        # P-in: on a DH day the starter bats at P; the DH spot goes, so the other
        # eight cover the field
        ins = bench + ([starter] if not two_way and starter in cards.batter else [])
        for tier in ("2+", "1+", "card"):
            for b in ins:
                for out, opos in nine:
                    if b == starter:
                        spots = [p for p in home.values() if p != "DH"]
                        players = [n for n in home if n != out]
                        flags = ["P-in"]
                    elif out == starter:            # P-out: she sits, the team gains a DH
                        spots = list(home.values()) + ["DH"]
                        players = list(home) + [b]
                        flags = ["P-out"]
                    else:
                        spots = [p for p in home.values()]
                        players = [n for n in home if n != out] + [b]
                        flags = []
                    res = assign(players, spots, {n: p for n, p in home.items() if n != out}, tier)
                    if res is None:
                        continue
                    moves, picks = res
                    if b == starter:
                        picks["P"] = starter
                    names = players + ([starter] if (two_way and out != starter) or b == starter else [])
                    r = arm_role(team, out, starter)
                    if r:
                        flags.append(f"{r}-out")
                    r = arm_role(team, b, starter)
                    if r:
                        flags.append(f"{r}-in")
                    where = {n: p for p, n in picks.items()}
                    moved = [f"{n} {home[n]}->{where[n]}" for n in home
                             if n != out and where[n] != home[n]]
                    rows.append(dict(team=team, starter=starter, tier=tier, inn=b, out=out, out_pos=opos,
                                     in_pos=where[b], moves=moves, moved="; ".join(moved),
                                     gain=runs(names) - base, flags=" ".join(flags)))

    out = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if out:
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, rows[0].keys())
            w.writeheader()
            w.writerows(rows)

    # per case: the best change per (in, out) under 2+, then what 1+ and the card add
    for team, starter in CASES:
        case = [r for r in rows if r["team"] == team and r["starter"] == starter]
        seen = set()
        for tier in ("2+", "1+", "card"):
            new = [r for r in case if r["tier"] == tier and (r["inn"], r["out"]) not in seen]
            seen |= {(r["inn"], r["out"]) for r in case if r["tier"] == tier}
            new = sorted([r for r in new if r["gain"] > 0.005], key=lambda r: -r["gain"])
            print(f"\n{team} / {starter.split()[-1]}, tier {tier}"
                  + ("" if tier == "2+" else " (newly legal only)") + f": {len(new)} gains > 0.005")
            for r in new[:12]:
                print(f"  {r['gain']:+.3f}  {r['inn']:>18s} in at {r['in_pos']:<2s} for "
                      f"{r['out']:<19s} ({r['out_pos']:<2s}) moves {r['moves']}"
                      f"{'  [' + r['moved'] + ']' if r['moved'] else ''}  {r['flags']}")


if __name__ == "__main__":
    main()
