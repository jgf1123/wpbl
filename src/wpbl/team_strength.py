"""Team offense and defense, split out of the runs each half-inning produced.

    pixi run teams

Every half-inning has two teams in it. When the Firebells score two runs off
the Hunters, some of that is the Firebells' bats and some the Hunters' pitching
and fielding, and no single inning says how much of each. Across a season it
can be separated, because every team bats against three different defenses and
fields against three different offenses: a team whose innings run high against
everyone is hitting, and one that everybody scores on is not preventing runs.

The model
---------
Runs in a half-inning, offense o against defense d, follow the league
distribution tilted exponentially:

    P(r | o, d)  proportional to  p0(r) * exp((mu + a_o + b_d) * r)

p0 is the league's own half-inning distribution (win_probability.half_inning_pmf);
a_o is how much the offense adds, b_d how much the defense allows, both zero for
an average team. The tilt keeps p0's shape and moves only where it sits. Because
offense and defense add inside the exponent they combine with no extra
parameter, and the same tilt carries straight into the win-probability model:
it is applied to every base-out state's rest-of-inning distribution as well,
which assumes a strong lineup is strong by the same amount in every situation.

Shrinkage
---------
Four teams, about 97 half-innings a side each. A team's raw runs per
half-inning has a standard error near 0.16 runs -- as large as the differences
being measured. So the effects are shrunk toward zero, a_o ~ N(0, tau_off^2) and
b_d ~ N(0, tau_def^2), with offense and defense given separate spreads: there is
no reason the league's hitting and its run prevention vary by the same amount.
Neither spread is set by hand. Both are integrated over a grid under a flat
prior on [0, TAU_MAX], each grid point weighted by how well it explains the data
(Laplace approximation to the marginal likelihood). If the data cannot tell the
defenses apart, that weight piles up near zero and the defensive effects all
but vanish -- the honest answer, and better than a point estimate that pretends
to know.

Assumptions
-----------
* Team quality is fixed over the season. It is not -- rosters are 15 players
  and pitching usage changed as teams learned -- so these are season averages.
* A half-inning's runs depend only on the two teams: not on which pitcher is
  in, where the order is, or the score.
* The same uncensored half-innings as the league distribution: innings 1-6 and
  the top of the 7th.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl.win_probability import MAX_RUNS, Model, plate_appearances, uncensored_halves

TAU_MAX = 0.4        # top of the flat prior on each spread, in tilt units: about
                     # 1 run per half-inning between teams, well past plausible
TAU_STEPS = 21
TAU_FLOOR = 1e-4     # stands in for a spread of exactly zero
DRAWS = 400
SEED = 20260910
RUNS = np.arange(MAX_RUNS + 1)


def team_names() -> dict[str, str]:
    games = pd.read_parquet("data/tables/games.parquet")
    pairs = pd.concat([
        games[["home_team_id", "home_team_name"]].set_axis(["id", "name"], axis=1),
        games[["away_team_id", "away_team_name"]].set_axis(["id", "name"], axis=1)])
    return dict(pairs.drop_duplicates("id").itertuples(index=False))


def _moments(base: np.ndarray, t):
    """Log normaliser, mean and variance of `base` tilted by each entry of t."""
    t = np.asarray(t, dtype=float)
    weights = base * np.exp(t[..., None] * RUNS)
    z = weights.sum(-1)
    mean = (weights * RUNS).sum(-1) / z
    var = (weights * RUNS ** 2).sum(-1) / z - mean ** 2
    return np.log(z), mean, var


def expected_runs(base: np.ndarray, t):
    return _moments(base, t)[1]


def tilted_pmfs(base: np.ndarray, t) -> np.ndarray:
    weights = base * np.exp(np.asarray(t, dtype=float)[..., None] * RUNS)
    return weights / weights.sum(-1, keepdims=True)


def fit(X, y, base, precision, beta=None):
    """Penalised maximum likelihood by Newton's method, plus the log evidence.

    The tilted family is an exponential family, so the log likelihood is
    concave in beta and Newton converges in a handful of steps. The evidence
    drops terms that do not depend on the spreads (sum of log p0(y), the flat
    prior on mu), so it is only comparable across grid points.
    """
    beta = np.zeros(X.shape[1]) if beta is None else beta.copy()
    penalty = np.diag(precision)
    for _ in range(100):
        _, mean, var = _moments(base, X @ beta)
        grad = X.T @ (y - mean) - penalty @ beta
        hess = X.T @ (X * var[:, None]) + penalty
        step = np.linalg.solve(hess, grad)
        beta += step
        if np.abs(step).max() < 1e-10:
            break
    logz, _, var = _moments(base, X @ beta)
    hess = X.T @ (X * var[:, None]) + penalty
    loglik = float(y @ (X @ beta) - logz.sum())
    evidence = (loglik - 0.5 * beta @ penalty @ beta
                - 0.5 * np.linalg.slogdet(hess)[1] + 0.5 * np.log(precision[1:]).sum())
    return beta, hess, evidence


class TeamStrength:
    """Posterior over every team's offense and defense.

    Effects are stored as one vector per posterior draw: [mu, a_1..a_k, b_1..b_k],
    teams in self.teams order.
    """

    def __init__(self, model: Model | None = None, halves: pd.DataFrame | None = None,
                 names: dict | None = None, draws: int = DRAWS, seed: int = SEED):
        self.model = model or Model()
        self.halves = uncensored_halves() if halves is None else halves
        self.names = names or team_names()
        self.base = self.model.full
        self.league = self.model.batting["top"]
        self.teams = sorted(set(self.halves["batting_team_id"]), key=self.names.get)
        self.k = len(self.teams)
        self.index = {t: i for i, t in enumerate(self.teams)}

        X = self.design(self.halves)
        y = self.halves["runs"].clip(upper=MAX_RUNS).to_numpy(float)
        self.taus = np.linspace(0, TAU_MAX, TAU_STEPS)
        n, p = len(self.taus), X.shape[1]
        self.evidence = np.empty((n, n))
        self.beta = np.empty((n, n, p))
        self.hess = np.empty((n, n, p, p))
        for i, tau_off in enumerate(self.taus):
            beta = self.beta[i - 1, 0] if i else None
            for j, tau_def in enumerate(self.taus):
                precision = np.r_[0.0,
                                  np.full(self.k, max(tau_off, TAU_FLOOR) ** -2),
                                  np.full(self.k, max(tau_def, TAU_FLOOR) ** -2)]
                beta, self.hess[i, j], self.evidence[i, j] = fit(X, y, self.base,
                                                                 precision, beta)
                self.beta[i, j] = beta
        weights = np.exp(self.evidence - self.evidence.max())
        self.weights = weights / weights.sum()          # [tau_off, tau_def]
        self.point = np.tensordot(self.weights, self.beta, axes=2)
        self.samples = self._draw(draws, seed) if draws else self.point[None, :]

    def design(self, halves: pd.DataFrame) -> np.ndarray:
        rows = np.arange(len(halves))
        X = np.zeros((len(halves), 1 + 2 * self.k))
        X[:, 0] = 1.0
        X[rows, 1 + halves["batting_team_id"].map(self.index).to_numpy(int)] = 1.0
        X[rows, 1 + self.k + halves["fielding_team_id"].map(self.index).to_numpy(int)] = 1.0
        return X

    def _draw(self, draws: int, seed: int) -> np.ndarray:
        """A spread pair drawn by its weight, then the effects from the Laplace
        approximation at that pair -- so uncertainty about whether teams differ
        at all is carried along with uncertainty about by how much."""
        rng = np.random.default_rng(seed)
        n = len(self.taus)
        cells = rng.choice(n * n, size=draws, p=self.weights.ravel())
        out = np.empty((draws, self.beta.shape[-1]))
        chol = {}
        for d, cell in enumerate(cells):
            i, j = divmod(int(cell), n)
            if cell not in chol:
                chol[cell] = np.linalg.cholesky(np.linalg.inv(self.hess[i, j]))
            out[d] = self.beta[i, j] + chol[cell] @ rng.standard_normal(out.shape[1])
        return out

    # ----------------------------------------------------------------- lookups

    def find(self, query: str) -> str:
        """A team id from a loose name: "NY", "LA", "Queens", "boston", ..."""
        q = query.lower().replace(".", "").strip()
        hits = []
        for tid, name in self.names.items():
            if tid not in self.index:
                continue
            words = name.lower().split()
            keys = {tid, name.lower(), words[-1], " ".join(words[:-1]),
                    "".join(w[0] for w in words), "".join(w[0] for w in words[:-1])}
            if q in keys:
                hits.append(tid)
        if not hits:
            hits = [t for t in self.teams if q in self.names[t].lower()]
        if len(hits) != 1:
            known = ", ".join(self.names[t] for t in self.teams)
            raise SystemExit(f"Could not pick one team from {query!r}. Teams: {known}")
        return hits[0]

    def short(self, team: str) -> str:
        return self.names[team].split()[-1]

    def offense(self, beta, team):
        return beta[..., 1 + self.index[team]]

    def defense(self, beta, team):
        return beta[..., 1 + self.k + self.index[team]]

    def tilt_for(self, offense: str, defense: str, beta=None):
        """The tilt for `offense` batting against `defense`, per draw."""
        beta = self.samples if beta is None else beta
        return beta[..., 0] + self.offense(beta, offense) + self.defense(beta, defense)

    def matchup(self, away: str, home: str, beta) -> Model:
        return self.model.matchup(self.league.tilted(float(self.tilt_for(away, home, beta))),
                                  self.league.tilted(float(self.tilt_for(home, away, beta))))

    def win_probability(self, away: str, home: str, inning: int, half: str,
                        outs: int, bases: str, diff: int) -> np.ndarray:
        """P(home wins) under each posterior draw."""
        return np.array([self.matchup(away, home, beta)
                         .win_probability(inning, half, outs, bases, diff)
                         for beta in self.samples])


# ------------------------------------------------------------------- reports

def interval(values, lo=5, hi=95) -> str:
    a, b = np.percentile(values, [lo, hi])
    return f"[{a:.2f}, {b:.2f}]"


def spreads(ts: TeamStrength) -> None:
    var0 = float(_moments(ts.base, 0.0)[2])
    off, dfn = ts.weights.sum(1), ts.weights.sum(0)
    print("=== how much do teams differ? ===")
    print("posterior over the spread (SD) of team effects; 'runs' converts the tilt to")
    print("runs per half-inning for a team one SD from average\n")
    print(f"  {'tau':>5}  {'runs':>5}  {'offense':>8}  {'defense':>8}")
    for i in range(0, len(ts.taus), 2):
        print(f"  {ts.taus[i]:5.2f}  {ts.taus[i] * var0:5.2f}  {off[i]:8.3f}  {dfn[i]:8.3f}")
    for label, marg in (("offense", off), ("defense", dfn)):
        mean = float((ts.taus * marg).sum())
        near_zero = float(marg[ts.taus < 0.05].sum())
        print(f"\n  {label}: posterior mean spread {mean:.3f} (~{mean * var0:.2f} runs); "
              f"P(spread < 0.05) = {near_zero:.2f}")
    bf_off = ts.evidence[:, 0].max() - ts.evidence[0, 0]
    bf_def = ts.evidence[0, :].max() - ts.evidence[0, 0]
    print(f"\n  log evidence gain over 'all teams equal', best spread: offense only "
          f"{bf_off:+.2f}, defense only {bf_def:+.2f}, both "
          f"{ts.evidence.max() - ts.evidence[0, 0]:+.2f}")
    print("  (a gain under ~1 is no real evidence either way; over ~3 is substantial)")


def team_table(ts: TeamStrength) -> None:
    s, h = ts.samples, ts.halves
    mu = s[:, 0]
    league = expected_runs(ts.base, mu)
    rows = {}
    for team in ts.teams:
        off = expected_runs(ts.base, mu + ts.offense(s, team))
        dfn = expected_runs(ts.base, mu + ts.defense(s, team))
        rows[ts.names[team]] = {
            "scored/half": f"{h.loc[h['batting_team_id'] == team, 'runs'].mean():.2f}",
            "offense": f"{off.mean():.2f}", "off 90%": interval(off),
            "allowed/half": f"{h.loc[h['fielding_team_id'] == team, 'runs'].mean():.2f}",
            "defense": f"{dfn.mean():.2f}", "def 90%": interval(dfn),
        }
    print("\n=== team ratings: expected runs per half-inning ===")
    print("raw = what happened; offense = against a league-average defense; defense =")
    print(f"allowed to a league-average offense. League average {league.mean():.2f}.\n")
    print(pd.DataFrame(rows).T.to_string())


def distributions(ts: TeamStrength) -> None:
    s = ts.samples
    mu = s[:, 0]
    cols = ["0", "1", "2", "3", "4+"]

    def row(t):
        pmf = tilted_pmfs(ts.base, t).mean(0)
        return dict(zip(cols, [*pmf[:4], pmf[4:].sum()]))

    rows = {"league": row(mu)}
    for team in ts.teams:
        rows[f"{ts.short(team)} batting"] = row(mu + ts.offense(s, team))
    for team in ts.teams:
        rows[f"{ts.short(team)} fielding"] = row(mu + ts.defense(s, team))
    print("\n=== half-inning run distributions, against a league-average opponent ===")
    print(pd.DataFrame(rows).T.round(3).to_string())


def credit(ts: TeamStrength) -> None:
    """The season's runs, credited to the batting side, the fielding side, or luck.

    For each half-inning: baseline = what an average offense scores off an
    average defense; bats = what this offense adds to that; defense = what this
    defense adds; the rest -- the gap between what the matchup was expected to
    produce and what it did -- is left unexplained. The interaction between the
    two effects is tiny and rides along in 'unexplained'.
    """
    s, h = ts.samples, ts.halves
    o = h["batting_team_id"].map(ts.index).to_numpy(int)
    d = h["fielding_team_id"].map(ts.index).to_numpy(int)
    mu = s[:, :1]
    a, b = s[:, 1:1 + ts.k][:, o], s[:, 1 + ts.k:][:, d]
    e0 = expected_runs(ts.base, mu)
    frame = h.assign(
        baseline=np.broadcast_to(e0, a.shape).mean(0),
        bats=(expected_runs(ts.base, mu + a) - e0).mean(0),
        defense=(expected_runs(ts.base, mu + b) - e0).mean(0))
    frame["unexplained"] = frame["runs"] - frame[["baseline", "bats", "defense"]].sum(axis=1)

    scored = frame.groupby("batting_team_id")[["runs", "baseline", "bats", "defense",
                                               "unexplained"]].sum()
    scored.columns = ["runs", "baseline", "own bats", "opp defense", "unexplained"]
    allowed = frame.groupby("fielding_team_id")[["runs", "baseline", "defense", "bats",
                                                 "unexplained"]].sum()
    allowed.columns = ["runs", "baseline", "own defense", "opp bats", "unexplained"]
    for table in (scored, allowed):
        table.index = [ts.names[t] for t in table.index]
    print("\n=== where the season's runs came from (uncensored half-innings) ===")
    print("each row adds up: runs = baseline + the two teams' credit + unexplained\n")
    print("runs SCORED")
    print(scored.round(1).to_string())
    print("\nruns ALLOWED")
    print(allowed.round(1).to_string())


def pregame(ts: TeamStrength) -> None:
    rows = {}
    for away in ts.teams:
        rows[f"{ts.short(away)} (away)"] = {
            ts.short(home): (ts.win_probability(away, home, 1, "top", 0, "___", 0).mean()
                             if home != away else np.nan)
            for home in ts.teams}
    league = ts.model.win_probability(1, "top", 0, "___", 0)
    print("\n=== P(home wins) at first pitch: rows away, columns home ===")
    print(f"league model gives every matchup {league:.3f}\n")
    print(pd.DataFrame(rows).T.round(3).to_string())


def cross_validate(ts: TeamStrength) -> None:
    """Leave one game out: fit teams on the other 29, score the held-out game.

    The league distribution p0 is shared by both models and includes the
    held-out game, so this compares only what the team effects add.
    """
    model, h = ts.model, ts.halves
    games = pd.read_parquet("data/tables/games.parquet").set_index("game_id")
    pas = plate_appearances()
    pas["league"] = [model.win_probability(r.inning, r.half, r.outs, r.bases, r.diff)
                     for r in pas.itertuples()]
    league_start = model.win_probability(1, "top", 0, "___", 0)

    rows = []
    for game_id, test in h.groupby("game_id"):
        fold = TeamStrength(model, h[h["game_id"] != game_id], ts.names, draws=0)
        t = fold.design(test) @ fold.point
        y = test["runs"].clip(upper=MAX_RUNS).to_numpy(float)
        game = games.loc[game_id]
        won = float(game["home_score"] > game["away_score"])
        m = fold.matchup(game["away_team_id"], game["home_team_id"], fold.point)
        pa = pas[pas["game_id"] == game_id]
        wp = np.array([m.win_probability(r.inning, r.half, r.outs, r.bases, r.diff)
                       for r in pa.itertuples()])
        rows.append({
            "halves": len(test),
            "log_gain": float((t * y - _moments(fold.base, t)[0]).sum()),
            "brier_team": float(((wp - won) ** 2).mean()),
            "brier_league": float(((pa["league"] - won) ** 2).mean()),
            "start_team": (m.win_probability(1, "top", 0, "___", 0) - won) ** 2,
            "start_league": (league_start - won) ** 2,
        })
    cv = pd.DataFrame(rows)
    n = len(cv)
    per_half = cv["log_gain"].sum() / cv["halves"].sum()
    se = cv["log_gain"].std() * np.sqrt(n) / cv["halves"].sum()
    better = int((cv["brier_team"] < cv["brier_league"]).sum())
    diff = cv["brier_team"] - cv["brier_league"]
    print(f"\n=== does it predict better? leave-one-game-out, {n} folds ===")
    print(f"  half-inning runs, log-likelihood gain per half-inning over the league pmf: "
          f"{per_half:+.4f} (SE {se:.4f}, clustered by game)")
    print(f"  in-game win probability, Brier (game-weighted): team "
          f"{cv['brier_team'].mean():.4f}  league {cv['brier_league'].mean():.4f}  "
          f"difference {diff.mean():+.4f} (SE {diff.std() / np.sqrt(n):.4f}); "
          f"team model better in {better} of {n} games")
    print(f"  first-pitch win probability, Brier: team {cv['start_team'].mean():.4f}  "
          f"league {cv['start_league'].mean():.4f}")


def main() -> None:
    pd.set_option("display.width", 250)
    ts = TeamStrength()
    h = ts.halves
    print(f"{len(h)} uncensored half-innings from {h['game_id'].nunique()} games, "
          f"{ts.k} teams; {DRAWS} posterior draws\n")
    spreads(ts)
    team_table(ts)
    distributions(ts)
    credit(ts)
    pregame(ts)
    cross_validate(ts)


if __name__ == "__main__":
    main()
