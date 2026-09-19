"""Cohort cards v2.

Rank: batters by share of team games started, pitchers by share of team batters
faced (both over her tenure with each team). Cohort per line: nearest players
by share, excluding her, whole tie groups at once, until the cohort holds 4k
PAs AND at least as many events as a league-average cohort of 4k PAs would.
HR special case: Benites and Whitmore take a fixed cohort (the other slugger,
Lansdell, Mackay) and are left out of everyone else's HR cohort and of the HR
spread estimate. Spread estimate subtracts both her own and the cohort's
sampling noise. Every card entry is floored at 1%, taken from outs."""
import numpy as np
import pandas as pd
from wpbl import tables
from wpbl.batters import contact

pd.set_option("display.width", 250)
TO_LINE = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR", "single": "1B",
           "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
CARD = {"B": ["K", "HBP", "HR", "1B"], "P": ["K", "BB"]}
FLOOR_PA = {"B": 25, "P": 40}
MIN_RATE = 0.01
SLUGGERS = ["Denae Benites", "Kelsie Whitmore"]            # 12 and 12 HR; next best 5 (user, 17 Sep)
SLUGGER_COHORT = ["Denae Benites", "Kelsie Whitmore", "Ashton Lansdell", "Jamie Mackay"]

plays = tables.read("plays", "training")
bat = tables.read("batting", "training")
games = tables.read("games", "all")
team_name = pd.concat([games.set_index("home_team_id")["home_team_name"],
                       games.set_index("away_team_id")["away_team_name"]]).groupby(level=0).first()
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pid_of = {v: k for k, v in name.items()}
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO_LINE.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pa["P"] = pa["pitcher_id"].map(person).fillna(pa["pitcher_id"])
pa["P_team"] = pa["pitching_team_id"].map(team_name)
pa["date"] = pa["game_date"].astype(str).str[:10]
L = pa["line"].value_counts(normalize=True)
print(f"{pa['game_id'].nunique()} games, {len(pa)} PAs")


def tenure_share(frame, who, team, date, own, per_date):
    """own[pid] / her team's per_date totals during her tenure (split at her first game for a new team)."""
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
starts = bat.groupby("person_id")["in_starting_lineup"].sum()
share = {"B": tenure_share(bat, "person_id", "team_name", "date", starts, team_games),
         "P": tenure_share(pa, "P", "P_team", "date", pa.groupby("P").size(), pa.groupby(["P_team", "date"]).size())}


def league_k(x, n, line, keep):
    r = x[line] / n
    tau2 = float(np.var(r[keep], ddof=1)) - float((L[line] * (1 - L[line]) / n[keep]).mean())
    return L[line] * (1 - L[line]) / tau2 if tau2 > 0 else np.inf


def build(side):
    x = pd.crosstab(pa[side], pa["line"])
    n = x.sum(axis=1)
    s = share[side].reindex(n.index).fillna(0.0)
    ids = n.index.to_numpy()
    sv, nv = s.to_numpy(), n.to_numpy()
    slug = np.isin([name.get(i, i) for i in ids], SLUGGERS) if side == "B" else np.zeros(len(ids), bool)
    qual = (n >= FLOOR_PA[side]).to_numpy()
    rows, cards, info = {}, {}, {}
    for line in CARD[side]:
        xv = x[line].to_numpy()
        special = side == "B" and line == "HR"
        keep_k = qual & ~slug if special else qual
        size = 4 * league_k(x, n, line, keep_k)
        events = size * L[line]
        t, nc, pc, ec = np.zeros(len(ids)), np.zeros(len(ids)), np.zeros(len(ids), int), np.zeros(len(ids))
        for i in range(len(ids)):
            if special and slug[i]:
                take = np.flatnonzero(np.isin([name.get(j, j) for j in ids], SLUGGER_COHORT) & (np.arange(len(ids)) != i))
            else:
                allowed = np.arange(len(ids)) != i
                if special:
                    allowed &= ~slug
                cand = np.flatnonzero(allowed)
                dist = np.round(np.abs(sv[cand] - sv[i]), 12)
                take, got_n, got_x = [], 0.0, 0.0
                for d in np.unique(dist):                  # whole tie groups at once, nearest first
                    grp = cand[dist == d]
                    take.extend(grp)
                    got_n += nv[grp].sum(); got_x += xv[grp].sum()
                    if got_n >= size and got_x >= events:
                        break
                take = np.array(take)
            nc[i], ec[i], pc[i] = nv[take].sum(), xv[take].sum(), len(take)
            t[i] = xv[take].sum() / nv[take].sum()
        r = xv / nv
        # real spread around the targets: subtract her own AND the cohort's sampling noise
        tau2 = float(np.mean(((r - t) ** 2 - t * (1 - t) / nv - t * (1 - t) / nc)[keep_k]))
        k = L[line] * (1 - L[line]) / tau2 if tau2 > 0 else np.inf
        card = t if np.isinf(k) else (xv + k * t) / (nv + k)
        cards[line] = pd.Series(card, index=ids)
        rows[line] = pd.DataFrame({"target": t, "cohort PA": nc, "cohort players": pc, "cohort events": ec,
                                   "raw": r}, index=ids)
        info[line] = {"size (PA)": round(size) if np.isfinite(size) else "inf (everyone)", "min events": round(events, 1) if np.isfinite(events) else "-", "k": round(k) if np.isfinite(k) else "inf"}
    card = pd.DataFrame(cards)
    floored = card < MIN_RATE
    card = card.clip(lower=MIN_RATE)
    return x, n, s, card, floored, rows, info


