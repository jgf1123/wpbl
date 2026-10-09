"""Each runner's smoothed steal-attempt and steal-success rates.

    pixi run python -m wpbl.steal_ratings

An OPPORTUNITY is a plate appearance that begins with a runner on first and
second open, or a runner on second and third open (`running_game.py`). An
ATTEMPT is a steal or caught-stealing play by that runner inside the plate
appearance. Rates are shrunk toward the league with a beta-binomial pseudo-count
K, estimated by method of moments from the runners themselves:

    rho = (Pearson chi-square - runners) / sum(n - 1),    K = 1 / rho - 1

    smoothed = (x + K * league) / (n + K)

which is the "about eleven opportunities" correction in stolen_base_post.md.
Attempt rate is per opportunity, both bases pooled; success rate is per attempt.
`attempt_scale` is smoothed attempt rate over the league's, the multiplier the
lineup model applies to the league's attempt rate for a given base and outs.
"""

from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from wpbl import tables

K_ATTEMPT, K_SUCCESS = 11.0, 7.3
STEALS = ("stolen_base", "caught_stealing")


def _base_of(narrative: str) -> str:
    text = str(narrative).lower()
    return "home" if "home" in text else "third" if "third" in text else "second"


@lru_cache(maxsize=1)
def events() -> tuple[pd.DataFrame, pd.DataFrame]:
    """(opportunities, steal attempts), one row each, runners by person_id."""
    plays = tables.read("plays", "training").sort_values(["game_id", "sequence"])
    players = tables.read("players", "training").drop_duplicates("person_id")
    pid = players.set_index("person_name")["person_id"]
    bat = tables.read("batting", "training").drop_duplicates("person_id")
    pid = pd.concat([pid, bat.set_index("person_name")["person_id"]])
    pid = pid[~pid.index.duplicated()]
    opps, atts = [], []
    for _, half in plays.groupby(["game_id", "inning", "half"], sort=False):
        group = []
        for play in half.itertuples():
            if play.outs_before >= 3:
                continue
            group.append(play)
            if not play.is_plate_appearance:
                continue
            head = group[0]
            f, s, t = (isinstance(x, str) for x in (head.first_base, head.second_base, head.third_base))
            steals = [p for p in group if p.event_type in STEALS]
            for base, runner, ok in (("second", head.first_base, f and not s),
                                     ("third", head.second_base, s and not t)):
                if not ok:
                    continue
                went = [p for p in steals if str(p.narrative).startswith(runner)
                        and _base_of(p.narrative) == base]
                opps.append(dict(game_id=play.game_id, runner=runner, base=base,
                                 outs=int(head.outs_before), attempt=bool(went)))
            group = []
        # A caught stealing that made the third out has no plate appearance after it.
        steals = [p for p in group if p.event_type in STEALS]
        if steals:
            head = group[0]
            base = _base_of(steals[0].narrative)
            runner = head.first_base if base == "second" else head.second_base
            opps.append(dict(game_id=head.game_id, runner=runner, base=base,
                             outs=int(head.outs_before), attempt=True))
    for play in plays[plays["event_type"].isin(STEALS)].itertuples():
        text = str(play.narrative)
        runner = next((n for n in (play.first_base, play.second_base, play.third_base)
                       if isinstance(n, str) and text.startswith(n)), None)
        atts.append(dict(game_id=play.game_id, runner=runner, base=_base_of(text),
                         outs=int(play.outs_before), safe=play.event_type == "stolen_base"))
    opps, atts = pd.DataFrame(opps), pd.DataFrame(atts)
    for frame in (opps, atts):
        frame["person_id"] = frame["runner"].map(pid)
    return opps, atts


def shrinkage(x: np.ndarray, n: np.ndarray, floor: float = 30) -> float:
    """Pseudo-count K by method of moments, over units with at least `floor` trials."""
    keep = n >= floor
    x, n = x[keep], n[keep]
    p = x.sum() / n.sum()
    chi = (((x - n * p) ** 2) / (n * p * (1 - p))).sum()
    rho = max((chi - len(x)) / (n - 1).sum(), 1e-6)
    return 1 / rho - 1


@lru_cache(maxsize=1)
def ratings() -> pd.DataFrame:
    opps, atts = events()
    att = (opps.groupby("person_id").agg(opps=("attempt", "size"), att=("attempt", "sum")))
    suc = (atts[atts["base"].isin(["second", "third"])].groupby("person_id")
           .agg(tries=("safe", "size"), safe=("safe", "sum")))
    table = att.join(suc, how="outer").fillna(0)
    # main() prints the method-of-moments estimates as a check; the ratings use the
    # pseudo-counts stolen_base_post.md states (about eleven opportunities for
    # attempts; 7.3 attempts for success, implied by an 11-for-11 runner landing
    # at 94%), because the success estimate swings from 4 to 14 with the cutoff.
    ka, ks = K_ATTEMPT, K_SUCCESS
    league_att = table["att"].sum() / table["opps"].sum()
    league_ok = table["safe"].sum() / table["tries"].sum()
    table["attempt_rate"] = (table["att"] + ka * league_att) / (table["opps"] + ka)
    table["success_rate"] = (table["safe"] + ks * league_ok) / (table["tries"] + ks)
    table["attempt_scale"] = table["attempt_rate"] / league_att
    table.attrs.update(ka=ka, ks=ks, league_att=league_att, league_ok=league_ok)
    return table


def league_attempt_rates() -> pd.DataFrame:
    """League attempts per opportunity, by base stolen and outs."""
    opps, _ = events()
    return opps.groupby(["base", "outs"])["attempt"].agg(["size", "sum", "mean"])


def main() -> None:
    pd.set_option("display.width", 200)
    opps, atts = events()
    r = ratings()
    names = tables.read("batting", "training").drop_duplicates("person_id").set_index("person_id")["person_name"]
    print(f"{len(opps)} opportunities, {int(opps['attempt'].sum())} attempts matched to them; "
          f"{len(atts)} steal plays ({int(atts['safe'].sum())} safe); "
          f"unmatched runner names {int(atts['person_id'].isna().sum())}")
    print(f"K attempt = {r.attrs['ka']:.1f} opportunities (post says ~11), "
          f"K success = {r.attrs['ks']:.1f} attempts")
    print(f"league attempt rate {r.attrs['league_att']:.3f}, success {r.attrs['league_ok']:.3f}")
    print("\nleague attempt rate by base stolen and outs\n", league_attempt_rates().round(3))
    r = r.assign(name=names.reindex(r.index).to_numpy()).sort_values("attempt_rate", ascending=False)
    print(r.head(12)[["name", "opps", "att", "attempt_rate", "tries", "safe", "success_rate"]].round(3))
    print(r[r["tries"] > 0].sort_values("success_rate").head(6)[
        ["name", "opps", "att", "attempt_rate", "tries", "safe", "success_rate"]].round(3))


if __name__ == "__main__":
    main()
