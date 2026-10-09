"""Expected runs for a batting order, exactly, with the running game in it.

    pixi run python -m wpbl.lineup_model        # sanity checks

The chain steps play by play, like `advance.py`, but keeps track of WHO is on
each base, because a steal depends on the runner. A state is (batter's lineup
slot, outs, runners) with each runner stored as a LAG: how many batters ahead of
the current one she batted (1 = the woman who batted just before). Advancement
stays league-average and player-independent, so the lag graph is built once from
`advance.py`'s card-line operators and reused for every lineup; a lineup only
supplies the batter's card at the plate and the steal ratings of each runner.

  * PA lines, and non-steal running plays (wild pitch, passed ball, balk), come
    from `advance.py`'s operators rebuilt WITHOUT steals. Steals are taken out of
    the running-play operator and modelled explicitly, so they are not counted
    twice.
  * Before every play a runner with an open base ahead of her attempts with a
    probability from `Steals`; a safe steal moves her up one base, a caught one
    puts her out (and if that is the third out the same batter leads off the
    next inning).
  * Who a runner IS, when the feed operator only knows base states: runners keep
    their order; on a plate appearance the players that leave the bases (score or
    are put out) are the lead-most ones, and the batter is out on a K or an OUT
    line and safe otherwise. This is exact except on a fielder's choice, where the
    trailing runner is out, not the leading one; it only changes who is credited
    with being on base for a later steal.

The value of a lineup is runs over seven innings, each inning starting with the
batter after the last one to bat. Each half-inning is solved exactly (dense
solves by out count); nothing is simulated.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from wpbl import advance, markov
from wpbl.advance import LINES, OVER, SLOT, STATES, observed_transitions
from wpbl.dice import B_CELLS, BAND_CELLS, CARD_LINES, PA_CELLS, P_CELLS, TREE_LINES

INNINGS = 7
MAX_LAG = 5                     # a runner stranded longer is treated as the fifth batter back
PRUNE = 0.004                   # operator edges rarer than this are dropped (row renormalised)
CFG0 = (-1, -1, -1)             # lags of the runners on 1st, 2nd, 3rd; -1 = empty
ELIGIBLE = [("1__", 0), ("1_3", 0), ("_2_", 1), ("12_", 1)]   # (bases, base stolen: 0=2nd, 1=3rd)
KINDS = [(bases, outs) for bases, _ in ELIGIBLE for outs in range(3)]
KIND = {k: i for i, k in enumerate(KINDS)}
CARD_TO_OP = {"K": "K", "BB": "FP", "HBP": "FP", "HR": "HR", "1B": "1B",
              "2B": "2B", "ROE": "ROE", "OUT": "OUT"}


# ----------------------------------------------------------------------------
# operators without steals
# ----------------------------------------------------------------------------

@lru_cache(maxsize=1)
def operators() -> dict:
    """`advance.operators()` with steals removed from the running-play operator.

    Also folds the one triple of the season into the double line (the advance
    table has no rate for a triple from most base-out states), and drops idle
    non-plate-appearance rows (substitutions), which change nothing.
    """
    frame = advance.moves()
    frame = frame[~frame["event"].isin(("stolen_base", "caught_stealing"))]
    idle = ((frame["label"] == "RUN") & (frame["bases"] == frame["t_bases"])
            & (frame["outs"] == frame["t_outs"]) & (frame["runs"] == 0))
    ghost = (frame["label"] == "RUN") & (frame["bases"] == "___")     # the extra-innings runner
    frame = frame[~idle & ~ghost]
    counts, _ = advance.advance_rates(advance.moves())
    rates = advance.rate_table(counts)
    built = {}
    for label in LINES:
        rows = []
        if label in ("1B", "ROE", "2B"):
            events = {"1B": {"single": 1.0}, "ROE": {"reached_on_error": 1.0},
                      "2B": {"double": 1.0}}[label]
            thick = observed_transitions(frame, label, borrow=False)
            for bases, outs in STATES:
                if (bases, outs) in thick:
                    rows.append(thick[(bases, outs)])
                    continue
                mixed = {}
                for event, share in events.items():
                    for key, p in advance.hit_transitions(rates, event, bases, outs).items():
                        mixed[key] = mixed.get(key, 0.0) + share * p
                rows.append(mixed)
        else:
            seen = observed_transitions(frame, label)
            for bases, outs in STATES:
                rows.append(seen.get((bases, outs)) or advance.structural(label, bases, outs))
        built[label] = rows
    running = observed_transitions(frame, "RUN")
    built["RUN"] = [running.get(state) or {(SLOT[state], 0): 1.0} for state in STATES]
    plays_from = frame.groupby(["bases", "outs"]).size()
    run_plays = frame[frame["label"] == "RUN"].groupby(["bases", "outs"]).size()
    share = (run_plays / plays_from).fillna(0.0)
    built["run_share"] = np.array([float(share.get(state, 0.0)) for state in STATES])
    return built


# ----------------------------------------------------------------------------
# the lag graph
# ----------------------------------------------------------------------------

def bases_of(cfg) -> str:
    return "".join(str(i + 1) if lag >= 0 else "_" for i, lag in enumerate(cfg))


def survivors(cfg, after_bases: str, batter_safe: bool, shift: int):
    """New runner lags after a play. Players in order lead -> trail; the lead-most
    leave first. Returns (new cfg, anomaly flag)."""
    order = [cfg[i] for i in (2, 1, 0) if cfg[i] >= 0]          # lead runner first
    if batter_safe:
        order = order + [0]
    want = [i for i in (2, 1, 0) if after_bases[i] != "_"]
    flag = False
    if len(want) > len(order) and not batter_safe:                # dropped third strike, a mislabelled
        order = order + [0]                                       # out: the batter reached after all
    if len(want) > len(order):                                    # still short: not a play we can follow
        flag = True
        order = order + [0] * (len(want) - len(order))
    keep = order[len(order) - len(want):] if want else []
    new = [-1, -1, -1]
    for base, lag in zip(want, keep):
        new[base] = min(lag + shift, MAX_LAG)
    return tuple(new), flag


@dataclass
class Graph:
    states: list                    # (outs, cfg)
    index: dict
    outs: np.ndarray                # outs of each relative state
    pa_src: np.ndarray              # merged plate-appearance edges
    pa_dst: np.ndarray              # -1 = inning over
    pa_p: np.ndarray                # (edges, 8): probability per CARD line
    pa_runs: np.ndarray             # (R, 8) expected runs per (state, CARD line)
    run_src: np.ndarray
    run_dst: np.ndarray
    run_p: np.ndarray
    run_runs: np.ndarray            # (R,) expected runs from a running play
    run_share: np.ndarray           # (R,)
    st_lag: np.ndarray              # (R,) lag of the runner who could steal, -1 if none
    st_kind: np.ndarray             # (R,) index into KINDS
    st_safe: np.ndarray             # (R,) destination if safe
    st_caught: np.ndarray           # (R,) destination if caught (-1 = inning over)
    anomalies: tuple
    pa_detail: dict = None          # src -> [(card-op line, dst, runs, p)], for exact run distributions
    run_detail: dict = None         # src -> [(dst, runs, p)]


@lru_cache(maxsize=1)
def graph() -> Graph:
    ops = operators()
    states, index = [], {}

    def ensure(state):
        if state not in index:
            index[state] = len(states)
            states.append(state)
        return index[state]

    ensure((0, CFG0))
    anomalies = [0, 0.0]        # edges dropped, probability they carried

    def kept(row, cfg, batter_safe, shift):
        """An operator row as (next slot, runs, p, new runner lags), leaving out edges
        that need a runner who is not there and edges rarer than PRUNE, and
        renormalising what is left."""
        out = []
        for (nxt, runs), p in row.items():
            new = None
            if nxt != OVER:
                new, bad = survivors(cfg, STATES[nxt][0], batter_safe, shift)
                if bad or p < PRUNE:
                    anomalies[0] += 1
                    anomalies[1] += p
                    continue
            elif p < PRUNE:
                anomalies[0] += 1
                anomalies[1] += p
                continue
            out.append((nxt, runs, p, new))
        total = sum(p for _, _, p, _ in out)
        return [(n, r, p / total, c) for n, r, p, c in out] if total else []

    pa_edges, run_edges, steal_rows = {}, {}, {}
    pa_detail, run_detail = {}, {}
    i = 0
    while i < len(states):
        outs, cfg = states[i]
        bases = bases_of(cfg)
        slot = SLOT[(bases, outs)]
        for line in LINES:
            for nxt, runs, p, new in kept(ops[line][slot], cfg, line not in ("K", "OUT"), 1):
                dst = -1 if nxt == OVER else ensure((STATES[nxt][1], new))
                pa_detail.setdefault(i, []).append((line, dst, runs, p))
                cell = pa_edges.setdefault((i, dst, line), [0.0, 0.0])
                cell[0] += p
                cell[1] += p * runs
        for nxt, runs, p, new in kept(ops["RUN"][slot], cfg, False, 0):
            dst = -1 if nxt == OVER else ensure((STATES[nxt][1], new))
            run_detail.setdefault(i, []).append((dst, runs, p))
            cell = run_edges.setdefault((i, dst), [0.0, 0.0])
            cell[0] += p
            cell[1] += p * runs
        lag = -1
        if cfg[1] >= 0 and cfg[2] < 0:                            # runner on 2nd, 3rd open
            lag, moved, gone = cfg[1], (cfg[0], -1, cfg[1]), (cfg[0], -1, cfg[2])
        elif cfg[0] >= 0 and cfg[1] < 0:                          # runner on 1st, 2nd open
            lag, moved, gone = cfg[0], (-1, cfg[0], cfg[2]), (-1, cfg[1], cfg[2])
        if lag >= 0:
            safe_dst = ensure((outs, moved))
            caught_dst = -1 if outs + 1 >= 3 else ensure((outs + 1, gone))
            steal_rows[i] = (lag, KIND[(bases, outs)], safe_dst, caught_dst)
        i += 1

    R = len(states)
    pa_runs = np.zeros((R, len(CARD_LINES)))
    line_cols = {}
    for j, card_line in enumerate(CARD_LINES):
        line_cols.setdefault(CARD_TO_OP[card_line], []).append(j)
    merged = {}
    for (src, dst, line), (p, pr) in pa_edges.items():
        row = merged.setdefault((src, dst), np.zeros(len(CARD_LINES)))
        for j in line_cols[line]:       # BB and HBP both take the FP operator's transitions
            row[j] += p
            pa_runs[src, j] += pr
    keys = sorted(merged)
    rkeys = sorted(run_edges)
    run_runs = np.zeros(R)
    for (src, _), (_, pr) in run_edges.items():
        run_runs[src] += pr
    st = {name: np.full(R, -1) for name in ("lag", "kind", "safe", "caught")}
    for r, (lag, kind, sd, cd) in steal_rows.items():
        st["lag"][r], st["kind"][r], st["safe"][r], st["caught"][r] = lag, kind, sd, cd
    return Graph(
        states, index, np.array([s[0] for s in states]),
        np.array([k[0] for k in keys]), np.array([k[1] for k in keys]),
        np.array([merged[k] for k in keys]), pa_runs,
        np.array([k[0] for k in rkeys]), np.array([k[1] for k in rkeys]),
        np.array([run_edges[k][0] for k in rkeys]), run_runs,
        np.array([ops["run_share"][SLOT[(bases_of(cfg), outs)]] for outs, cfg in states]),
        st["lag"], np.maximum(st["kind"], 0), st["safe"], st["caught"], tuple(anomalies), pa_detail, run_detail)


# ----------------------------------------------------------------------------
# batters and steals
# ----------------------------------------------------------------------------

def facing_average_pitcher(card: np.ndarray, league: np.ndarray) -> np.ndarray:
    """A batter card as the game resolves it against a league-average pitcher.

    Cells 00-32 read the pitcher's card, 45-99 the batter's, and the bands (2B,
    ROE) belong to neither: so the six tree lines are a 33:55 mixture of the
    league's card and hers, each renormalised over the tree, and the bands keep
    4/94 and 2/94. Cards are the smoothed probabilities, not the printed cells,
    and the 1% floor on the combined line is not applied.
    """
    tree = [CARD_LINES.index(l) for l in TREE_LINES]
    out = np.zeros(len(CARD_LINES))
    out[tree] = (P_CELLS / PA_CELLS * league[tree] / league[tree].sum()
                 + B_CELLS / PA_CELLS * card[tree] / card[tree].sum())
    for line, cells in BAND_CELLS.items():
        out[CARD_LINES.index(line)] = cells / PA_CELLS
    return out


@lru_cache(maxsize=1)
def break_even() -> dict:
    """Success rate a steal needs to pay, by (bases, outs), from the Markov RE24.

    gain = RE(safe) - RE(now); loss = RE(now) - RE(caught, one more out).
    Returns (gain, loss, break-even). A run that scores on the throw is ignored,
    as in the blog post's table.
    """
    table = markov.run_expectancy()
    re = markov.re_of
    out = {}
    for bases, to in ELIGIBLE:
        for outs in range(3):
            if to == 0:
                safe, caught = "_2" + bases[2], "__" + bases[2]
            else:
                safe, caught = bases[0] + "_3", bases[0] + "__"
            now = re(table, bases, outs)
            gain = re(table, safe, outs) - now
            loss = now - re(table, caught, outs + 1)
            out[(bases, outs)] = (gain, loss, loss / (gain + loss))
    return out


@dataclass
class Steals:
    """Per-player steal parameters, in the order of `ids`.

    attempt[p, kind]  probability she goes on an opportunity of that kind
    safe[p]           probability she is safe when she goes
    """
    ids: list
    attempt: np.ndarray
    safe: np.ndarray


def steal_params(ids, ratings, league_rate: dict, green_light=True, flat=False) -> Steals:
    """attempt = green light x smoothed attempt scale x league rate for the kind.

    Green light: her smoothed success rate beats the break-even of that base-out
    state. `flat` skips the league rate by kind and uses her own smoothed
    attempt rate per opportunity on every kind (a sensitivity check).
    """
    be = break_even()
    attempt = np.zeros((len(ids), len(KINDS)))
    safe = np.zeros(len(ids))
    for n, pid in enumerate(ids):
        known = pid in ratings.index
        scale = float(ratings.loc[pid, "attempt_scale"]) if known else 1.0
        base_rate = float(ratings.loc[pid, "attempt_rate"]) if known else ratings.attrs["league_att"]
        s = float(ratings.loc[pid, "success_rate"]) if known else ratings.attrs["league_ok"]
        safe[n] = s
        for k, (bases, outs) in enumerate(KINDS):
            to = dict(ELIGIBLE)[bases]
            rate = base_rate if flat else min(1.0, scale * league_rate[(to, outs)])
            go = (s > be[(bases, outs)][2]) if green_light else True
            attempt[n, k] = rate if go else 0.0
    return Steals(list(ids), attempt, safe)


# ----------------------------------------------------------------------------
# evaluating a lineup
# ----------------------------------------------------------------------------

class Evaluator:
    """Exact expected runs over `INNINGS` innings for a batting order drawn from
    a pool of players. Build once per pool, then call `value(order)` with a list
    of pool indices in batting order."""

    def __init__(self, cards: np.ndarray, steals: Steals):
        g = self.g = graph()
        self.cards, self.steals = cards, steals
        self.R = R = len(g.states)
        E_pa, E_run = len(g.pa_src), len(g.run_src)
        st = np.where(g.st_lag >= 0)[0]
        self.st = st
        self.src = np.concatenate([g.pa_src, g.run_src, st, st])
        self.dst = np.concatenate([g.pa_dst, g.run_dst, g.st_safe[st], g.st_caught[st]])
        etype = np.concatenate([np.zeros(E_pa, int), np.ones(E_run, int),
                                np.full(len(st), 2), np.full(len(st), 3)])
        self.adv = (etype == 0).astype(int)
        self.E = [E_pa, E_run, len(st)]
        self.loc = np.zeros(R, int)
        self.nk = []
        self.layer_states = []
        for k in range(3):
            idx = np.where(g.outs == k)[0]
            self.layer_states.append(idx)
            self.loc[idx] = np.arange(len(idx))
            self.nk.append(len(idx))
        slayer = g.outs[self.src]
        dlayer = np.where(self.dst >= 0, g.outs[np.maximum(self.dst, 0)], 9)
        self.by_layer = []
        for k in range(3):
            base = np.where(slayer == k)[0]
            self.by_layer.append((base[dlayer[base] == 9], base[dlayer[base] == k],
                                  base[(dlayer[base] > k) & (dlayer[base] < 9)]))
        self.start_state = g.index[(0, CFG0)]

    def value(self, order, detail=False):
        g, R = self.g, self.R
        L = np.asarray(order)
        card = self.cards[L]                                     # (9, 8) by batting slot
        pa_w = card @ g.pa_p.T                                   # (9, E_pa)
        rew_pa = card @ g.pa_runs.T                              # (9, R)
        slot = np.arange(9)[:, None]
        lag = g.st_lag[None, :]
        runner = (slot - np.maximum(lag, 0)) % 9                 # (9, R)
        live = lag >= 0
        a = np.where(live, self.steals.attempt[L][runner, g.st_kind[None, :]], 0.0)
        s = np.where(live, self.steals.safe[L][runner], 0.0)
        rs = g.run_share[None, :]
        pa_scale, run_scale = (1 - a) * (1 - rs), (1 - a) * rs
        W = np.concatenate([pa_w * pa_scale[:, g.pa_src],
                            g.run_p[None, :] * run_scale[:, g.run_src],
                            (a * s)[:, self.st], (a * (1 - s))[:, self.st]], axis=1)   # (9, E)
        nb = (np.arange(9)[:, None] + self.adv[None, :]) % 9                             # (9, E)
        Zabs = np.zeros((9 * R, 10))
        for k in (2, 1, 0):
            n = self.nk[k]
            size = 9 * n
            idx = self.layer_states[k]
            rew = pa_scale[:, idx] * rew_pa[:, idx] + run_scale[:, idx] * g.run_runs[None, idx]
            rhs = np.zeros((size, 10))
            rhs[:, 0] = rew.reshape(-1)
            ends, same, up = self.by_layer[k]
            bcol = np.arange(9)[:, None]
            row = lambda e: (bcol * n + self.loc[self.src[e]][None, :])          # local source rows
            if len(ends):
                rows = row(ends).ravel()
                cols = 1 + nb[:, ends].ravel()
                rhs += np.bincount(rows * 10 + cols, weights=W[:, ends].ravel(),
                                   minlength=size * 10).reshape(size, 10)
            if len(up):
                rows = row(up).ravel()
                dst_abs = (nb[:, up] * R + self.dst[up][None, :]).ravel()
                w = W[:, up].ravel()
                for c in range(10):
                    rhs[:, c] += np.bincount(rows, weights=w * Zabs[dst_abs, c], minlength=size)
            Q = np.zeros(size * size)
            if len(same):
                rows = row(same).ravel()
                cols = (nb[:, same] * n + self.loc[self.dst[same]][None, :]).ravel()
                Q = np.bincount(rows * size + cols, weights=W[:, same].ravel(),
                                minlength=size * size)
            Z = np.linalg.solve(np.eye(size) - Q.reshape(size, size), rhs)
            abs_rows = (np.arange(9)[:, None] * R + idx[None, :]).ravel()
            Zabs[abs_rows] = Z
        starts = np.arange(9) * R + self.start_state
        runs, T = Zabs[starts, 0], Zabs[starts, 1:]
        v = np.zeros(9)
        v[0] = 1.0
        total, per = 0.0, []
        for _ in range(INNINGS):
            per.append(float(v @ runs))
            total += per[-1]
            v = v @ T
        return (total, per, runs, T) if detail else total


def main() -> None:
    import time
    from wpbl.dice import cards as dice_cards, league_card, plate_appearances
    g = graph()
    print(f"{len(g.states)} lag states, {len(g.pa_src)} PA edges, {len(g.run_src)} running-play edges, "
          f"{int((g.st_lag >= 0).sum())} steal states; anomalies {g.anomalies}")
    print("break-even (gain, loss, needed success):")
    for k, v in break_even().items():
        print("  ", k, [round(x, 3) for x in v])
    league = league_card(plate_appearances()).to_numpy()
    avg = facing_average_pitcher(league, league)
    print("league card", dict(zip(CARD_LINES, league.round(4))))
    print("league card as mixed (should equal itself)", dict(zip(CARD_LINES, avg.round(4))))
    ratings = None
    steals = Steals(list(range(1)), np.zeros((1, len(KINDS))), np.array([0.85]))
    ev = Evaluator(np.array([avg]), steals)
    t0 = time.time()
    total, per, runs, T = ev.value([0] * 9, detail=True)
    print(f"league lineup, no steals: {total:.3f} runs in 7 innings, {per[0]:.3f} an inning "
          f"({time.time() - t0:.2f}s)")
    print("advance.py league RE(___,0) x7:", 7 * advance.run_expectancy(advance.league_card())[0])


if __name__ == "__main__":
    main()
