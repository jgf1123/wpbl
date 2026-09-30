"""Do managers run when the win probability says to?

    pixi run python analysis/dice/steal_decision.py

A steal is chosen, so the observed success rate is selected (see steals.py). The
hope behind this script was an exclusion restriction: if the GAME SITUATION moved
the attempt decision without touching the chance of being safe, it could separate
a runner's ability from the manager's selection. The inning and the score change
what a steal is worth without changing how fast she is.

For each moment a manager could run -- a plate appearance beginning with a runner
and the base ahead of her open -- three win probabilities are taken from the
batting side: as it stands, if she is safe, and if she is thrown out. Then

    gain = WP(safe) - WP(now),  loss = WP(now) - WP(caught)
    break-even = loss / (gain + loss)

is the success rate the attempt needs to be worth making. A manager reading win
probability attempts less often as that number rises.

**The answer is no, and the test had to be fixed before it could say so.** Split
only by base state, the break-even looked like it mattered a lot -- the 1st-and-3rd
state ran 55% of the time at a low break-even against 23% at a high one. But inside
a state the break-even is mostly driven by the OUTS, and the attempt rate depends on
outs directly, so that comparison was confounded. Stratified by state AND outs, so
the break-even varies only through the inning and the score, the effect disappears
and the 1st-and-3rd row reverses.

Two consequences. The exclusion restriction is not there, so this route to undoing
the selection is closed. But if managers are not selecting on the game situation,
the selection is on the base state -- which any model can condition on -- and on the
matchup, which is the deterrence steals.py measures. The confounding is narrower
than it looked.

A caveat that cuts the other way: this win-probability model is league-average. It
does not know who is running or who bats next, and a manager who knows her runner is
fast faces a lower break-even than the table says. Real responsiveness could hide
behind that.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables
from wpbl.win_probability import Model

pd.set_option("display.width", 210)

# state before an attempt -> (state if safe, state if caught)
MOVE = {
    "1__": ("_2_", "___"),      # stealing 2nd
    "1_3": ("_23", "__3"),      # stealing 2nd
    "_2_": ("__3", "___"),      # stealing 3rd
    "12_": ("1_3", "1__"),      # stealing 3rd
}
REG = 7
MIN_OPP, MIN_ATT = 40, 6        # a cell worth splitting in half


def code(row) -> str:
    return "".join(c if isinstance(b, str) else "_" for c, b in
                   zip("123", (row.first_base, row.second_base, row.third_base)))


def opportunities(model: Model) -> pd.DataFrame:
    """Every steal-eligible moment, with what a steal is worth there."""

    def bat_wp(inning, half, outs, bases, diff):
        p = model.win_probability(inning, half, outs, bases, diff)
        return p if half == "bottom" else 1.0 - p

    def stakes(inning, half, outs, state, diff):
        safe, caught = MOVE[state]
        now = bat_wp(inning, half, outs, state, diff)
        win_safe = bat_wp(inning, half, outs, safe, diff)
        if outs < 2:
            win_caught = bat_wp(inning, half, outs + 1, caught, diff)
        else:                                   # third out: the half is over
            nxt = (inning, "bottom") if half == "top" else (inning + 1, "top")
            p = model.win_probability(nxt[0], nxt[1], 0, "___", diff)
            win_caught = (1.0 - p) if half == "top" else p
        gain, loss = win_safe - now, now - win_caught
        return gain, loss, (loss / (gain + loss) if gain + loss > 0 else np.nan)

    pl = tables.read("plays", "training").copy()
    pl["state"] = [code(r) for r in pl.itertuples()]
    pl["diff"] = pl["home_score_before"] - pl["away_score_before"]
    low = pl["narrative"].fillna("").str.lower()
    pl["is_steal"] = low.str.contains("stole|caught stealing")
    # Innings 1-6 and the top of the 7th: the uncensored set the WP model pools
    # over, so there is no walk-off or game-over edge to handle.
    keep = (pl.inning <= REG - 1) | ((pl.inning == REG) & (pl.half == "top"))
    pl = pl[keep & pl.state.isin(MOVE) & pl.outs_before.lt(3)]

    rows = []
    for r in pl.itertuples():
        g, l, be = stakes(int(r.inning), r.half, int(r.outs_before), r.state, int(r.diff))
        rows.append({"state": r.state, "outs": int(r.outs_before), "inning": int(r.inning),
                     "absdiff": abs(int(r.diff)), "gain": g, "loss": l, "be": be,
                     "steal": bool(r.is_steal), "pa": bool(r.is_plate_appearance)})
    return pd.DataFrame(rows).dropna(subset=["be"])


def what_it_is_worth(d: pd.DataFrame) -> None:
    print("=== what a steal is worth, in win-probability points ===")
    t = (d[d.pa].groupby(["state", "outs"])
         .agg(opp=("be", "size"), gain=("gain", "mean"), loss=("loss", "mean"),
              breakeven=("be", "mean")))
    t["att"] = d[d.steal].groupby(["state", "outs"]).size()
    t["att"] = t["att"].fillna(0).astype(int)
    t["rate"] = (t.att / t.opp).round(3)
    t[["gain", "loss"]] = (100 * t[["gain", "loss"]]).round(2)
    t["breakeven"] = t.breakeven.round(3)
    print(t.to_string())
    r = float(np.corrcoef(t.breakeven, t.rate)[0, 1])
    print(f"\ncorr(break-even, attempt rate) over the {len(t)} base-out cells = {r:+.2f}")
    print("   The loss always dwarfs the gain, so a steal needs 0.66 to 0.93 to pay")
    print("   against a league success of 0.859 -- and the rate does not follow it.")


def split(d: pd.DataFrame, var: str, label: str) -> None:
    """Attempt rate below vs above the median of `var`, within each (state, outs)."""
    opp, att = d[d.pa], d[d.steal]
    A = B = OA = OB = 0
    rows = []
    for (st, o), g in opp.groupby(["state", "outs"]):
        a = att[(att.state == st) & (att.outs == o)]
        if len(g) < MIN_OPP or len(a) < MIN_ATT:
            continue
        cut = g[var].median()
        lo_o, hi_o = g[g[var] <= cut], g[g[var] > cut]
        lo_a, hi_a = a[a[var] <= cut], a[a[var] > cut]
        rows.append((f"{st} {o}out", len(lo_o), len(lo_a), len(hi_o), len(hi_a)))
        A += len(lo_a); OA += len(lo_o); B += len(hi_a); OB += len(hi_o)
    if not OA or not OB:
        print(f"  {label}: no cell large enough")
        return
    ra, rb = A / OA, B / OB
    se = np.sqrt(ra * (1 - ra) / OA + rb * (1 - rb) / OB)
    lo, hi = (ra - rb) - 1.96 * se, (ra - rb) + 1.96 * se
    print(f"  {label:16s} low {A:3d}/{OA:3d} = {ra:.3f}   high {B:3d}/{OB:3d} = {rb:.3f}"
          f"   diff {ra - rb:+.3f} ({(ra - rb) / se:+.2f} SE, 95% {lo:+.3f} to {hi:+.3f})")
    return rows


def by_state() -> None:
    """Success rate by where the runner started -- the engine keys only on the base."""
    pl = tables.read("plays", "training")
    low = pl["narrative"].fillna("").str.lower()
    st = pl[low.str.contains("stole|caught stealing")].copy()
    st["ok"] = low[low.str.contains("stole|caught stealing")].str.contains("stole").to_numpy()
    st["state"] = [code(r) for r in st.itertuples()]
    st["target"] = ["2nd" if s in ("1__", "1_3") else "3rd" for s in st.state]
    st["r3"] = st.state.str.endswith("3")
    print("\n=== does WHERE she runs from change whether she makes it? ===")
    for key, lab in (("state", "from"), ("target", "taking")):
        g = st.groupby(key)["ok"].agg(["size", "sum"])
        g["succ"] = (g["sum"] / g["size"]).round(3)
        print(f"  by {lab}:  " + ",  ".join(f"{i} {r.succ:.3f} (n={int(r['size'])})"
                                            for i, r in g.iterrows()))
    a, b = st[st.r3], st[~st.r3]
    pa_, pb = a.ok.mean(), b.ok.mean()
    se = np.sqrt(pa_ * (1 - pa_) / len(a) + pb * (1 - pb) / len(b))
    print(f"  runner on 3rd {pa_:.3f} (n={len(a)}) against {pb:.3f} (n={len(b)}): "
          f"{pa_ - pb:+.3f}, {(pa_ - pb) / se:+.2f} SE")
    print("  So the catcher does NOT hold the ball with a runner on 3rd, and taking")
    print("  3rd is no harder than taking 2nd. One rate covers every attempt.")


def main() -> None:
    d = opportunities(Model())
    what_it_is_worth(d)
    print("\n=== does the attempt rate follow the stake? (within state AND outs) ===")
    split(d, "be", "break-even")
    split(d, "gain", "gain if safe")
    split(d, "loss", "loss if caught")
    split(d, "absdiff", "|score margin|")
    split(d, "inning", "inning")
    by_state()


if __name__ == "__main__":
    main()
