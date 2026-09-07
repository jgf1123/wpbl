"""Analysis 1: kept in or replaced at the inning boundary.

    pixi run bullpen

At the end of every half-inning a manager makes one decision about the pitcher
who just finished: send her back out, or bring someone else in. The two things
plausibly driving it are how much she has already thrown and how much the
coming inning matters. This isolates that decision.

Why the inning boundary is the clean case: mid-inning changes are almost
always reactive -- 34 of the 37 in this season came with runners already on
base -- so the situation the manager is reacting to was created by the pitcher
being evaluated. At a boundary the slate is clean: bases empty, nobody out,
and the leverage of what is coming is known before anyone bats.

The game's opening assignment is excluded. A starter takes the mound in the
first because she is the starter, which is not this decision.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.leverage import Leverage
from wpbl.parse import OUT_DIR
from wpbl.usage_chart import CODES

BATTING_ORDER = 9      # batters faced per time through the order


def decisions(lev: Leverage) -> pd.DataFrame:
    """One row per inning-boundary decision about the incumbent pitcher."""
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    people = pd.read_parquet(OUT_DIR / "players.parquet").set_index("player_id")["person_name"]
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    starters = set(zip(pitching.loc[pitching["is_starter"], "game_id"],
                       pitching.loc[pitching["is_starter"], "person_id"]))

    live = (plays[plays["outs_before"] < 3]
            .dropna(subset=["batting_team_id", "pitching_team_id", "pitcher_id"])
            .sort_values(["game_id", "sequence"]))

    rows = []
    for (game_id, team_id), side in live.groupby(["game_id", "pitching_team_id"]):
        # Work through this team's half-innings in order, tracking what the
        # pitcher on the mound has thrown so far.
        halves = list(side.groupby(["inning", "half"], sort=False))
        thrown = {}          # person_id -> [pitches, batters faced, outs]
        incumbent = None
        for index, ((inning, half), block) in enumerate(halves):
            block = block.sort_values("sequence")
            faced = block[block["is_plate_appearance"]]
            order = list(dict.fromkeys(faced["pitcher_id"]))
            if not order:
                continue
            opener = order[0]

            if incumbent is not None:
                pitches, bf, _ = thrown[incumbent]
                first = block.iloc[0]
                diff = int(first["home_score_before"] - first["away_score_before"])
                lead = diff if half == "top" else -diff   # from the pitching side
                rows.append({
                    "game_id": game_id,
                    "team": team_id,
                    "inning": inning,
                    "half": half,
                    "pitcher": people.get(incumbent, incumbent),
                    "pitcher_id": incumbent,
                    "is_starter": (game_id, incumbent) in starters,
                    "pitches": pitches,
                    "batters_faced": bf,
                    "times_through": bf / BATTING_ORDER,
                    "lead": lead,
                    "li": lev.inning(inning, half, diff),
                    "replaced": opener != incumbent,
                    "replaced_by": people.get(opener, opener) if opener != incumbent else None,
                })

            for pitcher_id in order:
                block_for = block[block["pitcher_id"] == pitcher_id]
                got = thrown.setdefault(pitcher_id, [0, 0, 0])
                got[0] += int(block_for["n_pitches"].sum())
                got[1] += int(block_for["is_plate_appearance"].sum())
            # Outs are only known for the whole half-inning, so credit the
            # pitcher who finished it with completing it.
            thrown[order[-1]][2] += 3
            incumbent = order[-1]

    return pd.DataFrame(rows)


def logistic(x: np.ndarray, y: np.ndarray, names: list[str], iterations: int = 200):
    """Plain Newton-Raphson logistic regression with standard errors.

    Written out rather than pulled in so the whole pipeline stays on the four
    dependencies it already has.
    """
    design = np.column_stack([np.ones(len(x))] + [x[:, i] for i in range(x.shape[1])])
    beta = np.zeros(design.shape[1])
    for _ in range(iterations):
        eta = design @ beta
        prob = 1 / (1 + np.exp(-eta))
        weight = np.clip(prob * (1 - prob), 1e-10, None)
        hessian = design.T @ (design * weight[:, None])
        step = np.linalg.solve(hessian, design.T @ (y - prob))
        beta += step
        if np.max(np.abs(step)) < 1e-9:
            break
    covariance = np.linalg.inv(design.T @ (design * weight[:, None]))
    se = np.sqrt(np.diag(covariance))
    return beta, se, ["intercept"] + names


def main() -> None:
    pd.set_option("display.width", 240)
    lev = Leverage()
    d = decisions(lev)

    print(f"{len(d)} inning-boundary decisions across "
          f"{d['game_id'].nunique()} games; {int(d['replaced'].sum())} replacements "
          f"({d['replaced'].mean() * 100:.0f}%)\n")

    print("=== by leverage of the coming inning ===")
    d["li_band"] = pd.cut(d["li"], [0, 0.75, 1.25, 2.0, 99],
                          labels=["low <0.75", "avg 0.75-1.25", "high 1.25-2.0", "very high 2.0+"])
    print(d.groupby("li_band", observed=True).agg(
        n=("replaced", "size"), replaced=("replaced", "sum"),
        rate=("replaced", "mean"), mean_pitches=("pitches", "mean")).round(2).to_string())

    print("\n=== by how much the incumbent has thrown ===")
    d["work_band"] = pd.cut(d["pitches"], [0, 25, 50, 75, 999],
                            labels=["<=25", "26-50", "51-75", "76+"])
    print(d.groupby("work_band", observed=True).agg(
        n=("replaced", "size"), replaced=("replaced", "sum"),
        rate=("replaced", "mean"), mean_li=("li", "mean")).round(2).to_string())

    print("\n=== the two together (replacement rate) ===")
    pivot = d.pivot_table(index="work_band", columns="li_band", values="replaced",
                          aggfunc="mean", observed=True).round(2)
    counts = d.pivot_table(index="work_band", columns="li_band", values="replaced",
                           aggfunc="size", observed=True)
    print(pivot.to_string())
    print("\n  cell counts:")
    print(counts.to_string())

    print("\n=== starters vs relievers ===")
    print(d.groupby("is_starter").agg(
        n=("replaced", "size"), replaced=("replaced", "sum"), rate=("replaced", "mean"),
        mean_pitches=("pitches", "mean"), mean_li=("li", "mean")).round(2).to_string())

    # A lopsided game is low-leverage *and* where managers empty the bullpen,
    # so the two pull replacement rate in opposite directions and the raw
    # leverage bands come out U-shaped. Splitting them shows the low-leverage
    # spike is mop-up work rather than a leverage effect.
    print("\n=== blowouts vs competitive games ===")
    d["blowout"] = d["lead"].abs() >= 5
    print(d.groupby("blowout").agg(
        n=("replaced", "size"), replaced=("replaced", "sum"), rate=("replaced", "mean"),
        mean_li=("li", "mean"), mean_pitches=("pitches", "mean")).round(3).to_string())

    print("\n=== logistic model ===")
    labels = ["pitches (per 10)", "leverage index", "is starter"]

    def report(frame, title):
        xs = np.column_stack([frame["pitches"].to_numpy(float) / 10,
                              frame["li"].to_numpy(float),
                              frame["is_starter"].to_numpy(float)])
        beta, se, names = logistic(xs, frame["replaced"].to_numpy(float), labels)
        events = int(frame["replaced"].sum())
        print(f"\n  {title}: n={len(frame)}, events={events} "
              f"({events // len(labels)} per predictor)")
        print("  term                     coef      se    odds  95% CI on odds")
        for name, b, s in zip(names, beta, se):
            lo, hi = np.exp(b - 1.96 * s), np.exp(b + 1.96 * s)
            flag = "" if lo <= 1 <= hi else "  *"
            print(f"  {name:20s} {b:8.3f} {s:7.3f} {np.exp(b):7.2f}  [{lo:.2f}, {hi:.2f}]{flag}")

    report(d, "all decisions")
    report(d[d["lead"].abs() <= 3], "competitive games only (lead within 3)")
    print("\n  * = 95% CI excludes 1")


if __name__ == "__main__":
    main()
