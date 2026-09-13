"""Win probability from a base-out state, score differential, and point in the game.

    pixi run wp

The idea that makes this work on 24 games: the base-out state only affects the
half-inning in progress. Every later half-inning starts bases-empty, nobody out,
and is drawn from one distribution estimated on 288 half-innings. So the thinly
sampled 24-cell part contributes at most one inning of variance, and the rest of
the game is carried by the well-estimated piece. Accumulating over the remaining
half-innings averages the noise down rather than compounding it.

Assumptions, all of them the ones asked for:

* Both teams draw from the same league-wide run distributions -- no team
  strength, no platoon, no park. Model.matchup lifts the first of those by
  letting each side bat from its own distributions; team_strength.py fits
  them.
* Half-innings are independent and identically distributed, pooled over every
  uncensored half-inning: innings 1-6 plus the top of the 7th. Only the bottom
  of the 7th is left out, being both truncated by walk-offs and conditioned on
  the home team not already leading.
* No park or travel term. Every game is played in the same stadium, so the only
  home advantage in the model is batting last, which is a rule rather than a
  venue.
* Regulation is seven innings. The home team does not bat in the bottom of the
  7th when already ahead, and stops as soon as it leads.

Under those assumptions a tie entering extra innings is exactly 50/50: both
sides draw the same distribution, so the sign of the difference is symmetric,
and the home team's ability to stop early cannot change who finishes ahead.
That closes the recursion without modelling the tiebreaker inning at all.
Once the two sides bat from different distributions the tie is no longer
50/50, and its value is solved for instead (Model._tie_value).
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import pandas as pd

from wpbl.run_expectancy import pool, states

REGULATION = 7
MAX_RUNS = 12          # per half-inning; the observed maximum is 7
MAX_DIFF = 25          # differential range the grid covers
SHRINK = 25            # pseudo-observations pulling a thin cell toward its group


def uncensored_halves() -> pd.DataFrame:
    """Runs in every complete, uncensored half-inning, and who batted and fielded.

    Innings 1-6 plus the top of the 7th. The top of the 7th is always played and
    never cut short, so it is a clean observation. The bottom of the 7th is the
    only half-inning that is both censored -- the home team stops the moment it
    leads -- and selected, since it happens only when the home team is not ahead.
    Including it would bias the distribution downwards.
    """
    plays = pd.read_parquet("data/tables/plays.parquet")
    games = pd.read_parquet("data/tables/games.parquet").set_index("game_id")
    key = ["game_id", "batting_team_id", "inning", "half"]
    clean = plays[(plays["inning"] <= 6)
                  | ((plays["inning"] == REGULATION) & (plays["half"] == "top"))]
    halves = clean.groupby(key)["runs_scored"].sum().rename("runs").reset_index()
    # The fielding side is taken from the game rather than the play rows, so a
    # play row with a blank pitching team cannot split or drop a half-inning.
    home = halves["game_id"].map(games["home_team_id"])
    away = halves["game_id"].map(games["away_team_id"])
    halves["fielding_team_id"] = home.where(halves["batting_team_id"] == away, away)
    return halves


def half_inning_pmf() -> np.ndarray:
    """Runs in a complete, uncensored half-inning; see uncensored_halves."""
    return _pmf(uncensored_halves()["runs"].values)


def _pmf(values) -> np.ndarray:
    pmf = np.zeros(MAX_RUNS + 1)
    for v in values:
        pmf[min(int(v), MAX_RUNS)] += 1
    return pmf / pmf.sum()


def tilt(pmf: np.ndarray, t: float) -> np.ndarray:
    """Exponentially tilt a run distribution: p(r) -> p(r) e^(t r), renormalised.

    t > 0 moves mass toward big innings, t < 0 toward empty ones, t = 0 leaves
    it alone. It keeps the league's shape -- the pile-up on zero, the long tail
    -- and moves only where it sits, which is about all a team's 97 half-innings
    can support.
    """
    if t == 0:
        return pmf
    weights = pmf * np.exp(t * np.arange(len(pmf)))
    return weights / weights.sum()


@dataclass(frozen=True, eq=False)
class Batting:
    """The run distributions one side bats from."""
    full: np.ndarray      # a whole half-inning from bases empty, nobody out
    state: dict           # (bases, outs) -> runs from there to the end of the half
    extra: np.ndarray     # an extra half-inning, from the runner placed on second

    def tilted(self, t: float) -> "Batting":
        return Batting(tilt(self.full, t),
                       {key: tilt(pmf, t) for key, pmf in self.state.items()},
                       tilt(self.extra, t))


def state_pmfs(frame: pd.DataFrame):
    """Runs from a base-out state to the end of the half-inning, per state.

    A thin cell is shrunk toward its pooled group rather than trusted on its
    own count. The grouping is out-dependent; see run_expectancy.POOL_GROUPS.
    """
    frame = frame.assign(grp=[pool(b, o) for b, o in zip(frame["bases"], frame["outs"])])
    group_pmf = {(g, o): _pmf(sub["runs_rest"].values)
                 for (g, o), sub in frame.groupby(["grp", "outs"])}
    out = {}
    for (bases, outs), sub in frame.groupby(["bases", "outs"]):
        n = len(sub)
        raw = _pmf(sub["runs_rest"].values)
        prior = group_pmf[(pool(bases, outs), outs)]
        out[(bases, outs)] = (n * raw + SHRINK * prior) / (n + SHRINK)
    return out


class Model:
    def __init__(self):
        frame = states()
        # Drop the bottom of the 7th here too, for the same reason the full
        # half-inning distribution does: it is truncated the moment the home
        # team leads, so it understates how much a state is worth.
        frame = frame[~((frame["inning"] == REGULATION) & (frame["half"] == "bottom"))]
        self.full = half_inning_pmf()
        self.state = state_pmfs(frame)
        # An extra half-inning is a complete trip through the runner-on-second,
        # nobody-out state, so its run distribution is that state's -- which
        # now pools genuine extra innings with regulation leadoff doubles,
        # rather than resting on the four extra half-innings on record.
        self.extra = self.state[("_2_", 0)]
        self.n_states = frame.groupby(["bases", "outs"]).size().to_dict()
        # Which distributions each half bats from. Both sides share the
        # league's here; matchup() gives each its own.
        league = Batting(self.full, self.state, self.extra)
        self.batting = {"top": league, "bottom": league}
        self.offset = MAX_DIFF
        self.width = 2 * MAX_DIFF + 1
        self._solve()

    def matchup(self, away: Batting, home: Batting) -> "Model":
        """A copy of this model in which each side bats from its own distributions.

        Cheap: the data is not reread, only the backward induction redone.
        """
        other = copy.copy(self)
        other.batting = {"top": away, "bottom": home}
        other._solve()
        return other

    def _tie_value(self) -> float:
        """P(home wins) from a tie entering an extra inning.

        Each extra inning is an independent trial from the same placed-runner
        start: home ends it ahead, away does, or it is tied again and the next
        one is the same trial. So v = P(home ahead) + P(tied) * v. The home
        side stopping the moment it leads cannot change who finishes ahead,
        so its early exit does not enter. With one shared distribution
        P(home ahead) = P(away ahead) and v is exactly 1/2.
        """
        joint = np.outer(self.batting["top"].extra, self.batting["bottom"].extra)
        home_ahead = np.triu(joint, 1).sum()      # joint[away runs, home runs]
        return float(home_ahead / (1.0 - np.trace(joint)))

    def _shift(self, wins: np.ndarray, pmf: np.ndarray, sign: int) -> np.ndarray:
        """Expected win probability after the batting team scores r ~ pmf.

        sign=+1 when the home team is batting (differential rises), -1 when the
        away team is batting.
        """
        out = np.zeros(self.width)
        for r, p in enumerate(pmf):
            if p == 0:
                continue
            if r == 0:
                shifted = wins
            elif sign > 0:
                # Home scored r: read the win probability r higher up the scale,
                # clamping at the top of the grid.
                shifted = np.empty_like(wins)
                shifted[:-r] = wins[r:]
                shifted[-r:] = wins[-1]
            else:
                shifted = np.empty_like(wins)
                shifted[r:] = wins[:-r]
                shifted[:r] = wins[0]
            out += p * shifted
        return out

    def _solve(self) -> None:
        """Backward induction over half-inning boundaries.

        top[i][d]    = P(home wins) about to start the top of inning i, home
                       leading by d, bases empty, nobody out.
        bottom[i][d] = same, about to start the bottom of inning i.

        Extra innings get their own pair, since they do not start bases empty:
        extra_top[d] / extra_bottom[d], with a runner already on second.
        """
        diffs = np.arange(-MAX_DIFF, MAX_DIFF + 1)
        away, home = self.batting["top"], self.batting["bottom"]
        self.top, self.bottom = {}, {}

        # A tie surviving the bottom of the 7th goes to extra innings, worth
        # self.tie to the home team. With both sides on the league
        # distribution that is exactly 50/50 -- asserted numerically in
        # validate(), not just assumed.
        self.tie = self._tie_value()
        self.end = np.where(diffs > 0, 1.0, np.where(diffs < 0, 0.0, self.tie))

        # An extra inning: away bats from a runner on second, then home does,
        # and a tie after both sends it to another identical inning -- so the
        # continuation value of a tie is again self.tie, which closes the
        # recursion without iterating.
        self.extra_bottom = self._shift(self.end, home.extra, +1)
        self.extra_top = self._shift(self.extra_bottom, away.extra, -1)

        # Bottom of the 7th. If the home team already leads it does not bat.
        batted = self._shift(self.end, home.full, +1)
        self.bottom[REGULATION] = np.where(diffs > 0, 1.0, batted)
        self.top[REGULATION] = self._shift(self.bottom[REGULATION], away.full, -1)

        for inning in range(REGULATION - 1, 0, -1):
            self.bottom[inning] = self._shift(self.top[inning + 1], home.full, +1)
            self.top[inning] = self._shift(self.bottom[inning], away.full, -1)

    def _lookup(self, table: np.ndarray, diff: int) -> float:
        return float(table[int(np.clip(diff + self.offset, 0, self.width - 1))])

    def win_probability(self, inning: int, half: str, outs: int, bases: str, diff: int) -> float:
        """P(home team wins), given the home team leads by `diff` right now.

        `half` is "top" or "bottom"; `bases` is a code like "_2_" or "123".
        """
        pmf = self.batting[half].state[(bases, outs)]
        if half == "top":
            # Away batting: their runs cut the home lead, then the bottom
            # follows -- an extra inning's bottom if this is an extra inning.
            after = self.extra_bottom if inning > REGULATION else self.bottom[inning]
            return float(sum(p * self._lookup(after, diff - r)
                             for r, p in enumerate(pmf) if p))
        if inning >= REGULATION:
            # Bottom of the 7th or any extra inning: the game is settled once
            # this half ends, except that a tie sends it to another extra
            # inning, worth self.tie.
            return float(sum(p * self._lookup(self.end, diff + r)
                             for r, p in enumerate(pmf) if p))
        return float(sum(p * self._lookup(self.top[inning + 1], diff + r)
                         for r, p in enumerate(pmf) if p))


BASES = ["___", "1__", "_2_", "__3", "12_", "1_3", "_23", "123"]

DOMINATED_BY = {
    "___": ["1__", "_2_", "__3"], "1__": ["12_", "1_3"], "_2_": ["12_", "_23"],
    "__3": ["1_3", "_23"], "12_": ["123"], "1_3": ["123"], "_23": ["123"],
}


def observed_states(model: "Model") -> pd.DataFrame:
    """Every real plate appearance, with the win probability the model gives it."""
    frame = plate_appearances()
    frame["wp"] = [model.win_probability(r.inning, r.half, r.outs, r.bases, r.diff)
                   for r in frame.itertuples()]
    return frame


def plate_appearances() -> pd.DataFrame:
    """Every real plate appearance in regulation: the state it began in, and who won."""
    plays = pd.read_parquet("data/tables/plays.parquet")
    games = pd.read_parquet("data/tables/games.parquet")
    home_won = (games.set_index("game_id")
                .apply(lambda r: r["home_score"] > r["away_score"], axis=1).to_dict())
    home_id = games.set_index("game_id")["home_team_id"].to_dict()

    rows = []
    live = plays[(plays["play_kind"] == "plate_appearance") & (plays["inning"] <= REGULATION)]
    for play in live.itertuples():
        bases = (("1" if pd.notna(play.first_base) else "_")
                 + ("2" if pd.notna(play.second_base) else "_")
                 + ("3" if pd.notna(play.third_base) else "_"))
        half = "bottom" if play.batting_team_id == home_id[play.game_id] else "top"
        rows.append({
            "game_id": play.game_id,
            "inning": int(play.inning),
            "half": half,
            "outs": int(play.outs_before),
            "bases": bases,
            "diff": int(play.home_score_before - play.away_score_before),
            "home_won": home_won[play.game_id],
        })
    return pd.DataFrame(rows)


def validate(model: "Model") -> None:
    print("=== structural checks ===")
    falling = 0
    for inning in range(1, REGULATION + 1):
        for half in ("top", "bottom"):
            for outs in (0, 1, 2):
                for bases in BASES:
                    curve = [model.win_probability(inning, half, outs, bases, d)
                             for d in range(-8, 9)]
                    if any(b < a - 1e-9 for a, b in zip(curve, curve[1:])):
                        falling += 1
    print(f"  win probability falls as the lead grows: {falling} of 336 curves  "
          f"({'PASS' if falling == 0 else 'FAIL'})")

    # The extra-innings recursion rests on a tie being exactly 50/50. That is
    # a claim about the arithmetic, not a modelling choice, so check it rather
    # than assert it in a comment.
    tied_extra = model._lookup(model.extra_top, 0)
    print(f"  a tie entering extra innings is 50/50: {tied_extra:.6f}  "
          f"({'PASS' if abs(tied_extra - 0.5) < 1e-9 else 'FAIL'})")

    # Adding a runner must help the batting team. Any breach is inherited base-out
    # noise; what matters is how large it is once future innings damp it.
    breaches = []
    for inning in range(1, REGULATION + 1):
        for half in ("top", "bottom"):
            for outs in (0, 1, 2):
                for base, better in DOMINATED_BY.items():
                    for state in better:
                        low = model.win_probability(inning, half, outs, base, 0)
                        high = model.win_probability(inning, half, outs, state, 0)
                        gain = (high - low) if half == "bottom" else (low - high)
                        if gain < 0:
                            breaches.append((abs(gain), inning, half, outs, base, state))
    breaches.sort(reverse=True)
    if breaches:
        sizes = [b[0] for b in breaches]
        print(f"  adding a runner lowers win probability: {len(breaches)} of 462 comparisons")
        print(f"    median breach {np.median(sizes):.4f}, largest {sizes[0]:.4f}, "
              f"{sum(1 for s in sizes if s > 0.01)} above 0.01")
        worst = breaches[0]
        print(f"    worst: inning {worst[1]} {worst[2]}, {worst[3]} out, "
              f"{worst[4]} -> {worst[5]}")
        print(f"    in the 7th inning: {sum(1 for b in breaches if b[1] == REGULATION)} "
              f"(no later innings left to average the noise away)")

    frame = observed_states(model)
    print()
    print(f"=== calibration on the {frame['game_id'].nunique()} completed games ===")
    frame["bin"] = pd.cut(frame["wp"], np.arange(0, 1.01, 0.1))
    # Weight by game, not by plate appearance: a team that blows a lead racks up
    # plate appearances while ahead, so PA-weighting systematically over-counts
    # the losses and makes a sound model look badly calibrated.
    per_game = (frame.groupby(["bin", "game_id"], observed=True)
                .agg(wp=("wp", "mean"), home_won=("home_won", "first")).reset_index())
    table = (per_game.groupby("bin", observed=True)
             .agg(games=("game_id", "size"), predicted=("wp", "mean"),
                  actual=("home_won", "mean")).round(3))
    table["pas"] = frame.groupby("bin", observed=True).size()
    print(table.to_string())

    brier = ((frame["wp"] - frame["home_won"]) ** 2).mean()
    base = ((0.5 - frame["home_won"]) ** 2).mean()
    print(f"\n  Brier {brier:.4f} vs {base:.4f} for a flat 0.500 "
          f"({100 * (1 - brier / base):.0f}% better)")
    print(f"  {len(frame)} plate appearances, but only {frame['game_id'].nunique()} "
          f"independent games -- treat every calibration row as provisional.")


def main() -> None:
    pd.set_option("display.width", 250)
    model = Model()

    print("half-inning run distribution (innings 1-6 and top of the 7th):")
    print("  " + "  ".join(f"{r}:{p:.3f}" for r, p in enumerate(model.full[:8])))
    print(f"  mean {sum(r * p for r, p in enumerate(model.full)):.3f}")

    start = model.win_probability(1, "top", 0, "___", 0)
    print(f"\nhome win probability at first pitch: {start:.3f}")
    print("  (batting last is the only asymmetry; no team, park or travel term)")

    print("\n=== P(home wins), tied game, nobody out ===")
    rows = {}
    for inning in range(1, REGULATION + 1):
        for half in ("top", "bottom"):
            rows[f"{half[0]}{inning}"] = {
                b: round(model.win_probability(inning, half, 0, b, 0), 3) for b in BASES}
    print(pd.DataFrame(rows).T.to_string())

    print("\n=== P(home wins), bottom of the 7th, home trailing by 1, by outs ===")
    grid = {}
    for outs in (0, 1, 2):
        grid[f"{outs} out"] = {b: round(model.win_probability(7, "bottom", outs, b, -1), 3)
                               for b in BASES}
    print(pd.DataFrame(grid).T.to_string())

    print()
    validate(model)

    print("\n=== P(home wins) by differential, start of each half-inning ===")
    band = range(-5, 6)
    rows = {}
    for inning in range(1, REGULATION + 1):
        for half in ("top", "bottom"):
            table = model.top[inning] if half == "top" else model.bottom[inning]
            rows[f"{half[0]}{inning}"] = {d: round(model._lookup(table, d), 3) for d in band}
    print(pd.DataFrame(rows).T.to_string())


if __name__ == "__main__":
    main()
