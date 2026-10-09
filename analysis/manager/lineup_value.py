"""What batting choices and an added player are worth, in exact runs and wins.

Part 1: each team's conventions nine (rule 4') against the best nine by exact
runs under 2+ starts, 1+ start and card eligibility, the DH status of the day
kept. Candidates: every nine from the roster, ranked by summed bat score; the
first TOP legal ones are scored exactly. An incumbent may keep her conventions
position. Mackay stays in LAQ's nine (convention).

Part 2: one position at a time, the incumbent replaced by a blended card --
(a) replacement: the bench, starts-weighted (players outside their team's top
nine by season batting starts), the same at every position; (b) average at the
position: min(positional, league), each a starts-weighted blend over the
season. A position's pool is the players who can play it: CFs also play LF,
but most LFs do not play CF, so LF pools LF and CF starts while CF keeps its
own. Signed runs: negative means the incumbent is better.

A blended card is exact: a batter's blocks are sums over her d100 faces, so a
blend's blocks are the weighted mean of its players' blocks.

Chart: each blend in one slot of an otherwise league-average lineup (`slot`),
runs a game against a league-average starter -- one player, one game.

Wins: Pythagenpat at each team's simulated runs scored and allowed
(team_runs.py), starter days weighted by start share there; series by the
best-of-5 formula at the team's game win %.

    pixi run python analysis/manager/lineup_value.py
"""
import itertools
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import easy_gains as E                                   # noqa: E402
from wpbl import manager as M, play, play_lineup, tables, usage   # noqa: E402

m, u, cards = E.m, E.u, E.cards
TOP = 300
FIELD = list(play.POSITIONS)

# team_runs.py: runs, allowed, game win %, start shares
ENV = {"BOS": (6.757, 8.776, 0.359, {"Kate Blunt": .420, "Paloma Benach": .325, "Alli Schroder": .255}),
       "LAQ": (7.501, 7.784, 0.480, {"Ayami Sato": .426, "Michelle Roche": .332, "Jamie Mackay": .242}),
       "NYH": (8.293, 7.153, 0.583, {"Emi Saiki": .579, "Rakyung Kim": .421}),
       "SFF": (8.440, 7.307, 0.576, {"Kelsie Whitmore": .424, "Jill Albayati": .324, "Niki Eckert": .252})}
MUST = {"LAQ": {"Jamie Mackay"}}


def pyth(r, a):
    x = (r + a) ** 0.287
    return r ** x / (r ** x + a ** x)


def bo5(p):
    return sum(comb(5, k) * p ** k * (1 - p) ** (5 - k) for k in (3, 4, 5))


def wins(team, d_runs):
    r, a, p, _ = ENV[team]
    dg = pyth(r + d_runs, a) - pyth(r, a)
    return dg, bo5(p + dg) - bo5(p)


# --- blended cards --------------------------------------------------------------
def blend(weights):
    tot = sum(weights.values())
    parts = [E.blk(n) for n in weights]
    return tuple(sum(w * b[i] for w, b in zip(weights.values(), parts)) / tot for i in range(4))


def runs_with(names, extra=None):
    """Exact runs, best order; `extra` = {label: blocks} for blended cards."""
    blocks = {n: E.blk(n) for n in names if not extra or n not in extra}
    blocks.update(extra or {})
    score = {n: (m.bat_score(n) if not extra or n not in extra else 0) for n in names}
    return play_lineup.local_best(blocks, sorted(names, key=lambda n: -score[n]), {})[1]


pos_w = defaultdict(dict)                                  # season starts at each position
for (n, p), k in u.starts_at.items():
    if n in m.bat_faces and k > 0 and p in FIELD + ["DH"]:
        pos_w[p][n] = k
league_w = defaultdict(float)
for p in pos_w:
    for n, k in pos_w[p].items():
        league_w[n] += k

names = {usage._norm(n): n for n in cards.batter}
bat = tables.read("batting", "all")
bat = bat[(bat.in_starting_lineup == True) & (bat.lineup_spot <= 9) & (bat.lineup_position.str.upper() != "P")]
bat = bat.assign(card=bat.person_name.map(lambda n: names.get(usage._norm(n))), team=bat.team_name.map(usage._team))
st = bat.groupby(["team", "card"]).game_id.nunique()
bench_w = defaultdict(float)
for t in ENV:
    s = st[t].sort_values(ascending=False)
    for n in s.index[9:]:
        bench_w[n] += s[n]


def sc(b):
    return play_lineup.expected_runs({"x": b}, ["x"] * 9)


LEAGUE = blend(league_w)
own = {p: blend(pos_w[p]) for p in pos_w}               # each position on its own
pools = dict(own)
lfcf = defaultdict(float)
for p in ("LF", "CF"):
    for n, k in pos_w[p].items():
        lfcf[n] += k
