# Bullpen simulator — spec

Status: draft v0, 2026-09-14. Nothing is built. **ASSUMPTION** marks a choice
Claude made that the user has not approved.

## Priorities and questions *(user-controlled)*

TBD — draft proposed in chat.

## What "done" looks like for v1 *(user-controlled)*

TBD — draft proposed in chat.

## Decided by the user (2026-09-14)

- The player manages one team's pitching through the 2026 postseason: a
  best-of-3 semifinal, then a best-of-5 championship series.
- Any of the 4 teams can be played. LAQ and NYH are the most interesting cases,
  but nothing in the code may be specific to a team.
- Real 2026 WPBL rosters and names.
- Pitcher quality is partly known: the manager sees a summary, never the
  distribution. Pitchers report their own fatigue.
- Pitching decisions only. Offense and fielding run automatically. Pitching a
  two-way player costs the lineup nothing, because the league uses a DH.
- Substitutions are allowed before any plate appearance.
- Championship series: Wed 16, Thu 17, Sat 19, Sun 20, Tue 22 Sep 2026. (The
  user wrote "Aug"; the weekdays match September.) Games 4 and 5 only if needed.
- Builder: probably Claude Code, not final.
- Fatigue and availability at the start come from **real pitch logs** through
  the day before each team's first semifinal game.
- Pitchers with **under 6 IP** in the regular season are their own group
  ("tryout" arms). Smoothing must never rate a tryout arm above the pitchers
  the team kept using. The data has a clean gap: nobody threw between 4.2 and
  7.2 IP.
- Overuse costs performance. Injury is a separate risk: rare, but it can end
  a pitcher's postseason. Jaida Lee (NYH) is already out with a foot injury.
- Pitchers report fatigue before each game and during mound visits. Mound
  visits are limited, so they can't happen before every batter.
- Losing the semifinal ends the run.
- The semifinal the player isn't in is simulated.
- Build the system first. Planning the computer manager waits until then.

## Calendar

The unit of time is the calendar day, and fatigue recovers per day.

| series | dates | source |
|---|---|---|
| Semi SF–BOS | 9, 11 Sep; G3 would be 13 Sep | feed. SF won 2–0 in reality |
| Semi NYH–LAQ | 10, 12 Sep; G3 14 Sep? | feed through 12 Sep. **ASSUMPTION**: G3 on the next alternate day |
| Final | 16, 17, 19, 20, 22 Sep | user |

Why the final is hard (regular season, `pixi run workload` / `pixi run pitches`):

- Median rest between starts is 7 days. Only 1 of 36 starts came on 3 days' rest or fewer.
- A full three-game week took **418 pitches across 6.9 pitchers**.
- At that rate, 5 games in 7 days is **~700 pitches**, about 1.7× any week in the data.
- Only 7 of 28 pitchers ever threw 140+ pitches in a 7-day window. The most was 175.

The final pushes arms past anything the data shows, so the fatigue model has to
guess beyond it (see Fatigue).

## Engine

The engine simulates one play at a time, from the base-out chain in
`markov.transitions()`.

State: inning (7 regulation, extra innings start with a runner on 2nd), half,
outs, bases, score, and each pitcher's pitch count for the day.

