"""How much each team's top 10 depends on the design choices in top_players.py.

    pixi run python analysis/top_players/sensitivity.py

The real season (no resampling), one choice changed at a time against the
baseline. For each variant: who enters and leaves each team's top 10, and how
many of the ten are pitchers (regular arms) vs batters. Written 8 Nov to follow
the game-resampling run, which held these choices fixed.
"""
import numpy as np
import pandas as pd

from wpbl import top_players as T

BASE = dict(TOP_PITCHERS=6, TOP_PA=None, X_SPREAD=0.025, MIN_OUTINGS=2,
            K_BAT=50.0, K_PK=77.0, K_PFP=69.0, SMOOTH_PRIOR=True)
VARIANTS = [
    ("two-group pitcher prior", dict(SMOOTH_PRIOR=False), None),
    ("smooth prior, k refit (FP 133)", dict(K_PFP=133.0, K_PK=74.0), None),
    ("pitcher cut top 5", dict(TOP_PITCHERS=5), None),
    ("pitcher cut top 7", dict(TOP_PITCHERS=7), None),
    ("season PA top-4 batters (old rule)", dict(TOP_PA=4), None),
    ("season PA top 3", dict(TOP_PA=3), None),
    ("season PA top 6", dict(TOP_PA=6), None),
    ("no shrinkage", dict(K_BAT=0.0, K_PK=0.0, K_PFP=0.0), None),
    ("shrinkage x0.5", dict(K_BAT=25.0, K_PK=38.5, K_PFP=34.5), None),
    ("shrinkage x2", dict(K_BAT=100.0, K_PK=154.0, K_PFP=138.0), None),
    ("pitchers per BF", {}, "per_bf"),
    ("single batter cut", dict(X_SPREAD=0.0), None),
    ("one-outing rule off", dict(MIN_OUTINGS=1), None),
]


def combine(b: np.ndarray, p: np.ndarray) -> np.ndarray:
    both = ~np.isnan(b) & ~np.isnan(p)
    pos = np.where(b > 0, b, 0) + np.where(p > 0, p, 0)
    return np.where(both, np.where((b > 0) | (p > 0), pos, np.fmax(b, p)),
                    np.where(np.isnan(b), p, b))


def run(D, w, settings, mode):
    for k, v in {**BASE, **settings}.items():
        setattr(T, k, v)
    out, info = T.evaluate(D, w)
    if mode == "per_bf":
        out["pitching"] = out["per_bf_runs"]
        out["runs"] = combine(out.batting.to_numpy(), out.pitching.to_numpy())
    out = out.dropna(subset=["runs"])
    out["rk"] = out.groupby("team")["runs"].rank(ascending=False, method="first")
    return out, info


def main():
    pd.set_option("display.width", 220)
    D = T.load()
    w = pd.Series(1.0, index=D["strata"].index)
    base, binfo = run(D, w, {}, None)
    btop = set(base.index[base.rk <= T.TOP_N])
    print(f"baseline: X {binfo['X']:.1%}, PA {binfo['PA']:.1f}; top-10 sums "
          + ", ".join(f"{t} {g[g.rk <= 10].runs.sum():+.1f}" for t, g in base.groupby("team")))

    counts = pd.Series(0, index=base.index)
    rows = []
    for label, settings, mode in VARIANTS:
        out, info = run(D, w, settings, mode)
        top = set(out.index[out.rk <= T.TOP_N])
        for pid in top:
            counts[pid] = counts.get(pid, 0) + 1
        ins, outs = top - btop, btop - top
        n_p = {t: int(g[(g.rk <= 10) & g.regular_p].shape[0]) for t, g in out.groupby("team")}
        rows.append(dict(variant=label, X=f"{info['X']:.1%}", PA=f"{info['PA']:.1f}",
                         changes=len(ins), pitchers_in_top10=n_p))
        print(f"\n--- {label}: X {info['X']:.1%}, PA {info['PA']:.1f}, "
              f"{len(ins)} of 40 places change; regular pitchers in top 10 {n_p}")
        for t in sorted(base.team.unique()):
            i = [f"+{out.at[p, 'name']} ({out.at[p, 'runs']:+.1f}, was #{int(base.at[p, 'rk']) if p in base.index else '-'})"
                 for p in ins if out.at[p, "team"] == t]
            o = [f"-{base.at[p, 'name']} ({base.at[p, 'runs']:+.1f}, now #{int(out.at[p, 'rk']) if p in out.index else '-'})"
                 for p in outs if base.at[p, "team"] == t]
            if i or o:
                print(f"  {t}: " + "; ".join(i + o))
    for k, v in BASE.items():
        setattr(T, k, v)

    n = len(VARIANTS)
    base["in_variants"] = counts.reindex(base.index).fillna(0).astype(int)
    print(f"\n=== top-10 membership across {n} variants (baseline top 10 marked *) ===")
    for t, g in base.groupby("team"):
        g = g[(g.rk <= 10) | (g.in_variants > 0)].sort_values("runs", ascending=False)
        print(f"\n{t}")
        print("  robust (all variants): " + ", ".join(g[g.in_variants == n].name))
        mixed = g[(g.in_variants > 0) & (g.in_variants < n)]
        print("  choice-dependent: " + ", ".join(
            f"{r.name}{'*' if r.rk <= 10 else ''} {r.in_variants}/{n}" for r in mixed.itertuples()))
    boot = T.OUT_DIR.parent / "top_players_boot.csv"
    if boot.exists():
        b = pd.read_csv(boot, index_col=0)
        base = base.join(b[["p_top10"]])
        print("\n=== the two kinds of uncertainty together, contested players ===")
        c = base[((base.in_variants > 0) & (base.in_variants < n)) | base.p_top10.between(0.1, 0.9)]
        print(c.sort_values(["team", "runs"], ascending=[True, False])[
            ["name", "team", "runs", "rk", "in_variants", "p_top10"]].round(2).to_string(index=False))


if __name__ == "__main__":
    main()