for side, label in (("B", "batters"), ("P", "pitchers")):
    x, n, s, card, floored, rows, info = build(side)
    print(f"\n==================== {label} ====================")
    print(pd.DataFrame(info).T.to_string())
    print(f"\nsmallest cohorts per line:")
    for line, r in rows.items():
        r = r.assign(who=[name.get(i, i) for i in r.index])
        by_pa, by_pl = r.sort_values("cohort PA").iloc[0], r.sort_values("cohort players").iloc[0]
        print(f"  {line}: fewest PA {int(by_pa['cohort PA'])} ({int(by_pa['cohort players'])} players, "
              f"{int(by_pa['cohort events'])} events; {by_pa['who']});  fewest players {int(by_pl['cohort players'])} "
              f"({int(by_pl['cohort PA'])} PA; {by_pl['who']});  median {int(r['cohort PA'].median())} PA / "
              f"{int(r['cohort players'].median())} players;  largest {int(r['cohort PA'].max())} PA")
    print(f"\ncards floored at 1%: " + ", ".join(f"{l} {int(floored[l].sum())}" for l in floored))
    if side == "B":
        r = rows["HR"]
        hr = pd.DataFrame({"start share %": 100 * s, "PA": n, "HR": x["HR"], "raw %": 100 * r["raw"],
                           "target %": 100 * r["target"], "cohort": r["cohort players"].astype(int),
                           "card %": 100 * card["HR"], "card HR": card["HR"] * n})
        hr.index = [name.get(i, i) for i in hr.index]
        print("\nHR, top 12 by home runs:")
        print(hr.sort_values("HR", ascending=False).head(12).round(2).to_string())
        print("\nHR, everyday starters (tie group):")
        print(hr[hr["start share %"] >= 99.9].round(2).to_string())
        v = hr["card %"]
        print(f"\nHR cards: min {v.min():.1f} median {v.median():.1f} max {v.max():.1f} SD {v.std():.2f}; "
              f"total card HR {hr['card HR'].sum():.1f} vs actual {int(hr['HR'].sum())}")
        for line in ("K", "HBP", "1B"):
            v = 100 * card[line]
            print(f"  {line} cards: min {v.min():.1f} median {v.median():.1f} max {v.max():.1f} SD {v.std():.2f}")
    else:
        for line in ("K", "BB"):
            v = 100 * card[line]
            print(f"  {line} cards: min {v.min():.1f} median {v.median():.1f} max {v.max():.1f} SD {v.std():.2f}")

x = pd.crosstab(pa["B"], pa["line"]); n = x.sum(axis=1)
q = n >= 25
sl = pd.Series([name.get(i, i) in SLUGGERS for i in n.index], index=n.index)
for line in ("HR", "1B", "K", "HBP"):
    print(f"league-level k for batter {line}: all qualifiers {league_k(x, n, line, q):.0f}; "
          f"without Benites & Whitmore {league_k(x, n, line, q & ~sl):.0f}")