**Outcome probabilities (ASSUMPTION on how).** Shift the league transition
probabilities by one number, in the same exponential-tilt form as
`team_strength.py`, but applied per play instead of per half-inning:

    P(s -> t)  ∝  P0(s -> t) * exp(λ * v(s,t))
    v(s,t)     =  runs on the play + RE(t) - RE(s)      (the play's RE24)
    λ          =  a_offense - θ_pitcher + φ_fatigue

Plain language: a good pitcher (θ > 0) makes run-costly plays less likely and
cheap ones more likely. A strong offense and a tired arm push the other way. The
cost is that pitchers differ only in how good they are, not in *how*
(strikeouts vs. weak contact).

**This happens once per plate appearance, not once per inning.** Before every
PA, the engine takes the row of possible outcomes from the current base-out
state and reweights it with the λ of whoever is on the mound *right now*. A
pitching change between batters just means the next PA uses a different λ.
Fatigue can update between batters the same way.

Worked example, from regular-season data: runner on 1st, 1 out (RE 1.013), all
138 PAs from that state. v is each outcome's run value, and positive v is bad
for the pitcher. θ = ±0.5 is an exaggerated value chosen to make the shift
visible.

| next state | runs | v | league P0 | θ = +0.5 | θ = −0.5 |
|---|---|---|---|---|---|
| inning over (double play) | 0 | −1.01 | .058 | .091 | .033 |
| runner on 1st, 2 out | 0 | −0.56 | .348 | .436 | .251 |
| runner on 2nd, 2 out | 0 | −0.49 | .080 | .097 | .059 |
| 1st & 2nd, 1 out | 0 | +0.42 | .413 | .318 | .486 |
| 1st & 3rd, 1 out | 0 | +0.66 | .022 | .015 | .029 |
| 2nd & 3rd, 1 out | 0 | +0.83 | .043 | .027 | .063 |
| bases empty, 1 out (HR) | 2 | +1.64 | .036 | .015 | .078 |
| expected v | | | −0.008 | −0.192 | +0.201 |

C2 then picks each pitcher's θ so that, averaged over the mix of states the
league actually faces, her expected v matches her shrunk RE24/BF.

- P0 uses **regular-season plays only**. `plays.parquet` now includes 4 postseason games.
- Substitutions are offered only before plays where `is_plate_appearance` is
  true. Steals, wild pitches, and similar plays stay in the chain and happen
  between plate appearances.
- Fielding gets no separate term. It is already inside each pitcher's RE24/BF
  (**ASSUMPTION**).
- Pitches per play come from the actual distribution in `pitch_events`, by
  outcome (K, BB/HBP, in play, non-PA). They are the same for every pitcher
  (**ASSUMPTION**).
- Check: with λ = 0 the engine must reproduce the Markov RE table (1.17 at
  bases empty, nobody out), allowing for simulation noise.

## Pitcher quality

- Measured as RE24 per batter faced, regular season (`pitchers.py`).
- Shrinkage: θ_i ~ N(μ_group, τ²). τ comes from the data: the spread between
  pitchers minus the spread expected from sample size, or the Laplace grid
  already in `team_strength.py`. Each pitcher gets a shrunk estimate m_i with
  uncertainty s_i.
- **Two groups** (user rule): kept pitchers (6+ IP, 26 of them) and tryout
  arms (under 6 IP, 13). Regular season, runs saved per batter faced, pooled
  by group:

  | group | pitchers | BF | runs saved / BF |
  |---|---|---|---|
  | 6+ IP | 26 | 1,964 | +0.017 |
  | under 6 IP | 13 | 202 | −0.079 |

  The tryout pool is clearly worse, but it is *better* than several kept
  pitchers taken individually. Raw figures: Mackay −0.212, Padgham −0.183,
  Day-Bédard −0.120. So a group average alone does not guarantee the user's
  rule. How to enforce it is an open question (below).
- Injured pitchers are unavailable from the start. The list is supplied by the
  user (so far Jaida Lee).
- Each playthrough draws each pitcher's hidden true θ_i ~ N(m_i, s_i²).
- The manager sees the season line (IP, BF, ERA, FIP, K/7, BB/7) and a coarse
  grade based on m_i. Postseason lines build up during play.
- The opponent AI sees the same summary as the manager, not the hidden draw
  (**ASSUMPTION**).

## Fatigue — invented, tuned against real usage

Two quantities per pitcher (**ASSUMPTION** on form):

- `p`: pitches thrown today
- `L`: load carried from earlier days, multiplied by `r` each day to model recovery

      φ = α * max(0, p - p0) + β * L

`α, β, p0, r` are design settings, not estimates. Tune them until the AI manager's
usage under the defaults looks like the real season:

- Stint length: starts about 70 pitches, relief about 35 (Kaplan-Meier upper bound 49).
- 7-day load: median 45 relief-only, 85 in a week with a start. 90th percentile 96 / 139.

**Fatigue report.** Every pitcher reports readiness on a 4-level scale: her
true φ plus noise. The noise size is a setting. It happens:

- before each game, for the whole staff
- during a mound visit, for the pitcher on the mound. Visits are limited per
  game; the rule is an open question.

**Injury (invented; the data has one injury, and it isn't an arm injury).**
Each PA carries a small injury chance that rises with φ (**ASSUMPTION** on
form). An injured pitcher leaves right away and misses the rest of the
postseason (**ASSUMPTION**). Tune it so a well-run staff rarely loses anyone
over a full run, while overuse makes injury a real risk.

## Opponent AI (also the autopilot) — deferred until the system is settled

Notes kept from v0. Nothing here is proposed yet.

- **Keep or pull at the inning boundary:** the logistic model in `bullpen.py`
  (pitch count, leverage).
- **Mid-inning:** **ASSUMPTION**, rule not yet chosen. 34 of 37 real mid-inning
  changes came with runners on.
- **Which reliever:** highest m_i among pitchers not reporting "can't go", with
  better arms saved for higher leverage (`relievers.py` and `depth.py` found
  real managers did this). **ASSUMPTION**: exact rule.
- **Starter:** the most-rested pitcher with at least one start (**ASSUMPTION**).
- The same AI also runs the semifinal the player isn't in.

## Grading

After each game, replay it with the autopilot managing your team, using the same
random numbers. One draw per plate appearance, keyed by (half-inning, PA
number), keeps the two runs comparable. Report the wins your moves added or
cost, plus a decision log showing the leverage index at each change.

## Build shape

- `src/wpbl/sim_export.py` writes `data/bullpen_sim/calibration.js`, which
  defines a global `CAL = {...}`. It is a `.js` file rather than `.json` so the
  page opens from disk without a server. Pixi task: `sim-export`.
- `game/bullpen.html`: one page, inline JS, no dependencies.
- Checks: a Python self-check that the λ = 0 chain matches `markov`, and an
  in-page debug button that simulates 10k half-innings.

## Calibration tasks (before game code)

| # | Task | Target quantity |
|---|---|---|
| C1 | Regular-season P0 export | λ = 0 reproduces markov RE |
| C2 | How λ maps to RE24/BF; fit a_offense | a team's simulated runs per half-inning match `team_strength` expected runs |
| C3 | Pitcher estimates | τ; m_i, s_i per pitcher; under-6-IP rule enforced |
| C4 | Pitches per play | distribution by outcome class |
| C5 | Decline with pitch count | RE24/BF by today's pitch-count bucket. Report only: managers pull pitchers who struggle, which biases it |
| C6 | Short rest | appearances on 0 or 1 days' rest: how many, pitches, RE24/BF |
| C7 | AI coefficients | export `bullpen.py` logistic fit |
| C8 | Semifinal G3 | re-scrape the feed (network; needs the user's go-ahead) |

## Data notes

- Postseason games have **new team_ids** (SF is `vhub…` in the regular season,
  `r622…` in the postseason). Join teams by name or through a mapping.
- `plays.parquet` and `pitching.parquet` now contain postseason rows. Every
  calibration step filters `game_type == 'regular'`.
- The README says `validate.py` fails when a completed game falls outside the
  regular season. Postseason games are now in the tables, so confirm whether
  `pixi run check` still passes.

## Open questions / known unknowns *(user-controlled)*

TBD — draft proposed in chat.
