"""Do runners and catchers differ for real, when the attempt is a CHOICE?

    pixi run python analysis/dice/steals.py

A steal is not dealt to a manager, it is chosen, and that breaks the usual test.
The rate we observe is P(safe | someone decided to try), and managers try when they
like the odds, so:

  a good catcher is only tested by runners confident enough to test her, which are
  the fast ones, so her observed caught-stealing rate reads LOW
  a weak catcher is tested by everybody, slow runners included, so hers reads HIGH

Selection would therefore COMPRESS both spreads toward the league mean, which would
make any surviving spread a floor rather than an estimate. **That mechanism is not
visible in this data** (matchup_selection.py). It needs runners to avoid the strong
arms, and the catchers with the best caught-stealing rates did not face better
runners: leave-one-out opposition quality runs 0.83 to 0.89 across all seven, and
correlates -0.47 with caught-stealing rate over seven points, which is noise. The
deterrence test is -1.1 SE. So read the spreads below as estimates, not floors.

Selection on whether to go AT ALL is real and does bias the level -- only a tenth
of chances become attempts -- which is why must_attempt.py cannot price a forced
steal. That is a different claim from compressing the spread between players.

Selection should leave a fingerprint the outcome rate cannot show: if managers pick
their spots they attempt LESS OFTEN against the catchers worth fearing, so the
attempt rate would carry the signal the success rate has had squeezed out of it.
**It does not survive being counted properly.** An earlier version of this file
charged each chance to the plate-appearance row, which shows the runner ALREADY
ADVANCED whenever she went, so it dropped the chance she had just used -- and
dropped it hardest for the catchers who get run on most, inflating exactly the rates
being compared. On that count the correlation between caught-stealing rate and
attempt rate was -0.66 and was read as deterrence. It was an artefact. Counted off
the chance itself (runner_chances) and asked as a signed question rather than a
correlation over seven points, the Benites odds ratio is 0.73 at -1.1 SE: the same
direction, not a finding (stolen_base_spec.md sections 2 and 5).

The same fingerprint on the runner side is the attempt rate per chance on base,
not the raw count of attempts. A chance is a plate appearance that began with
her on base and the next base open, read after a pinch runner has taken the
base. Counts pile up on whoever plays; the rate is what speed would move.
Stealing second, the 8 busiest runners have 48% of the attempts and 19% of the
chances. Among runners with 15 or more chances the attempt-rate spread is real
(SD 0.112, a null where everyone shares the league rate invents 0.055, p < 0.001).
Andreanne Leblanc is 0 for 32, Denae Benites 10 for 23. Equal rates are out.
Whether that is more pitches clearing a lower bar, or the manager sending them,
is the same number either way.

The null matters more than usual. Seven catchers and a dozen runners on 131
attempts will show a spread whatever is true, so the method-of-moments estimate is
compared against a simulated null in which every subject shares the league rate --
not against a bootstrap of the observed rates, which answers a different question
and flatters the result.

One more caution on the catcher: the caught-stealing spread is one player. Benites
caught 8 of 21; the other six caught 10 of 110. Take her out and the leftover is
nothing at all, which this file now prints rather than leaving to be discovered.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables

MIN_CATCHER = 5      # attempts faced
MIN_RUNNER = 4       # attempts made
MIN_BIN_CHANCES = 10  # chances on second before a runner can be binned
ATTEMPT_GOES_CUT = 0.19  # shrunk attempt rate that makes her "attempt_goes": a CHOICE
# The two ratings each have a default value, and both used to be called "league".
# They are prefixed by their dial so a bin name says which rating it belongs to:
#   attempt rate -> attempt_goes / attempt_league
#   success      -> success_low  / success_league
DRAWS = 20000
SEED = 20260925


def moments(k: np.ndarray, n: np.ndarray):
    """Real spread by method of moments: observed variance less the chance term."""
    p = k.sum() / n.sum()
    obs = np.average((k / n - p) ** 2, weights=n)
    exp = p * (1 - p) * len(n) / n.sum()
    return p, obs, exp, np.sqrt(max(obs - exp, 0.0))


def null_test(k: np.ndarray, n: np.ndarray, label: str, rng, unit: str = "attempts") -> float:
    """How large a 'real' spread does chance alone invent when everyone is equal?"""
    p, obs, exp, sd = moments(k, n)
    null = np.empty(DRAWS)
    for i in range(DRAWS):
        null[i] = moments(rng.binomial(n.astype(int), p).astype(float), n)[3]
    pval = float((null >= sd).mean())
    print(f"{label}: rate {p:.3f} over {n.sum():.0f} {unit}, {len(n)} subjects")
    print(f"   observed variance {obs:.4f}, chance term {exp:.4f} -> real SD {sd:.3f}")
    print(f"   null invents {np.percentile(null, 95):.3f} at the 95th percentile")
    print(f"   p = {pval:.3f} -> {'ESTABLISHED' if pval < 0.05 else 'not established'}")
    return pval


def attempts():
    """Every steal attempt, with the runner's name and whether she made it."""
    pl = tables.read("plays", "training")
    low = pl["narrative"].fillna("").str.lower()
    st = pl[low.str.contains("stole|caught stealing")].copy()
    st["ok"] = low[low.str.contains("stole|caught stealing")].str.contains("stole").to_numpy()
    st["runner"] = st["narrative"].str.extract(r"^([A-Z][^,]*?) (?:stole|out at)")[0]
    # Three of the caught-stealings were the PITCHER's, not the catcher's: the
    # narrative reads "p to ss" or "p to 1b". The feed labels a pickoff as a caught
    # stealing too, and the catcher's box score rightly does not take the credit.
    st["pickoff"] = st["narrative"].str.contains(r"\bp to\b", regex=True)
    return st


