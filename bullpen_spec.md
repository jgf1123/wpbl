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
| Semi NYH–LAQ | 10, 12 Sep; G3 14 Sep? | LAQ won G1 10–3, NYH won G2 9–7. G3 is not in the feed's schedule (scrape of 14 Sep). **ASSUMPTION**: G3 on the next alternate day |
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

## First use: NYH semifinal G1 counterfactual

Question: when Saiki came out of G1, was saving NYH's better relievers better
for the series than using them to try to win G1?

**Cutoff (user).** Everything before play 42 of `j4uofrn55sr4wnlt` (10 Sep,
LAQ at NYH): "London Studer to p for Emi Saiki." At that point: top 5, 1 out,
runner on 2nd, LAQ up 4–0, Saiki at 85 pitches. Nothing after it is used to
fit anything. `pixi run wpq --during "top 5" --outs 1 --bases 2 --away 4
--home 0 --away-team LA --home-team NY --cutoff j4uofrn55sr4wnlt:42` gives
NYH 17.9% there (team-adjusted, 90% interval 11–27%) and 55.6% at first pitch.

**Worlds.**

- A: NYH relief scripted as it happened: Studer, then Izumi.
- B: NYH relieves from Eccles, O'Sullivan and Reynolds, best m_i first
  (**ASSUMPTION** on order). Reynolds was available (user). Lee is injured.
- Both worlds: NYH starts Kim in G2 (user).
- From the cutoff on, both worlds simulate the rest of G1, G2 (12 Sep) and G3.
  The real G2 result is not used.
- Both worlds share each replicate's hidden θ draw and its random numbers per
  (game, half-inning, PA).

**LAQ's closer (user, checked against her log).** Meidlinger's recovery is the
anchor for LAQ's side:

| date | IP | pitches | days since last | next |
|---|---|---|---|---|
| 21 Aug | 1.0 | 14 | 6 | pitched the next day, her only back-to-back |
| 22 Aug | 3.0 | 60 | 1 | her only 3-IP outing; sat out 23 Aug, next pitched 26 Aug |
| 10 Sep | 2.0 | 27 | 5 | pitched the 7th of G2 two days later |
| 12 Sep | 1.0 | 23 | 2 | entered the 7th tied, allowed 2 R; NYH won |

The user wrote 25 Aug; the log says 26 Aug. LAQ had no game on 24–25 Aug, so
the log shows one skipped game, not a measured three-day recovery. User's
rule: 2 IP in G1, as she threw, still lets her close G2; 3 IP would not. The
fatigue settings must reproduce that. So if a closer G1 in world B pulls a
third inning out of her, LAQ loses its G2 closer. LAQ's autopilot manages
LAQ in both worlds and reacts to the game in front of it (user), including
the rest of G1.

**Shimano (open, user).** LAQ's starting SS has pitched 3 times: 23 Aug start
(4.2 IP, 85 pitches), 29 Aug relief (3 IP, 41 pitches, 0 R), 5 Sep relief
(1 IP, 39 pitches, 4 R), moving from SS to the mound both times in relief. She
has not pitched in the semifinal: she started G1 at SS and only pinch-hit in
G2 (Eynon played SS). Why is still unexplained.

**Break-even, no simulator needed.** With w = NYH's G1 win probability after
the change and p2, p3 its G2 and G3 probabilities:

    P(series) = w (p2 + p3 − p2 p3) + (1 − w) p2 p3

At w = 0.18 and p = 0.57: ∂/∂w = 0.49 and ∂/∂p2 = ∂/∂p3 = 0.55. World B is
better exactly when G2 cost + G3 cost < 0.9 × G1 gain. For scale, a bullpen
that allowed nothing after the change lifts G1 only to about 35% (league
half-inning runs, no team adjustment). That caps the G1 gain near 17 points.

**Report.**

- P(NYH wins series) in each world, the difference, and its simulation error.
- The split into G1 gain vs. G2/G3 cost, which must agree with the identity.
- Short-rest fatigue is invented (C6), so show the difference as a curve over
  fatigue strength, with the break-even marked. The conclusion reads:
  "trying to win was better unless short rest costs more than X."

**Checks.** With fatigue off, B ≥ A. With B scripted the same as A, the
difference is exactly 0.

**Engine needs beyond v1.** Start from a mid-game state. Script one team's
manager for part of one game.

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
| C8 | Semifinal G3 | re-scraped 14 Sep by the user; G3 not scheduled in the feed yet |

## Data notes

- Postseason games have **new team_ids** (SF is `vhub…` in the regular season,
  `r622…` in the postseason). Join teams by name or through a mapping.
- `plays.parquet` and `pitching.parquet` now contain postseason rows. Every
  calibration step filters `game_type == 'regular'`.
- `pixi run check` accepts postseason games. SF–BOS semifinal G1
  (`ucwyhv1ki318nni5`) is a known gap in the pitch-code check
  (`validate.PITCH_STRING_GAPS`): the feed recorded incomplete pitch strings
  through about the 5th inning. The box-score pitch counts come from the same
  strings, so **Blunt's and Whitmore's 9 Sep pitch counts are too low**. That
  matters when seeding SF and BOS fatigue for the final. The build now
  estimates them (`parse.estimate_pitch_counts`, user decision 15 Sep):
  `pitching.pitches_est`, `pitching_stints.pitches_est` and
  `plays.n_pitches_est` (flag `n_pitches_estimated`) sit beside the feed's
  counts. Blunt 66 → ~99, Whitmore 70 → ~101, Bricker 30 → ~35; game total
  ~283. **Seed fatigue from the `_est` columns.** `workload`, `pitch_counts`
  and `bullpen` already use them.
- `tables.read()` with `tables.set_cutoff("GAME_ID:SEQUENCE")` gives every
  game before a play plus the finished half-innings of that game, with
  postseason team_ids mapped to regular-season ones. It drops the half-inning
  in progress, so fatigue seeding must read the cutoff game's plays directly.
- Semifinal G3 (14 Sep, `r1slo258zh4c0mwg`) is **excluded from training data
  except for pitcher fatigue** (user decision, 15 Sep): it is in
  `tables.TRAINING_EXCLUDED`, so `tables.read(name, "training")` drops it and
  `tables.read(name, "all")` keeps it. Why: both bullpens were exhausted (high
  OBP, 26 runs), so it would skew league and team averages. For the same
  reason it is the best evidence of how fatigued pitchers perform, so it
  belongs in fatigue seeding **and** in fitting the fatigue term (φ_fatigue);
  P0, pitcher quality and every other calibration leave it out. The other four
  playoff games are training data. This supersedes "regular-season plays only"
  and the `game_type == 'regular'` filter above for model fits
  (**FLAGGED** for the spec owner to reconcile).
- The feed calls O'Sullivan "Catherine" throughout semifinal G2.
  `parse.RAW_NAME_FIXES` corrects it in every string.

## Open questions / known unknowns *(user-controlled)*

TBD — draft proposed in chat.
