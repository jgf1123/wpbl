"""Which way of combining pitcher and batter cards predicts held-out PAs best,
scored in runs and in pitches?  5 combination rules x 4 card sets (+ league only).

Cross-fitted: PAs split at random into halves; cards built on one half score the
other; swap; repeat over REPEATS random splits.  No PA helps build the cards
that score it."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact, plate_appearances

pd.set_option("display.width", 240)
REPEATS, BOOT, SEED = 20, 2000, 20260917
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]
FREE = LINES[:-1]                                   # OUT is always the remainder
IDX = {l: i for i, l in enumerate(LINES)}
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE", "groundout": "OUT",
           "flyout": "OUT", "popup": "OUT", "lineout": "OUT", "foul_out": "OUT", "out": "OUT"}
FLOOR = {"P": 20, "B": 12}                          # min build-half PAs to inform the spread estimate
CARD_SETS = {"all": ({*FREE}, {*FREE}),
             "spec": ({"K", "BB"}, {"K", "HR", "HBP", "1B"}),
             "pitcher only": ({*FREE}, set()),
             "batter only": (set(), {*FREE})}
RULES = ["additive", "flat log5", "two-level log5", "averaging"]
EPS = 1e-4

# ---------------- data ----------------
plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n)) for e, n in zip(pa["event_type"], pa["narrative"])]
print("unmapped PAs dropped:", int(pa["line"].isna().sum()))
pa = pa.dropna(subset=["line"]).reset_index(drop=True)
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
y = pa["line"].map(IDX).to_numpy()
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs")

# run value per line (training linear weights) and pitches per line
lw = plate_appearances("training")
lw["line"] = lw["outcome"].map(TO_LINE)
w = lw.dropna(subset=["line"]).groupby("line")["run_value"].mean().reindex(LINES).to_numpy()
c = pa.groupby("line")["n_pitches_est"].mean().reindex(LINES).to_numpy()
print("run value per line:", dict(zip(LINES, w.round(3))))
print("pitches per line:  ", dict(zip(LINES, c.round(2))))

# pitcher group: kept = 6+ regular-season IP (18 outs), else tryout
reg = tables.read("pitching", "default").groupby("person_id")["ip_outs"].sum()
kept = set(reg[reg >= 18].index)
print(f"kept pitchers {len(kept)}, tryout {int((reg < 18).sum())} (regular season)")


_nb = pa.groupby('B').size()
_by = _nb.groupby(_nb).sum().sort_index()
U_FULL = _nb.map((_by.cumsum() - _by / 2) / _by.sum())


def onehot(lines):
    m = np.zeros((len(lines), len(LINES)))
    m[np.arange(len(lines)), lines] = 1
    return m


def cards(build, side, league):
    """Smoothed 8-line card per person on `side`, built on `build` only.
    Returns (DataFrame person x FREE lines, spread constants per line)."""
    x = pd.DataFrame(onehot(build["line"].map(IDX).to_numpy()), columns=LINES).groupby(build[side].to_numpy()).sum()
    n = x.sum(axis=1)
    rate = x.div(n, axis=0)
    if side == "B":
        # quartiles of PAs: pooled midpoint of each PA-count tie group in the running total
        u = n.index.to_series().map(U_FULL)          # position from full-season PA counts
        low = x[u < 0.5].sum() / n[u < 0.5].sum()
        high = x[u >= 0.5].sum() / n[u >= 0.5].sum()
        frac = ((u - 0.25) / 0.5).clip(0, 1)
        global LOHI
        LOHI = (low, high)
        target = pd.DataFrame(np.outer(1 - frac, low) + np.outer(frac, high), index=n.index, columns=LINES)
        default = None
    else:
        grp = pd.Series(np.where(n.index.isin(kept), "kept", "tryout"), index=n.index)
        means = x.groupby(grp).sum().div(n.groupby(grp).sum(), axis=0)
        target = means.reindex(grp.to_numpy()).set_index(n.index)
        default = means.loc["tryout"] if "tryout" in means.index else league
    qual = n >= FLOOR[side]
    card, ks = pd.DataFrame(index=n.index), {}
    for line in FREE:
        t = target[line]
        tau2 = float(((rate[line] - t) ** 2 - t * (1 - t) / n)[qual].mean())
        k = league[line] * (1 - league[line]) / tau2 if tau2 > 0 else np.inf
        ks[line] = k
        card[line] = t if np.isinf(k) else (x[line] + k * t) / (n + k)
    return card, ks, default


def full(entries, league, on):
    """n x 8 distribution: chosen entries from the card, league elsewhere, OUT = remainder."""
    d = np.tile(league.to_numpy(), (len(entries), 1))
    for line in on:
        d[:, IDX[line]] = entries[line].to_numpy()
    d[:, IDX["OUT"]] = 1 - d[:, :IDX["OUT"]].sum(axis=1)
    return d


def norm(m):
    return m / m.sum(axis=1, keepdims=True)


def combine(rule, P, B, L):
    if rule == "additive":
        raw = P + B - L
        return norm(np.clip(raw, EPS, None)), (raw < EPS).any(axis=1)
    if rule == "flat log5":
        return norm(P * B / L), None
    if rule == "averaging":
        return (P + B) / 2, None
    top = [IDX["K"], IDX["BB"], IDX["HBP"]]            # two-level: K/BB/HBP/in play, then within in play
    bip = [IDX[l] for l in ("HR", "1B", "2B", "ROE", "OUT")]
    def split(M):
        return np.column_stack([M[:, top], M[:, bip].sum(axis=1)]), M[:, bip] / M[:, bip].sum(axis=1, keepdims=True)
    Lv = L[None, :]
    (pt, pc), (bt, bc), (lt, lc) = split(P), split(B), split(Lv)
    t = norm(pt * bt / lt)
    inner = norm(pc * bc / lc)
    out = np.zeros_like(P)
    out[:, top] = t[:, :3]
    out[:, bip] = t[:, [3]] * inner
    return out, None


names = ["league only"] + [f"{r} / {s}" for r in RULES for s in CARD_SETS]
nC = len(names)
runs_se = np.zeros((len(pa), nC)); pit_se = np.zeros((len(pa), nC)); ll = np.zeros((len(pa), nC))
pred_runs = np.zeros((len(pa), nC)); league_runs = np.zeros(len(pa))
clipped = np.zeros(nC); zeros = np.zeros(nC); kept_k = {"P": [], "B": []}
rng = np.random.default_rng(SEED)
for r in range(REPEATS):
    game_half = dict(zip(sorted(pa["game_id"].unique()), rng.permutation(np.arange(pa["game_id"].nunique()) % 2)))
    half = pa["game_id"].map(game_half).to_numpy()
    for fold in (0, 1):
        build, test = pa[half != fold], np.flatnonzero(half == fold)
        Ls = build["line"].value_counts(normalize=True).reindex(LINES, fill_value=0)
        L = Ls.to_numpy()
        side_cards = {}
        for side in ("P", "B"):
            card, ks, default = cards(build, side, Ls)
            kept_k[side].append(ks)
            ids = pa.loc[test, side]
            if default is None:   # batters with no build-half PAs: target at their full-season position
                fr = ((ids.map(U_FULL) - 0.25) / 0.5).clip(0, 1).to_numpy()[:, None]
                lo, hi = LOHI
                fill = pd.DataFrame((1 - fr) * lo[FREE].to_numpy() + fr * hi[FREE].to_numpy(), columns=FREE, index=ids.to_numpy())
                side_cards[side] = card.reindex(ids.to_numpy()).fillna(fill)
            else:
                side_cards[side] = card.reindex(ids.to_numpy()).fillna(default[FREE])
        v, cc = w[y[test]], c[y[test]]
        league_runs[test] += L @ w
        for j, name in enumerate(names):
            if name == "league only":
                p = np.tile(L, (len(test), 1))
            else:
                rule, cs = name.split(" / ")
                on_p, on_b = CARD_SETS[cs]
                P = full(side_cards["P"], Ls, on_p)
                B = full(side_cards["B"], Ls, on_b)
                p, clip = combine(rule, P, B, L)
                if clip is not None:
                    clipped[j] += clip.sum()
            m_runs, m_pit = p @ w, p @ cc if False else p @ c
            runs_se[test, j] += (v - m_runs) ** 2
            pit_se[test, j] += (cc - m_pit) ** 2
            zeros[j] += int((p[np.arange(len(test)), y[test]] <= 0).sum())
            ll[test, j] += np.log(np.clip(p[np.arange(len(test)), y[test]], 1e-12, None))
            pred_runs[test, j] += m_runs
runs_se /= REPEATS; pit_se /= REPEATS; ll /= REPEATS; pred_runs /= REPEATS; league_runs /= REPEATS

# ---------------- game-clustered bootstrap ----------------
games_codes, g = np.unique(pa["game_id"], return_inverse=True)
nG = len(games_codes)
cnt = np.bincount(g, minlength=nG).astype(float)
def game_sums(S):
    return np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(S.shape[1])], axis=1)
W = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)

def table(S, label, scale, lower_better=True):
    G = game_sums(S)
    point = S.mean(axis=0)
    boot = (W @ G) / (W @ cnt)[:, None]
    base = 0                                          # league only
    best = int(np.argmin(point) if lower_better else np.argmax(point))
    sign = 1 if lower_better else -1
    rows = []
    for j in range(nC):
        gain = sign * (point[base] - point[j]) * scale
        gain_se = (boot[:, base] - boot[:, j]).std() * scale
        gap = sign * (point[j] - point[best]) * scale
        gap_se = (boot[:, j] - boot[:, best]).std() * scale
        rows.append({"candidate": names[j], f"{label} gain vs league": round(gain, 3), "±SE": round(gain_se, 3),
                     "behind best": round(gap, 3), "±SE ": round(gap_se, 3),
                     "gap/SE": round(gap / gap_se, 1) if gap_se > 0 else 0.0})
    return pd.DataFrame(rows)

print(f"\n=== RUNS: squared error of expected run value, x1000 per PA (higher gain = better) ===")
print(table(runs_se, "runs", 1000).sort_values("behind best").to_string(index=False))
print(f"\n=== PITCHES: squared error of expected pitches, x1000 per PA ===")
print(table(pit_se, "pitches", 1000).sort_values("behind best").to_string(index=False))
print(f"\n=== LOG-LIKELIHOOD per PA, x1000 (diagnostic) ===")
print(table(ll, "loglik", 1000, lower_better=False).sort_values("behind best").to_string(index=False))

# ---------------- calibration slopes: actual vs predicted run deviation per player ----------------
print("\n=== calibration: slope of actual on predicted runs above league, per player (1 = right size) ===")
act = w[y] - league_runs
rows = []
for j in range(1, nC):
    d = pred_runs[:, j] - league_runs
    row = {"candidate": names[j]}
    on = CARD_SETS[names[j].split(" / ")[1]]
    for side, covered in (("P", on[0]), ("B", on[1])):
        n_s = pa.groupby(side).size()
        dp = pd.Series(d).groupby(pa[side]).mean()
        da = pd.Series(act).groupby(pa[side]).mean()
        s = float((n_s * dp * da).sum() / (n_s * dp ** 2).sum()) if covered else float("nan")
        row[f"slope {'pitchers' if side == 'P' else 'batters'}"] = round(s, 2)
    row["additive floor hit (% of scored PAs)"] = round(100 * clipped[j] / (len(pa) * REPEATS), 2) if "additive" in names[j] else ""
    row["zero-prob outcomes"] = int(zeros[j])
    rows.append(row)
print(pd.DataFrame(rows).to_string(index=False))

print("\n=== smoothing constants k (median over the 40 builds; inf = no measurable spread, card = target) ===")
for side in ("P", "B"):
    k = pd.DataFrame(kept_k[side]).median().round(0)
    print(f"  {'pitchers' if side == 'P' else 'batters'}: {k.to_dict()}")

print("\n=== batters by full-data PA quartile: runs per PA above league, held-out games ===")
nb = pa.groupby("B").size()
by_n = nb.groupby(nb).sum().sort_index()
u = nb.map((by_n.cumsum() - by_n / 2) / by_n.sum())
quart = (u * 4).astype(int).clip(0, 3) + 1
jb = names.index("flat log5 / batter only")
frame = pd.DataFrame({"q": pa["B"].map(quart), "pred": pred_runs[:, jb] - league_runs, "act": act})
# SE by game bootstrap is overkill here; binomial-ish SE of the actual mean from per-PA spread
out = frame.groupby("q").agg(batters=("q", lambda s: pa.loc[s.index, "B"].nunique()), PAs=("act", "size"),
                             predicted=("pred", "mean"), actual=("act", "mean"), sd=("act", "std"))
out["actual SE"] = out["sd"] / np.sqrt(out["PAs"])
print((out.drop(columns="sd") * [1, 1, 1000, 1000, 1000]).round(1).rename(
    columns={"predicted": "predicted (mruns/PA)", "actual": "actual (mruns/PA)", "actual SE": "SE"}).to_string())