def mantel_haenszel(cells):
    """One odds ratio held common across strata, with the Robins-Greenland SE.

    cells: (a, b, c, d) per stratum -- a/b are the marked subject's yes/no, c/d
    everyone else's. Closed form, because a correlation over seven points cannot
    answer a signed question and this repo has no optimiser to spare.
    """
    R = S = 0.0
    vr = vrs = vs = 0.0
    for a, b, c, d in cells:
        n = a + b + c + d
        if n == 0:
            continue
        r, t = a * d / n, b * c / n
        P, Q = (a + d) / n, (b + c) / n
        R += r
        S += t
        vr += P * r
        vrs += P * t + Q * r
        vs += Q * t
    if R == 0 or S == 0:
        return float("nan"), float("nan")
    var = vr / (2 * R * R) + vrs / (2 * R * S) + vs / (2 * S * S)
    return R / S, np.sqrt(var)


def stratified_logit(rows, iters=200):
    """logit p = alpha_stratum + beta * marked, by Newton-Raphson. (beta, SE)."""
    strata = sorted({r[0] for r in rows})
    ix = {sname: i for i, sname in enumerate(strata)}
    k = len(strata)
    theta = np.zeros(k + 1)
    hess = np.eye(k + 1)
    for _ in range(iters):
        grad = np.zeros(k + 1)
        hess = np.zeros((k + 1, k + 1))
        for sname, x, hits, n in rows:
            i = ix[sname]
            eta = theta[i] + theta[k] * x
            p = 1.0 / (1.0 + np.exp(-eta))
            w = n * p * (1 - p)
            resid = hits - n * p
            grad[i] += resid
            grad[k] += resid * x
            hess[i, i] += w
            hess[i, k] += w * x
            hess[k, i] += w * x
            hess[k, k] += w * x * x
        hess += 1e-9 * np.eye(k + 1)
        step = np.linalg.solve(hess, grad)
        theta += step
        if np.max(np.abs(step)) < 1e-11:
            break
    cov = np.linalg.inv(hess)
    return theta[k], float(np.sqrt(cov[k, k]))


