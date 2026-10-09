"""Who could fill a team's weakest positions (lineup_post.md, Part 4).

For each pairing, the receiving team's gain: exact runs a game with the player
in place of the regular at that position, the other eight unchanged, best order,
starter days weighted by share (lineup_value.py); and the giving team's cost:
the player taken off its roster and its usual lineup rebuilt (player_loss.py).
Batting only: a player who also pitches brings her arm, not counted here.

    pixi run python analysis/manager/trade_fits.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import player_loss as P                                   # noqa: E402

L, E, M, m = P.L, P.E, P.M, P.m

FITS = [("BOS", "SS", "Samaria Benitez", "LAQ"),
        ("LAQ", "CF", "Ela Day Bedard", "SFF"),
        ("LAQ", "CF", "Jordan Eyster", "SFF"),
        ("NYH", "CF", "Ela Day Bedard", "SFF"),
        ("NYH", "CF", "Jordan Eyster", "SFF")]


def gain(team, pos, player):
    """Runs a game: she replaces the regular at `pos`, by start share."""
    total, who = 0.0, set()
    for starter, w in L.ENV[team][3].items():
        nine = M.usage_nine(m, team, starter)
        names = [n for n, _ in nine]
        regular = next(n for n, p in nine if p == pos)
        who.add(regular.split()[-1])
        total += w * (E.runs([n for n in names if n != regular] + [player]) - E.runs(names))
    return total, "/".join(sorted(who))


def cost(team, player):
    """Runs a game the giving team loses, and who comes in, by start share."""
    share = L.ENV[team][3]
    base = sum(w * E.runs([n for n, _ in M.usage_nine(m, team, s)]) for s, w in share.items())
    after, ins = 0.0, set()
    for s, w in share.items():
        conv, _, _, i, _ = P.day_runs(team, s, player)
        after += w * conv
        ins |= set(i)
    return base - after, ", ".join(sorted(ins)) or "nobody (not in the usual lineup)"


def main():
    for team, pos, player, giver in FITS:
        g, regular = gain(team, pos, player)
        c, ins = cost(giver, player)
        _, gs = L.wins(team, g)
        _, cs = L.wins(giver, -c)
        print(f"{player:16s} {giver} -> {team} {pos} for {regular:10s}: gain {g:+.3f} runs ({100 * gs:+.1f} series)"
              f" | {giver} loses {c:+.3f} ({100 * cs:+.1f} series), in: {ins}")


if __name__ == "__main__":
    main()
