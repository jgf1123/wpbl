"""Choose each card line's smoothing constant k by held-out prediction.

Game-level halves (20 random splits x 2 folds). Cohort targets rebuilt in each
build half (usage rank, size + event minimums, slugger HR exception). One line's
k varies at a time; batter lines scored from batter cards alone, pitcher lines
from pitcher cards alone. Score: squared error of expected run value (primary)
and the line's own Brier score. No tie rule: reports the best k and the ranges within 1 and 2 SE of it."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact, plate_appearances

pd.set_option("display.width", 250)
REPEATS, BOOT, SEED = 20, 2000, 20260918
LINES = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE"]
ALL = LINES + ["OUT"]
KGRID = [2 ** i for i in range(12)] + [np.inf]          # 1..2048, log-spaced; inf = reference
MIN_RATE = 0.01
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
# cohort size (PA) per line: 4k from the agreed estimates; lines with no finite
# estimate use 4 x the smallest plausible k from the bootstrap (ASSUMPTION, 18 Sep)
SIZE = {"B": {"K": 184, "HBP": 122, "HR": 145, "1B": 287, "BB": 4 * 208, "2B": 4 * 127, "ROE": 4 * 328},
        "P": {"K": 191, "BB": 328, "HBP": 4 * 91, "HR": 4 * 237, "1B": 4 * 107, "2B": 4 * 105, "ROE": 4 * 365}}
BASE_K = {"B": {"K": 46, "BB": np.inf, "HBP": 31, "HR": 36, "1B": 72, "2B": np.inf, "ROE": np.inf},
          "P": {"K": 48, "BB": 82, "HBP": 206, "HR": 1669, "1B": 423, "2B": 523, "ROE": np.inf}}
SLUGGERS = ["Denae Benites", "Kelsie Whitmore"]
SLUGGER_COHORT = ["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"]

plays = tables.read("plays", "training")
bat = tables.read("batting", "training")
games = tables.read("games", "all")
team_name = pd.concat([games.set_index("home_team_id")["home_team_name"],
                       games.set_index("away_team_id")["away_team_name"]]).groupby(level=0).first()
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy().reset_index(drop=True)
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["P_team"] = pa["pitching_team_id"].map(team_name)
pa["date"] = pa["game_date"].astype(str).str[:10]
y = pa["line"].map({l: i for i, l in enumerate(ALL)}).to_numpy()
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs")

lw = plate_appearances("training")
lw["line"] = lw["outcome"].map(TO_LINE).fillna("OUT")
w = lw.groupby("line")["run_value"].mean().reindex(ALL).to_numpy()


def tenure_share(frame, who, team, date, own, per_date):
    out = {}
    for pid, g in frame.groupby(who):
        firsts = g.groupby(team)[date].min().sort_values()
        denom = 0
        for i, (t, first) in enumerate(firsts.items()):
            d = per_date.loc[t]
            lo = first if i > 0 else "0000"
            hi = firsts.iloc[i + 1] if i + 1 < len(firsts) else "9999"
            denom += float(d[(d.index >= lo) & (d.index < hi)].sum())
        out[pid] = own.get(pid, 0) / denom
    return pd.Series(out)


bat["date"] = bat["game_date"].astype(str).str[:10]
team_games = bat.drop_duplicates(["game_id", "team_name"]).groupby(["team_name", "date"]).size()
share = {"B": tenure_share(bat, "person_id", "team_name", "date", bat.groupby("person_id")["in_starting_lineup"].sum(), team_games),
         "P": tenure_share(pa, "P", "P_team", "date", pa.groupby("P").size(), pa.groupby(["P_team", "date"]).size())}
people = {s: np.array(sorted(pa[s].unique())) for s in ("B", "P")}


def targets(build, side, L):
    """Cohort target per person and line, from the build half only."""
    ids = people[side]
    x = pd.crosstab(build[side], build["line"]).reindex(index=ids, columns=ALL, fill_value=0)
    n = x.sum(axis=1).to_numpy().astype(float)
    sv = share[side].reindex(ids).fillna(0.0).to_numpy()
    slug = np.isin([name.get(i, i) for i in ids], SLUGGERS) if side == "B" else np.zeros(len(ids), bool)
    in_slug_cohort = np.isin([name.get(i, i) for i in ids], SLUGGER_COHORT)
    T = {}
    for line in LINES:
        xv = x[line].to_numpy().astype(float)
        size, events = SIZE[side][line], SIZE[side][line] * L[line]
        special = side == "B" and line == "HR"
        t = np.zeros(len(ids))
        for i in range(len(ids)):
            if special and slug[i]:
                take = np.flatnonzero(in_slug_cohort & (np.arange(len(ids)) != i))
            else:
                allowed = np.arange(len(ids)) != i
                if special:
                    allowed &= ~slug
                cand = np.flatnonzero(allowed & (n > 0))
                dist = np.round(np.abs(sv[cand] - sv[i]), 12)
                take, got_n, got_x = [], 0.0, 0.0
                for d in np.unique(dist):                # whole tie groups, nearest first
                    grp = cand[dist == d]
                    take.extend(grp)
                    got_n += n[grp].sum(); got_x += xv[grp].sum()
                    if got_n >= size and got_x >= events:
                        break
                take = np.array(take)
            t[i] = xv[take].sum() / max(n[take].sum(), 1)
        T[line] = t
    return x, n, pd.DataFrame(T, index=ids)


def card_line(xv, n, t, k):
    c = xv / np.where(n > 0, n, 1) if k == 0 else (t if np.isinf(k) else (xv + k * t) / (n + k))
    c = np.where((k == 0) & (n == 0), t, c)              # raw rate undefined with no PAs: use the target
    return np.maximum(c, MIN_RATE)


# scores[side][line] -> per-PA array (n_pa x len(KGRID)) of runs SE and Brier, averaged over repeats
runs = {s: {l: np.zeros((len(pa), len(KGRID))) for l in LINES} for s in ("B", "P")}
brier = {s: {l: np.zeros((len(pa), len(KGRID))) for l in LINES} for s in ("B", "P")}
rng = np.random.default_rng(SEED)
gids = sorted(pa["game_id"].unique())
for r in range(REPEATS):
    half_of = dict(zip(gids, rng.permutation(np.arange(len(gids)) % 2)))
    half = pa["game_id"].map(half_of).to_numpy()
    for fold in (0, 1):
        build, test = pa[half != fold], np.flatnonzero(half == fold)
        L = build["line"].value_counts(normalize=True).reindex(ALL, fill_value=0)
        for side in ("B", "P"):
            x, n, T = targets(build, side, L)
            pos = pd.Series(np.arange(len(people[side])), index=people[side])[pa.loc[test, side]].to_numpy()
            # baseline card: every line at its base k; OUT is the remainder
            base = np.zeros((len(people[side]), len(LINES)))
            for j, line in enumerate(LINES):
                base[:, j] = card_line(x[line].to_numpy().astype(float), n, T[line].to_numpy(), BASE_K[side][line])
            base_m = base @ w[:-1] + (1 - base.sum(axis=1)) * w[-1]
            v = w[y[test]]
            for j, line in enumerate(LINES):
                is_line = (y[test] == ALL.index(line)).astype(float)
                for kk, k in enumerate(KGRID):
                    c = card_line(x[line].to_numpy().astype(float), n, T[line].to_numpy(), k)
                    m = base_m + (c - base[:, j]) * (w[j] - w[-1])   # swap this line, mass from/to outs
                    runs[side][line][test, kk] += (v - m[pos]) ** 2
                    brier[side][line][test, kk] += (is_line - c[pos]) ** 2
    print(f"  split {r + 1}/{REPEATS} done", flush=True)

# ---------------- summarise with a game bootstrap ----------------
g = pd.Series(pd.Categorical(pa["game_id"])).cat.codes.to_numpy()
nG = g.max() + 1
cnt = np.bincount(g, minlength=nG).astype(float)
Wb = np.random.default_rng(SEED + 1).multinomial(nG, np.full(nG, 1 / nG), size=BOOT).astype(float)


def boot_means(S):
    G = np.stack([np.bincount(g, weights=S[:, j], minlength=nG) for j in range(S.shape[1])], axis=1)
    return S.mean(axis=0), (Wb @ G) / (Wb @ cnt)[:, None]


labels = ["inf" if np.isinf(k) else str(int(k)) for k in KGRID]
chosen = {}
for side, label, n_ref in (("B", "BATTER", 75), ("P", "PITCHER", 150)):
    print(f"\n==================== {label} lines: runs score gain over k = inf (x1e6 per PA; higher is better) ====================")
    rows = []
    for line in LINES:
        S = runs[side][line] / REPEATS
        pt, bt = boot_means(S)
        best = int(np.argmin(pt))
        gap_se = np.array([(bt[:, j] - bt[:, best]).std() for j in range(len(KGRID))])
        near1 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[best] <= gap_se[j]]
        near2 = [KGRID[j] for j in range(len(KGRID)) if pt[j] - pt[best] <= 2 * gap_se[j]]
        fmt = lambda v: 'inf' if np.isinf(v) else str(int(v))
        chosen[(side, line)] = KGRID[best]
        inf_j = len(KGRID) - 1
        gains = {lab: round(1e6 * (pt[inf_j] - pt[j]), 0) for j, lab in enumerate(labels[:-1])}
        B = brier[side][line] / REPEATS
        pb, bb = boot_means(B)
        bbest = int(np.argmin(pb))
        k_pick = KGRID[best]
        rows.append({"line": line, **gains, "best": labels[best],
                     f"own share @{n_ref}": "0%" if np.isinf(k_pick) else f"{n_ref / (n_ref + k_pick):.0%}",
                     "within 1 SE": f"{fmt(min(near1))}-{fmt(max(near1))}",
                     "within 2 SE": f"{fmt(min(near2))}-{fmt(max(near2))}",
                     "SE best vs inf": round(1e6 * gap_se[inf_j], 0), "Brier best": labels[bbest]})
    print(pd.DataFrame(rows).to_string(index=False))

print("\nchosen k:", {f"{s}-{l}": ("inf" if np.isinf(k) else k) for (s, l), k in chosen.items()})

# ---------------- Lansdell and the batter spread under the chosen k (full data) ----------------
L = pa["line"].value_counts(normalize=True).reindex(ALL, fill_value=0)
x, n, T = targets(pa, "B", L)
card = pd.DataFrame({line: card_line(x[line].to_numpy().astype(float), n, T[line].to_numpy(), chosen[("B", line)])
                     for line in LINES}, index=people["B"])
card["OUT"] = 1 - card.sum(axis=1)
raw = x.div(np.where(n > 0, n, 1), axis=0)
val = pd.DataFrame({"PA": n, "raw": raw[ALL].to_numpy() @ w, "card": card[ALL].to_numpy() @ w}, index=people["B"])
val.index = [name.get(i, i) for i in val.index]
q = val["PA"] >= 25
print("\n=== context-neutral runs per PA x1000, best k, full data ===")
print((val.loc[["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"]] * [1, 1000, 1000]).round(0).to_string())
print(f"spread across batters with 25+ PA (SD): raw {1000 * val.loc[q, 'raw'].std():.0f}, card {1000 * val.loc[q, 'card'].std():.0f}"
      f"   (previous cards: 68)")
lid = [i for i in people["B"] if name.get(i) == "Ashton Lansdell"][0]
print("\nLansdell line by line (%):")
print(pd.DataFrame({"raw": 100 * raw.loc[lid, LINES], "target": 100 * T.loc[lid, LINES], "card": 100 * card.loc[lid, LINES],
                    "k": [("inf" if np.isinf(chosen[("B", l)]) else chosen[("B", l)]) for l in LINES]}).round(1).T.to_string())