def chance_bins(d, cut=ATTEMPT_GOES_CUT):
    """Which runners go, from their own shrunk attempt rate -- not a name list.

    The ghost count is m = p(1-p)/tau^2 with tau the method-of-moments leftover,
    so a runner keeps her own rate in proportion to how many chances she had.
    The cut is a choice (stolen_base_spec.md section 4) and the bins are derived
    here every run, because the spec is explicit that they are not frozen.
    """
    sub = d[d.target == "2nd"]
    g = sub.groupby("runner").agg(opp=("att", "size"), att=("att", "sum"))
    g = g[g.opp >= MIN_BIN_CHANCES]
    p, _obs, _exp, tau = moments(g.att.to_numpy(float), g.opp.to_numpy(float))
    m = p * (1 - p) / tau ** 2 if tau > 0 else np.inf
    g["shrunk"] = (g.att + m * p) / (g.opp + m)
    goes = set(g.index[g.shrunk >= cut])
    return goes, m, p, tau


def catchers(rng):
    """The catcher, on the two questions that need different denominators."""
    f = tables.read("fielding", "training")
    cat = f[f["position"].astype(str).str.lower() == "c"]
    g = cat.groupby("person_name").agg(sba=("sba", "sum"), csb=("csb", "sum")).reset_index()
    g["att"] = g.sba + g.csb
    g = g[g.att >= MIN_CATCHER].sort_values("att", ascending=False)
    g["CS%"] = (100 * g.csb / g.att).round(1)

    print("=== catcher, once the attempt has already been chosen ===")
    print("  This denominator is sound: the runner decided to go, and the question")
    print("  is only whether she made it.")
    print(g[["person_name", "att", "csb", "CS%"]].to_string(index=False))
    print()
    null_test(g.csb.to_numpy(float), g.att.to_numpy(float), "CAUGHT STEALING", rng)

    top = g.loc[g["CS%"].idxmax()]
    rest = g[g.person_name != top.person_name]
    print(f"\n   and it is one player. {top.person_name} caught "
          f"{int(top.csb)}/{int(top.att)} = {top.csb / top.att:.3f}; the other "
          f"{len(rest)} caught {int(rest.csb.sum())}/{int(rest.att.sum())} = "
          f"{rest.csb.sum() / rest.att.sum():.3f}.")
    _, _, _, sd_rest = moments(rest.csb.to_numpy(float), rest.att.to_numpy(float))
    print(f"   With her removed the leftover real SD is {sd_rest:.3f}.")
    print("   Her 0.381 is a floor either way: a good arm is only tested by runners")
    print("   willing to go.")
    return g, top.person_name