pools["LF"] = blend(lfcf)                               # LF's pool includes the CFs; CF keeps its own
AVG = {p: (pools[p] if sc(pools[p]) < sc(LEAGUE) else LEAGUE) for p in FIELD + ["DH"]}
AVG["DH"] = LEAGUE
REPL = blend(bench_w)


def slot(b):
    """Runs a game a team gains with this card in one slot of an otherwise
    league-average lineup, against a ninth league-average starter; best order.
    The post's units (one player, one game), unlike sc's nine copies."""
    blocks = {f"lg{i}": LEAGUE for i in range(8)}
    blocks["x"] = b
    return (play_lineup.local_best(blocks, ["x"] + [f"lg{i}" for i in range(8)], {})[1]
            - play_lineup.expected_runs({"lg": LEAGUE}, ["lg"] * 9))


# --- part 1 ---------------------------------------------------------------------
def best_nine(team, starter, nine, tier):
    home = {n: p for n, p in nine if p != "P"}
    two_way = len(home) < len(nine)
    spots = list(home.values())
    pool = [b for b in cards.team_batters(team) if b != starter]
    must = MUST.get(team, set()) - {starter}
    combos = sorted(itertools.combinations(pool, len(spots)), key=lambda c: -sum(m.bat_score(b) for b in c))
    legal, best = 0, None
    for rank, c in enumerate(combos):
        if not must <= set(c):
            continue
        if E.assign(list(c), spots, {n: p for n, p in home.items() if n in c}, tier) is None:
            continue
        legal += 1
        r = E.runs(list(c) + ([starter] if two_way else []))
        if best is None or r > best[0]:
            best = (r, c, legal)
        if legal >= TOP:
            break
    return best


def main():
    print("blends (bat score, runs of nine of her): league %.3f, replacement (bench) %.3f" % (sc(LEAGUE), sc(REPL)))
    print("  average at position: " + ", ".join(f"{p} {sc(AVG[p]):.3f}" for p in FIELD + ["DH"]))
    print("\n== Average bat at each position, one slot in an otherwise average lineup")
    print("   (runs a game vs a league-average starter; nine copies in brackets)")
    chart = [(p, own[p]) for p in FIELD + ["DH"]] + [("LF pool", pools["LF"]), ("bench", REPL), ("league", LEAGUE)]
    for p, b in sorted(chart, key=lambda x: -slot(x[1])):
        print(f"   {p:6s} {slot(b):+.3f}  ({sc(b):.3f})")
    for t, (r, a, p, _) in ENV.items():
        print(f"  {t}: Pythagenpat {100 * pyth(r, a):.1f}% vs simulated {100 * p:.1f}%")

    print("\n== Part 1: conventions nine vs best nine by exact runs")
    for team, (_, _, _, share) in ENV.items():
        tot = defaultdict(float)
        for starter, w in share.items():
            nine = M.usage_nine(m, team, starter)
            base = E.runs([n for n, _ in nine])
            line = f"  {team} {starter:16s} {w:.3f}  conv {base:.3f}"
            for tier in ("2+", "1+", "card"):
                r, c, rank = best_nine(team, starter, nine, tier)
                tot[tier] += w * (r - base)
                ins = [b.split()[-1] for b in c if b not in dict(nine)]
                outs = [n.split()[-1] for n, pp in nine if n not in c and pp != "P"]
                line += f" | {tier} {r - base:+.3f} (#{rank}) in {','.join(ins) or '-'} out {','.join(outs) or '-'}"
            print(line)
        for tier in ("2+", "1+", "card"):
            dg, ds = wins(team, tot[tier])
            print(f"    {team} weighted {tier}: {tot[tier]:+.3f} runs, games {100 * dg:+.1f} pts, series {100 * ds:+.1f} pts")

    print("\n== Part 2: incumbent replaced (signed; negative = incumbent better)")
    for team, (_, _, _, share) in ENV.items():
        rows = defaultdict(lambda: [0.0, 0.0, defaultdict(float)])
        for starter, w in share.items():
            nine = M.usage_nine(m, team, starter)
            names9 = [n for n, _ in nine]
            base = E.runs(names9)
            for n, pos in nine:
                if pos == "P":
                    continue
                rest = [x for x in names9 if x != n]
                for k, card in ((0, REPL), (1, AVG[pos])):
                    rows[pos][k] += w * (runs_with(rest + ["~"], {"~": card}) - base)
                rows[pos][2][n.split()[-1]] += w
        print(f"  {team}")
        for pos in FIELD + ["DH"]:
            if pos not in rows:
                continue
            rp, av, who = rows[pos]
            inc = ", ".join(f"{n} {100 * s:.0f}%" for n, s in sorted(who.items(), key=lambda x: -x[1]))
            g_rp, s_rp = wins(team, rp)
            g_av, s_av = wins(team, av)
            print(f"    {pos:3s} vs replacement {rp:+.3f} ({100 * s_rp:+.1f} series)   "
                  f"vs average {av:+.3f} ({100 * s_av:+.1f} series)   [{inc}]")


if __name__ == "__main__":
    main()
