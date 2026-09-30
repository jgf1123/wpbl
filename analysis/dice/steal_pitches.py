"""Does a steal chance show up during the plate appearance, one pitch at a time?

    pixi run python analysis/dice/steal_pitches.py

Equal caught-stealing rates on second and third do not mean the two steals are
equally easy. Attempting third is rarer, and attempt rate moves opposite the
caught-stealing rate (steals.py), so the attempts we see are the ones a manager
already liked. One way to like them: the runner is waiting for a pitch she can
go on, and the question is whether such a pitch arrives during this at-bat.

The feed cannot say which pitch. A steal is its own play, filed ahead of the
plate appearance with an empty pitch string and a 0-0 count -- that count is
the start of the at-bat, not the count she ran on. Three further attempts are
written into the plate appearance narrative ("struck out; she stole second")
and name no pitch either. Nothing in the pitch log mentions a steal.

What it can say is how many pitches the plate appearance lasted. If each pitch
is an independent draw at rate q,

    P(attempt | n pitches) = 1 - (1 - q)^n

and the attempt rate rises with n. A manager who decides before the first pitch
has a rate that does not depend on n.

The base state is read from the first play of the plate appearance, before the
steal the feed files ahead of it. Reading the plate appearance row itself would
show the runner already on the next base and drop the opportunity she used
(running_game.py). Seven caught stealings with two outs ended the half-inning,
so that plate appearance was never completed and has no pitch count. They stay
out of the length comparison.

COUNT THE LIVE PITCHES, NOT THE PITCHES. A runner cannot go on a foul or a hit
batter -- the ball is dead and she is sent back -- nor on the pitch the batter
puts in play, which ends the at-bat. Only balls, called strikes and swinging
strikes give her an opening. Of the 740 chances to steal second with a full
pitch string, 378 fouls and 34 hit batters come out, and the live count tops
out at 6, since three balls and two strikes is the most that can be taken
before a pitch ends the plate appearance.

The answer, on that axis: she waits, but the case is weaker than counting every
pitch makes it look. Stealing second the attempt rate runs 0.000 (119 plate
appearances with no live pitch at all), 0.071, 0.179, 0.176, 0.195, 0.250,
0.238. A constant per-live-pitch rate q = 0.063 beats deciding up front by 5.7
log likelihood -- enough to prefer it, not enough to settle it. Counting every
pitch instead gives q = 0.041 and +17.2, and most of that advantage is the
one-pitch zero, which was never evidence: a plate appearance that ends on
contact offers no live pitch, so an attempt there was impossible rather than
merely unlikely. Keeping those structural zeros in the fit inflates it further,
to +25. The curve also misses the top of the table, where the observed rate
flattens and the model keeps climbing.

Within state and outs the longer half still runs hotter, 0.176 against 0.106 on
live pitches, +2.34 SE (on every pitch it was 0.193 against 0.097, +3.35 SE).

A two-component mixture -- a fraction who go at the first opportunity, the rest
at hazard q -- was fitted to test whether the flattening is two kinds of runner.
It lands at pi = 0.048 and buys +1.18 log likelihood for the extra parameter,
which is less than one degree of freedom is worth. Nor do early attempts convert
worse, as unchoosy runners should: with nobody or one out, where every attempt
is placeable, going within the first two live pitches succeeds 0.893 (28) against
0.870 (46) later, +0.30 SE. The test cannot see a penalty smaller than about 15
points, so this is a null, not an absence.

Stealing third has the same shape and about a quarter of the rate, q = 0.016
against 0.063, and the curve beats a flat rate by only 1.8 log likelihood on 21
attempts -- on live pitches the shape is not even monotone (0.009, 0.038, 0.091,
0.050), so read no curve into it. Success once she goes is 0.844 on second (109
attempts) against 0.870 on third (23). Third is not harder to convert. A pitch
worth going on comes up less often.

The 2-out caught stealings that end the half-inning have no pitch count at all
(the plate appearance never completes, so the feed logs no pitches for it), and
all seven are failures. That is 7 of the 19 failures in the sample, missing
non-randomly, which is why the early/late success test above is restricted to 0
and 1 out, where a caught stealing does not end the half and every attempt is
placeable.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables

pd.set_option("display.width", 200)
MIN_OPP, MIN_ATT = 40, 6          # a cell worth splitting in half, as steal_decision.py


def code(row) -> str:
    return "".join(c if isinstance(b, str) else "_" for c, b in
                   zip("123", (row.first_base, row.second_base, row.third_base)))


def attach(pl: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """One row per plate appearance, plus the attempts whose at-bat never finished.

    Plays up to and including a plate appearance share its id, so a steal filed
    ahead of the at-bat is part of the at-bat and the base state is the one she
    ran from.
    """
    frame = pl.sort_values(["game_id", "sequence"]).copy()
    frame = frame[frame.outs_before < 3].reset_index(drop=True)
    low = frame["narrative"].fillna("").str.lower()
    frame["attempt"] = low.str.contains("stole|caught stealing")
    frame["pickoff"] = frame["narrative"].fillna("").str.contains(r"\bp to\b", regex=True)
    half = ["game_id", "inning", "half"]
    frame["pa_group"] = (frame.groupby(half)["is_plate_appearance"]
                         .transform(lambda s: s.astype(int).cumsum().shift(fill_value=0)))

    rows, censored = [], []
    for key, g in frame.groupby(half + ["pa_group"], sort=False):
        first = g.iloc[0]
        state = code(first)
        steals = g[g.attempt]
        if not g["is_plate_appearance"].any():
            for r in steals.itertuples():
                to_second = state[0] == "1" and state[1] == "_"
                to_third = state[1] == "2" and state[2] == "_"
                censored.append({"state": state, "outs": int(first.outs_before),
                                 "target": "2nd" if to_second else ("3rd" if to_third else None),
                                 "pickoff": bool(r.pickoff), "narrative": r.narrative,
                                 "ok": "stole" in str(r.narrative).lower()})
            continue
        pa = g[g.is_plate_appearance].iloc[-1]
        to_second = state[0] == "1" and state[1] == "_"
        to_third = state[1] == "2" and state[2] == "_"
        # A runner can only go on a LIVE pitch. Balls (B), called strikes (K)
        # and swinging strikes (S) are live and leave the plate appearance
        # running. A foul (F) and a hit batter (H) kill the ball and send her
        # back, and the pitch put in play (P) ends the plate appearance. So a
        # one-pitch plate appearance offers nothing: it is contact or a hit
        # batter. Three balls and two strikes is the most that can be taken
        # without ending the at-bat, so the live count tops out at 6.
        seq = pa.pitch_sequence if isinstance(pa.pitch_sequence, str) else ""
        rows.append({
            "state": state,
            "outs": int(first.outs_before),
            "target": "2nd" if to_second else ("3rd" if to_third else None),
            "n": float(pa.n_pitches_est),
            "n_feed": int(pa.n_pitches),
            "estimated": bool(pa.n_pitches_estimated),
            "live": sum(seq.count(c) for c in "BKS"),
            "balls": seq.count("B"),
            "attempt": bool(len(steals)),
            "n_attempts": int(len(steals)),
            "pickoff": bool(steals["pickoff"].any()) if len(steals) else False,
            "ok": bool(steals["narrative"].str.contains("stole").any()) if len(steals) else False,
            "narrative": " | ".join(steals.narrative.astype(str)) if len(steals) else "",
        })
    return pd.DataFrame(rows), pd.DataFrame(censored)


def what_the_feed_records(pl: pd.DataFrame, pitches: pd.DataFrame) -> None:
    low = pl["narrative"].fillna("").str.lower()
    st = pl[low.str.contains("stole|caught stealing")]
    empty = int((st.pitch_sequence.fillna("") == "").sum())
    text = pitches["feed_description"].fillna("").str.lower()
    mentioned = int(text.str.contains("stole|stolen|stealing").sum())
    print("=== the feed does not name the pitch ===")
    print(f"  {len(st)} attempts, {empty} with an empty pitch string")
    print(f"  balls-strikes on those rows: "
          f"{int((st.balls.fillna(0) == 0).sum())} at 0 balls, "
          f"{int((st.strikes.fillna(0) == 0).sum())} at 0 strikes")
    print(f"  pitch-log descriptions mentioning a steal: {mentioned}")


def bins(d: pd.DataFrame, label: str) -> None:
    """Attempt rate by how long the plate appearance was."""
    x = d[d.n >= 1].copy()
    x["bin"] = x["n"].clip(upper=6).astype(int).astype(str)
    x.loc[x.n >= 6, "bin"] = "6+"
    g = x.groupby("bin").agg(opp=("attempt", "size"), att=("attempt", "sum"))
    g["rate"] = (g.att / g.opp).round(3)
    print(f"\n  {label}")
    print("  " + g.to_string().replace("\n", "\n  "))


def fit_q(n: np.ndarray, a: np.ndarray) -> float:
    """Per-pitch opportunity rate. P(attempt | n) = 1 - (1-q)^n."""
    grid = np.linspace(0.0005, 0.25, 2000)
    # log (1-q) * n is the log chance of never going; the attempt term is
    # log(1 - (1-q)^n). A flat decision is the special case reported beside it.
    survive = (1 - grid)[:, None] ** n[None, :]
    p = np.clip(1 - survive, 1e-12, 1 - 1e-12)
    ll = (a * np.log(p) + (1 - a) * np.log(1 - p)).sum(axis=1)
    return float(grid[int(np.argmax(ll))])


def model(d: pd.DataFrame, label: str, col: str = "n") -> None:
    """Fit the per-pitch rate on `col`: every pitch, or live pitches only.

    Plate appearances with none of the pitch in question stay out. On the live
    axis that is not a convenience: with no live pitch an attempt was
    impossible, so those rows are a structural zero and counting them inflates
    the curve's advantage over a flat rate (+25 rather than +6).
    """
    # A cut-off pitch string undercounts the live pitches it does not show, so
    # on that axis those plate appearances stay out, as in live_pitches().
    x = d[d[col] >= 1] if col == "n" else d[(d[col] >= 1) & ~d.estimated]
    n, a = x[col].to_numpy(float), x.attempt.to_numpy(float)
    if a.sum() < 5 or len(x) < 20:
        print(f"  {label}: too few attempts to fit")
        return
    q = fit_q(n, a)
    p_flat = float(a.mean())
    pred = 1 - (1 - q) ** n
    # Bernoulli log likelihood of the opportunity curve against a flat rate.
    def ll(p):
        p = np.clip(p, 1e-12, 1 - 1e-12)
        return float(np.sum(a * np.log(p) + (1 - a) * np.log(1 - p)))
    gain = ll(pred) - ll(np.full_like(a, p_flat))
    print(f"  {label}: q = {q:.4f} per pitch   flat rate {p_flat:.3f} over {len(x)} PA, "
          f"{int(a.sum())} attempts")
    print(f"    a {int(np.median(n))}-pitch PA attempts at {1 - (1 - q) ** np.median(n):.3f} "
          f"under the curve, {p_flat:.3f} if she decides up front")
    print(f"    log likelihood, curve minus flat: {gain:+.2f}")


def live_pitches(d: pd.DataFrame) -> None:
    """Live pitches: balls, called strikes and swinging strikes, the only ones a
    runner can go on. A foul or a hit batter kills the ball and sends her back,
    and the pitch put in play ends the at-bat."""
    # A cut-off pitch string undercounts them, so those plate appearances stay out.
    x = d[(d.n_feed >= 1) & ~d.estimated].copy()
    x["bin"] = x["live"].clip(upper=4).astype(int).astype(str)
    x.loc[x.live >= 4, "bin"] = "4+"
    print("\n=== live pitches only: no foul, no hit batter, no ball in play ===")
    print("  a one-pitch plate appearance has none of these: it ends on contact")
    for label, sub in (("stealing 2nd", x[x.target == "2nd"]),
                       ("stealing 3rd", x[x.target == "3rd"])):
        g = sub.groupby("bin").agg(opp=("attempt", "size"), att=("attempt", "sum"))
        g["rate"] = (g.att / g.opp).round(3)
        print(f"\n  {label}")
        print("  " + g.to_string().replace("\n", "\n  "))
    # Hold the length roughly fixed, so more live pitches is not just a longer
    # at-bat.
    deep = x[(x.target == "2nd") & (x.n >= 4)]
    few, many = deep[deep.live <= 1], deep[deep.live >= 3]
    print(f"\n  stealing 2nd, plate appearances of 4+ pitches "
          f"(length held roughly fixed):")
    print(f"    0-1 live {int(few.attempt.sum()):3d}/{len(few):3d} = {few.attempt.mean():.3f}")
    print(f"    3+  live {int(many.attempt.sum()):3d}/{len(many):3d} = {many.attempt.mean():.3f}")
    print(f"    The 0-1 cell is {len(few)} plate appearances, all contact and fouls, so the")
    print("    gap is the same fact as the one-pitch zero: she does not go on contact.")


def split(d: pd.DataFrame) -> None:
    """Attempt rate below vs above the median pitch count, within state and outs."""
    A = B = OA = OB = 0
    print("\n=== longer plate appearance, more attempts? within state AND outs ===")
    for (st, o), g in d[d.n >= 1].groupby(["state", "outs"]):
        att = int(g.attempt.sum())
        if len(g) < MIN_OPP or att < MIN_ATT:
            continue
        cut = g.n.median()
        lo, hi = g[g.n <= cut], g[g.n > cut]
        # a median can put everyone on one side when n is lumpy; skip it
        if not len(lo) or not len(hi):
            continue
        A += int(hi.attempt.sum()); OA += len(hi)
        B += int(lo.attempt.sum()); OB += len(lo)
        print(f"  {st} {o}out  n<={cut:.0f} {int(lo.attempt.sum()):3d}/{len(lo):3d} = "
              f"{lo.attempt.mean():.3f}    n>{cut:.0f} {int(hi.attempt.sum()):3d}/{len(hi):3d} = "
              f"{hi.attempt.mean():.3f}")
    if not OA or not OB:
        print("  no cell large enough")
        return
    ra, rb = A / OA, B / OB
    se = np.sqrt(ra * (1 - ra) / OA + rb * (1 - rb) / OB)
    print(f"  pooled     longer {A:3d}/{OA:3d} = {ra:.3f}    shorter {B:3d}/{OB:3d} = {rb:.3f}"
          f"    diff {ra - rb:+.3f} ({(ra - rb) / se:+.2f} SE)")


def main() -> None:
    pl = tables.read("plays", "training")
    pitches = tables.read("pitch_events", "training")
    what_the_feed_records(pl, pitches)

    pas, censored = attach(pl)
    elig = pas[pas.target.notna()].copy()
    found = int(pas.n_attempts.sum()) + len(censored)
    expected = int(pl.narrative.fillna("").str.lower().str.contains("stole|caught stealing").sum())
    # every attempt in the feed is either attached to the plate appearance it
    # interrupted or is one of the half-innings a caught stealing ended
    assert found == expected
    other = pas[(pas.n_attempts > 0) & pas.target.isna()]

    print("\n=== plate appearances that began with a base open ===")
    print(f"  {len(elig)} opportunities, {int(elig.attempt.sum())} attempts during a completed PA")
    print(f"  {int(elig.n_attempts.sum())} attempt-rows on those PAs "
          f"({int((elig.n_attempts > 1).sum())} PAs had two)")
    print(f"  pitch count was estimated (cut-off string) on {int(elig.estimated.sum())}")
    print(f"  {len(censored)} attempts ended the half on a caught stealing with 2 outs "
          f"and have no pitch count; {int(censored.pickoff.sum()) if len(censored) else 0} were pickoffs")
    print(f"  pickoffs among the completed-PA attempts: {int(elig.pickoff.sum())}")
    if len(other):
        print(f"  {int(other.n_attempts.sum())} attempt(s) with no base open ahead "
              f"(not in the rates below):")
        for narr in other.narrative:
            print(f"    {narr}")

    print("\n=== attempt rate by pitches in the plate appearance ===")
    bins(elig, "every open base")
    bins(elig[elig.target == "2nd"], "stealing 2nd")
    bins(elig[elig.target == "3rd"], "stealing 3rd")

    print("\n=== per-pitch rate against a decision made up front ===")
    print("  every pitch (overstates the case: a foul is not a chance to run)")
    model(elig, "every open base")
    model(elig[elig.target == "2nd"], "stealing 2nd")
    model(elig[elig.target == "3rd"], "stealing 3rd")
    print("\n  live pitches only -- this is the one the post quotes")
    model(elig, "every open base", "live")
    model(elig[elig.target == "2nd"], "stealing 2nd", "live")
    model(elig[elig.target == "3rd"], "stealing 3rd", "live")
    for st, g in elig.groupby("state"):
        model(g, f"state {st}")

    split(elig)
    live_pitches(elig)

    print("\n=== success, given she went ===")
    print("  includes the 2-out caught stealings that ended the half, which have")
    print("  no pitch count but are still outs")
    went = elig[elig.attempt][["target", "ok", "n"]]
    extra = censored.loc[censored.target.notna(), ["target", "ok"]].copy()
    extra["n"] = np.nan
    both = pd.concat([went, extra], ignore_index=True)
    for target, g in both.groupby("target"):
        print(f"  {target}: {g.ok.mean():.3f} on {len(g)} attempts")
    stayed = elig[~elig.attempt]
    print(f"  pitches when she did not go: {stayed.n.mean():.2f} "
          f"against {elig.loc[elig.attempt, 'n'].mean():.2f} when she did")


if __name__ == "__main__":
    main()