def deterrence(marked, rng):
    """Are the good catchers run on less often? Counted off the chance itself.

    The chance has to be read before the steal the feed files ahead of the plate
    appearance, or every attempt silently deletes its own opportunity.
    """
    pl = tables.read("plays", "training")
    d = runner_chances(pl)
    goes, m, p, tau = chance_bins(d)
    print("\n\n=== is the catcher run on less often? ===")
    print(f"  chance bins derived here: ghost count m = {m:.1f} chances "
          f"(league {p:.3f}, tau {tau:.3f}), cut at {ATTEMPT_GOES_CUT}")
    print(f"  {len(goes)} runners land in 'attempt_goes'")

    f = tables.read("fielding", "training")
    cat = f[f["position"].astype(str).str.lower() == "c"]
    who = (cat.sort_values("sba", ascending=False)
              .drop_duplicates(["game_id", "team_id"])
              .set_index(["game_id", "team_id"])["person_name"].to_dict())
    d["catcher"] = [who.get((gid, t)) for gid, t in zip(d.game_id, d.fielding)]
    missing = int(d.catcher.isna().sum())
    d = d.dropna(subset=["catcher"])
    d["bin"] = np.where(d.runner.isin(goes), "attempt_goes", "attempt_league")
    d["marked"] = d.catcher == marked
    rated = d[d.runner.isin(
        d[d.target == "2nd"].groupby("runner").size().pipe(
            lambda s: s[s >= MIN_BIN_CHANCES]).index)]
    print(f"  {len(d)} chances with a catcher matched ({missing} dropped), "
          f"{len(rated)} of them to a rated runner")

    print("\n  attempt rate, raw:")
    print("  base bin     marked            else              stratum")
    cells, rows = [], []
    for target in ("2nd", "3rd"):
        for b in ("attempt_goes", "attempt_league"):
            sub = rated[(rated.target == target) & (rated["bin"] == b)]
            mk, ot = sub[sub.marked], sub[~sub.marked]
            a, na = int(mk.att.sum()), len(mk)
            c, nc = int(ot.att.sum()), len(ot)
            if na == 0 or nc == 0:
                continue
            cells.append((a, na - a, c, nc - c))
            rows.append((f"{target}/{b}", 1, a, na))
            rows.append((f"{target}/{b}", 0, c, nc))
            print(f"  {target}  {b:5s}  {a:3d}/{na:3d} = {a / na:.3f}   "
                  f"{c:3d}/{nc:3d} = {c / nc:.3f}   "
                  f"{a + c:3d}/{na + nc:3d} = {(a + c) / (na + nc):.3f}")

    orr, se = mantel_haenszel(cells)
    print(f"\n  Mantel-Haenszel odds ratio {orr:.2f}, 95% "
          f"{np.exp(np.log(orr) - 1.96 * se):.2f} to {np.exp(np.log(orr) + 1.96 * se):.2f} "
          f"({np.log(orr) / se:+.2f} SE on the log scale)")
    beta, bse = stratified_logit(rows)
    print(f"  stratified logit beta {beta:+.3f} (SE {bse:.3f}) = {beta / bse:+.2f} SE, "
          f"odds ratio {np.exp(beta):.2f}")
    print("  NOT ESTABLISHED. The direction is the one deterrence predicts, and the")
    print("  size is what a floor would look like, but it does not clear its own noise.")
    print("  The -0.66 correlation this file used to print came from charging the")
    print("  chance to the plate-appearance row; see the module docstring.")


def runners(rng):
    st = attempts()
    rr = (st.dropna(subset=["runner"]).groupby("runner")
            .agg(att=("ok", "size"), ok=("ok", "sum")))
    rr = rr[rr.att >= MIN_RUNNER].sort_values("att", ascending=False)
    rr["SB%"] = (100 * rr.ok / rr.att).round(1)
    print("\n\n=== runners ===")
    print(rr.to_string())
    print()
    null_test(rr.ok.to_numpy(float), rr.att.to_numpy(float), "STEAL SUCCESS", rng)
    return rr


MIN_CHANCES = 15     # times on base with the next base open, enough to rate her


def runner_chances(pl: pd.DataFrame) -> pd.DataFrame:
    """One row per plate appearance that began with a base open.

    The runner is whoever was standing on the base she could take, read before
    the steal the feed files ahead of the plate appearance. Charging the
    opportunity off the plate-appearance row itself would show her already
    there and drop the chance she used.
    """
    frame = pl.sort_values(["game_id", "sequence"]).copy()
    frame = frame[frame.outs_before < 3].reset_index(drop=True)
    low = frame["narrative"].fillna("").str.lower()
    frame["went"] = low.str.contains("stole|caught stealing")
    half = ["game_id", "inning", "half"]
    frame["pa_group"] = (frame.groupby(half)["is_plate_appearance"]
                         .transform(lambda s: s.astype(int).cumsum().shift(fill_value=0)))
    rows = []
    for _, g in frame.groupby(half + ["pa_group"], sort=False):
        steals = g[g.went]
        # A pinch runner takes the base between the previous plate appearance
        # and this one, and the substitution row still names the player she
        # replaced. The steal row, or the plate appearance if she stayed, has
        # the runner who was actually standing there.
        if len(steals):
            src = steals.iloc[0]
        elif g["is_plate_appearance"].any():
            src = g[g.is_plate_appearance].iloc[-1]
        else:
            continue
        on1 = isinstance(src.first_base, str)
        on2 = isinstance(src.second_base, str)
        on3 = isinstance(src.third_base, str)
        if on1 and not on2:
            runner, target = src.first_base, "2nd"
        elif on2 and not on3:
            runner, target = src.second_base, "3rd"
        else:
            continue
        text = " | ".join(steals.narrative.astype(str)) if len(steals) else ""
        rows.append({"game_id": src.game_id, "fielding": src.pitching_team_id,
                     "outs": int(src.outs_before), "runner": runner, "target": target,
                     "att": int(f"{runner} stole" in text or f"{runner} out at" in text),
                     "ok": int(f"{runner} stole" in text),
                     "narrative": text})
    return pd.DataFrame(rows)


def runner_rates(rng) -> None:
    """Do some runners go more often, or do they just reach base more often?"""
    d = runner_chances(tables.read("plays", "training"))
    went = d[d.att == 1]
    orphan = d[(d.narrative != "") & (d.att == 0)]
    print("\n\n=== who attempts, per chance on base ===")
    print(f"  {len(went)} attempts credited to the runner on the base")
    if len(orphan):
        print(f"  {len(orphan)} steal narratives not credited to her:")
        print(orphan[["target", "runner", "narrative"]].to_string(index=False))
    print("  A chance is a plate appearance that began with her on base and the")
    print("  next base open. Counts concentrate wherever the playing time is;")
    print("  the rate is the thing runner speed would move.")
    for target, label in (("2nd", "STEALING 2ND"), ("3rd", "STEALING 3RD")):
        sub = d[d.target == target]
        g = (sub.groupby("runner")
                .agg(opp=("att", "size"), att=("att", "sum"), ok=("ok", "sum"))
                .reset_index())
        print(f"\n  {label}: {int(g.att.sum())} attempts in {int(g.opp.sum())} chances, "
              f"{len(g)} runners")
        top = g.sort_values("att", ascending=False).head(8).copy()
        top["rate"] = (top.att / top.opp).round(3)
        share_a = top.att.sum() / g.att.sum()
        share_o = top.opp.sum() / g.opp.sum()
        print(top[["runner", "opp", "att", "rate"]].to_string(index=False))
        print(f"  those 8: {share_a:.0%} of attempts, {share_o:.0%} of chances")
        rated = g[g.opp >= MIN_CHANCES].copy()
        rated["rate"] = (rated.att / rated.opp).round(3)
        rated["SB%"] = np.where(rated.att > 0, (100 * rated.ok / rated.att).round(1), np.nan)
        show = rated.sort_values(["att", "opp"], ascending=False)
        print(show.to_string(index=False))
        print()
        null_test(rated.att.to_numpy(float), rated.opp.to_numpy(float),
                  f"ATTEMPT RATE, {label}, {MIN_CHANCES}+ chances", rng, unit="chances")
        both = rated[rated.att >= MIN_RUNNER]
        if len(both) >= 5:
            r = float(np.corrcoef(both.att / both.opp, both.ok / both.att)[0, 1])
            print(f"   corr(attempt rate, success rate) = {r:+.2f} over {len(both)} runners "
                  f"with {MIN_RUNNER}+ attempts")


def thirds():
    """Who actually retired the runner, and why the counts do not line up."""
    st = attempts()
    f = tables.read("fielding", "training")
    cat = f[f["position"].astype(str).str.lower() == "c"]
    print("\n\n=== three contributors, not two ===")
    print(f"   attempts in the play-by-play      {len(st)}")
    print(f"   of which caught                   {(~st.ok).sum()}")
    print(f"   ... by the pitcher (a pickoff)    {int((~st.ok & st.pickoff).sum())}")
    print(f"   ... by the catcher                {int((~st.ok & ~st.pickoff).sum())}")
    print(f"   catcher box score csb / sba       {cat.csb.sum():.0f} / {cat.sba.sum():.0f}")
    print("   The pitcher's hold is a third factor the game does not model at all.")


def main():
    rng = np.random.default_rng(SEED)
    _, marked = catchers(rng)
    deterrence(marked, rng)
    runners(rng)
    runner_rates(rng)
    thirds()


if __name__ == "__main__":
    main()
