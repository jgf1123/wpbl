# Manager AI — spec

Status: draft v0, 2026-10-04. Nothing is built. **ASSUMPTION** marks a choice
Claude made that the user has not approved.

## Goal

A computer manager for one team in *Two Outs, So What?*
(`Two_Outs_So_What_rules.md`, played by `pixi run play`) that maximises the
probability of winning a best-of-3 or best-of-5 series. Pitch counts carry
across days by the rulebook (recover 20 a day, floor -30).

## Decided by the user (2026-10-04)

- **Opponent:** a fixed heuristic first. Eventually the AI must play another
  intelligent manager. Motivating case: 2026-09-10 LAQ at NYH, where NYH brought
  in a weaker reliever and LAQ answered with a weaker reliever of its own.
- **Substitution rules:** the official baseball rules (MLB OBR 5.11(a)), which
  `tosw_play_spec.md` section 4 already implements. Checked against the WPBL
  play-by-play below.
- **Outcome model:** the dice game as played: the Matchup Table's d100 reads
  the pitcher's card on 00-42 (from cards v0.8.0 it carries the double and
  the running play; through v0.7.0 it was 00-32, with those on shared lines
  33-44), reached on error 43-44, and the batter's card on 45-99, with steals
  by the steal table.
- **Fatigue:** the rulebook's pitch count and fresh / fading / gassed columns.
  Baseline rule: relieve any pitcher who reaches gassed.
- **Information:** full cards for both teams.
- **Conventions** (a team's defensive choices; dropping pitchers who were
  tried and did not perform) are switchable constraints, not part of the
  objective. The list of disfavored pitchers goes to the user for review before
  use, since absence can have other causes (injury, trade).

## Decided by the user (2026-10-04, second round)

- **Three-batter minimum: imposed** (OBR 5.10(g), no injury exception). Now in
  the rulebook and `play.py`.
- **Pinch hitting and bunts: out** for now.
- **Full rosters:** no conflicts, no injuries. Maximiliana (a conflict), Lee
  (injured) and Reynolds (NYH returned to her) all pitch.
- **Disfavored, do not pitch:** Padgham, Foxx, Frank, Apgar, Narasaki, Park.
  Bryant and Eyster have no pitcher card, so the question does not arise.
  Izumi can pitch (user); whether NYH wants her to is open.
- **Catcher:** anyone who caught in 2026. The cards already list C for exactly
  the seven who did, so no extra rule is needed.
- **Try the shadow price** and see whether it works.
- **Jaida Lee is NYH's closer** (user): she began 2026 as a starter and moved
  into that role. The "best reliever" test classed arms by stamina (under 70)
  and so picked Eccles; roles should come from usage, not stamina.

## Substitution rules against WPBL data (2026-10-04)

Regular season plus postseason, 80 team-games.

- **DH:** 62 team-games posted 10 (DH, pitcher carried at spot 10), 18 posted 9
  with the pitcher batting.
- **5.11(b), the two-way "Ohtani" rule, was never used.** All 21 starting
  pitchers who batted were listed at P, never also as DH. TOSW does not have
  the rule and does not need it.
- **A pitcher who bats stays in by moving to the field.** 15 of those 21
  batted again after leaving the mound, each from a field position (Whitmore
  CF, Albayati 3B, Mackay C, ...). In 3 of the 15 the team had a DH, which
  that move ends (5.11(a)(8)).
- **Fielders coming in to pitch is routine.** 52 relief outings came from
  players who had already batted in the game, 45 of them on teams using a DH,
  which the move ends (5.11(a)(14)).
  So losing the DH is a cost the AI will face often, which is why pitching
  changes and lineup interact.
- **No re-entry:** no pitcher returned after leaving (README).
- **Three-batter minimum (MLB 5.10(g)):** 1 of 153 relief outings faced fewer
  than three batters and left mid-inning (del Castillo, 2 BF). Imposed anyway
  (user).

## What the additive matchup table implies

Each plate appearance is 0.33 x pitcher card + 0.12 shared + 0.55 x batter
card. Batter and pitcher enter separately, so there is no matchup effect: a
batter's line does not depend on who is pitching. Consequences:

- The best nine and order depend on the opposing pitcher only through the run
  environment. The existing lineup search carries over.
- A pinch hitter helps only when the bench bat is better than the slot's,
  which the lineup search would already have started, or after a pitching
  change cost the DH or a bat. No pinch hitting for now (user). Substitutions
  forced by a pitching change are in.
- Where lineup and bullpen interact: bringing a fielder in to pitch costs the
  DH, and moves or removes bats. The pitching decision must be valued with its
  lineup consequence.

## Decisions the AI makes

| when | decision |
|---|---|
| before each game | starting pitcher; DH or not; nine and batting order |
| before each PA, fielding | keep or change pitcher, with the lineup rearrangement section 4 requires |
| before each PA, batting | steal green light: the WP rule in `tosw_play_spec.md` section 5, unchanged |

## Method (ASSUMPTION, for discussion)

1. **Exact game WP with real cards.** Extend `play_wp.py` from league-average
   to the actual nines, each team's lineup slot, and the pitcher's current
   column. Answers "WP now if pitcher X faces the next k batters" exactly.
2. **In-game policy with a shadow price per pitch.** Maximise
   WP - sum over pitchers of lambda_p x (pitches p carries out of the game).
   lambda_p is what one more pitch from p costs the rest of the series. The
   median-WP rule of thumb is a special case: high lambda brings a good arm in
   only when the game is close.
3. **Series level.** Tune the lambda_p by simulating whole series against the
   opponent policy. 3-5 games and about 7 arms keep this small.
4. **Baselines to beat:** B0 relieve at gassed with the best rested arm;
   B1 the median-WP rule.
5. **Opponent:** B0 first. Later, alternate best responses (each side
   re-optimises against the other) until neither improves: the 2026-09-10
   pattern, where one side resting its arms lowers the leverage for the
   other, should come out of this.
6. **Robustness:** run under 2-3 fatigue settings and report which decisions
   hold across them.

## Shadow price v1: built, and does not beat B0 (2026-10-04)

`pixi run manager` (`src/wpbl/manager.py`). Setup, the same for every policy:
best-of-5 on the final's calendar (16, 17, 19, 20, 22 Sep), all arms rested at
the start, every (team, opponent) pair with the team on each side, the opponent
playing B0. The nine, the order and the starter are fixed rules (best nine by
runs against a league pitcher; best rested arm with stamina 70+), so only
in-game pitching differs.

The policy, before every plate appearance at which a change is legal: for keep
and each legal change (a bench arm, or a player in the lineup moving to P with
the forced position moves), the fielding side's WP over the rest of this
half-inning, from an exact chain over (slot, outs, bases) with the real batting
order and the pitcher's card at her column, then the team-neutral `play_wp`
table. Less lambda x the slack she loses for every later game the series could
reach. A version that charged only the next game rode starters past gassed
(a starter does not pitch tomorrow anyway), and was replaced.

2,400 series per row, SE about 1.0 point:

| policy | series won vs B0 | pitchers per game, G1-G5 |
|---|---|---|
| B0 vs B0 | 49.7% | 2.0 2.3 3.0 3.0 3.5 |
| shadow, lambda 0 (greedy WP) | 50.7% | 4.7 4.7 6.3 4.8 6.0 |
| shadow, lambda 0.0002 | 51.0% | 4.9 4.7 4.5 3.9 6.0 |
| shadow, lambda 0.0005 | 50.7% | 5.0 4.4 4.1 3.5 5.6 |
| shadow, lambda 0.001 | 50.7% | 4.9 4.2 4.2 3.0 5.1 |
| saboteur: the move that MINIMISES WP (1,200 series) | 27.0% | |
| B1 median rule, 2 A arms, always relieves at gassed (same seeds) | 50.5% | 2.0 2.3 3.0 3.0 3.9 |

B1 relieves the moment the pitcher is gassed, like B0 (user: riding a gassed
pitcher is the wrong baseline); the median rule only picks which arm. Its
reliefs: A arm 7,338, B arm 4,113, A wanted but both would enter gassed 4,328
(best available instead) -- about 1.6 a game. 1,673 plate appearances were
pitched gassed because no legal arm was left. A first version that also rode
the pitcher when the leader was at 0.95+ (Claude's assumption, dropped) won
49.7%.

Reading: bullpen choices matter -- a deliberately bad bullpen loses 23 points
-- but B0 already sits near the top of the range. The shadow price changes usage
the way it should (higher lambda saves arms in games 3-4 and spends them in game
5, where nothing is left to save for) without a measurable gain. Whatever the
best policy gains over B0 is likely under about 2 points, which would need
~10,000 series per policy to see.

Likely reasons, untested: the pitcher's card is a third of the d100, and arms
on one staff are close (a league lineup scores 0.92-1.18 runs an inning off LAQ's
regular arms, fresh); the lookahead is one half-inning and knows nothing of the
arms it will need later in the same game.

### Pricing a warm-up (2026-10-11)

User: the real cost of an extra warm-up is 30 pitches that arm cannot throw
later, which a weaker arm must then throw -- probably in low leverage. Real
2026 games, postseason included (40 games with plays), measured two ways.

**The marginal 30 pitches** (`marginal_pitches.py`). For every team and date
it played, the 7 days ending that date (80 windows, about 3 games and 390
pitches each). Quality = runs per pitch off the pitcher's card, fading column,
league lineup. The marginal 30 = the window's pitches from its weakest arms.
Leverage = `leverage.py`, mid-inning included (average half-inning start
1.00). One run at an average half-inning start is worth 0.060 of win
probability (dice neutral model).

| team | runs/pitch, window average | marginal 30 | leverage, all pitches | marginal 30 | cost of 30 pitches |
|---|---|---|---|---|---|
| BOS | 0.0646 | 0.0689 | 0.72 | 0.75 | 0.60 WP points |
| LAQ | 0.0620 | 0.0685 | 0.87 | 0.66 | 0.63 |
| NYH | 0.0609 | 0.0678 | 0.97 | 0.90 | 1.03 |
| SFF | 0.0599 | 0.0650 | 0.84 | 0.73 | 0.57 |

All windows: **0.69 WP points** (median 0.73, 10-90% 0.09-1.22). Marginal
pitches lean to low leverage -- 41% at leverage under 0.5 against 29% of all
pitches -- except at BOS, whose thin staff could not hide Bricker and Dumais.
About 5% of marginal pitches still come at leverage 2+. Caveats: few,
overlapping windows (per-team figures are noisy); "marginal" is the weakest
card in the window, starters included (Mackay, Eckert); leverage from the
real-data model, the run conversion from the dice model.

**The leverage at a relief decision** (`change_leverage.py`). All 152 real
pitching changes (153 relief appearances; one entry did not begin with a
plate appearance):

| | n | mean | median | 25-75% | share at 1+ |
|---|---|---|---|---|---|
| all changes | 152 | 0.93 | 0.80 | 0.32-1.41 | 43% |
| starter relieved | 78 | 0.91 | 0.92 | 0.48-1.30 | 46% |
| reliever relieved | 74 | 0.94 | 0.63 | 0.22-1.57 | 39% |
| at a half-inning start | 93 | 0.95 | 0.91 | 0.32-1.46 | 48% |
| mid-inning | 59 | 0.88 | 0.71 | 0.33-1.22 | 34% |

Starters were relieved mostly in the 3rd-5th innings (60 of 78), at median
leverage 0.8-1.0, rising to 1.37 in the 6th.

**Calibration.** At a typical relief decision (leverage about 0.93), a warm-up
(0.69 WP points) is worth what 0.69 / (0.93 x 6.0) = **about 0.12 runs** of
pitching over the rest of the game is worth. So a reliever who needs one more
warm-up behind her to finish the game should be preferred only if she saves
more than about 0.12 runs over the longer arm -- less in low leverage, more in
high.

**Run value, not spread (2026-10-11).** `leverage.py`'s index is the spread
(standard deviation) of win probability over a half-inning's outcomes. In a
high-scoring game a big late lead keeps a fat tail -- about a 3% chance of 6+
runs -- so "top 7, home up 6" reads 0.95, average. A pitching decision needs
the *run value*: the win probability the fielding side loses to one more run
allowed, given the runs that score anyway (`Model.run_value`, dice model,
scaled so an average real half-inning start reads 1.00, where one run is worth
0.0619). T7 home up 6: 0.22; T7 tied: 3.90 (spread 2.41); B7 tied, 2 out,
bases loaded: 4.12 (2.31). On real game states the two barely differ on
average, because real games rarely sit in the tails:

| | spread index | run-value index |
|---|---|---|
| cost of 30 marginal pitches | 0.69 WP points | 0.77 (median 0.86, 10-90% 0.13-1.31) |
| leverage at real relief decisions, mean | 0.93 | 0.95 (starter relieved 1.00) |
| top 4.3% of plate appearances starts at | 2.0 | 2.03 |

### B2: runs to the end, warm-ups priced (built 2026-10-11)

Decided with the user:

- A gassed pitcher is replaced. Exception: with 2 outs in the 7th or later,
  keeping her is scored too (the inning may end without another warm-up).
- A pitcher who is not gassed may be replaced only in the top ~4% of plate
  appearances by run value (index 2.0+), e.g. tied in the 7th.
- Units are win probability: runs x run value now; warm-ups priced at what 30
  marginal pitches cost (0.0077), at the leverage they are later thrown in.

For every option (each legal reliever; keep her where allowed):

    score = series leverage today x run value now x 0.0619 x (-runs to the end)
            - next game's series leverage x 0.0077 x (expected warm-ups)

- Runs to the end of regulation: the arm pitches until gassed -- fresh column
  to 20, then fading, innings = pitches / her pitches per inning -- and the
  next-best available arm finishes (user: fine for now; later perhaps a typical
  reliever per team). League lineup rates. Extra innings not counted.
- Expected warm-ups: 1 for a new arm, plus the chance she runs out before the
  end. **ASSUMPTION:** pitches per inning spread with SD 6.
- Next game's series leverage: averaged over today's result; 0 when no next
  game is possible either way (game 5), so conservation switches off. At 1-2
  it is 0.5 (if we win, game 5 is worth 1.0) -- so B2 still conserves in an
  elimination game that is not the last possible one.
- Pool, lineup moves and fallbacks as B0 (relief role first; most bats among
  moves that bring in the same arm).

**First test (2026-10-11): no gain, and it spends more arms, not fewer.**
Conventions on, opponent B0, same 2,400 series (B0's own row is 50.2% now,
not 50.7%: rule 4' changed the lineups since).

| | series won | pitchers a game, G1-G5 | PAs pitched gassed a game | relievers from the lineup a game | DH lost |
|---|---|---|---|---|---|
| B0 | 50.2% | 2.0 2.2 2.7 3.0 3.4 | 0.22 | 0.41 | 38% |
| B2 | 50.0% | 2.1 2.5 3.1 4.3 4.9 | 0.98 | 0.55 | 41% |

B2's decisions (counted per plate appearance): relieved gassed 17,560; early
swap 2,649; kept at high leverage 13,020; rode out the 7th 654; no legal arm
left 2,558. The gap from B0 grows through the series (2.1 vs 2.0 arms in game
1, 4.9 vs 3.4 in game 5), and staffs run dry far more often -- the opposite of
the intent. Likely causes, untested: early swaps carry no in-game cost when the
next-game weight is low (0 in game 5), and the plan assumes the next-best arm
is always there to finish, so it never sees itself running out.

**Ablation (2026-10-11).** Early swaps now skipped while the pitcher is still
fresh (user). Same series; "gassed PAs" counts both no arm left and B2's rides
in the 7th.

| | series won | warm-ups a game | gassed PAs a game, G1-G5 | gassed PAs by inning, peak |
|---|---|---|---|---|
| B0 | 50.2% | 2.52 | 0.00 0.02 0.04 0.54 1.22 | 6th-7th (28%, 26%) |
| B2 | 49.9% | 3.02 | 0.05 0.13 0.18 2.75 4.28 | 3rd-4th (21%, 22%) |
| B2, no early swaps | 49.4% | 2.84 | 0.06 0.12 0.19 2.80 3.95 | 3rd-4th (24%, 23%) |

Early swaps are not the cause: without them B2 still runs dry about as often
in games 4-5. The difference from B0 is *when*: B0's gassed batters come late
in games 4-5, when a long week finally runs out; B2's come in the 2nd-4th
innings. That points to the plan's assumption that the next-best arm always
finishes: it makes a tired arm's short stint look cheap, so B2 burns arms in
short stints -- which the next day leaves its starters tired too (2nd-inning
gassed PAs rise from 4% to 11-12%).

**Instrumented (2026-10-11, `instrumented.py`, tables in `data/sim/`).** The
last guess was half wrong. Starters are the same under every manager: the
shared starter rule picks a fresh role starter in games 1-2, and in game 4
nearly every team's starter enters at about 44 pitches and lasts about 2.4
innings -- the schedule, not B2. Nightly recovery is also the same (e.g. after
game 4: 237, 242, 233 pitches a team of a possible 383). The difference was the
relievers: B2 brought in arms entering fading 34% and already gassed 12%
(B0: 24% and 3%), for 1.48 innings (B0 1.93), finishing 49% of games (B0 65%).
Cause: the plan credited the innings left after the candidate to the best
other arm *whatever her stamina*, so a junk arm followed by "the best arm
finishes" scored nearly as well as the best arm -- and the promise was
postponed at every decision.

**Fixed (user, 2026-10-12): the real staff, and a floor.** The plan now covers
the innings left with the other arms in turn, best first, each only for her own
coverage; each is a warm-up, weighted by the chance she is needed; if the staff
runs out, the last arm pitches on gassed. And an arm who would enter gassed is
not an option while another would not. Same 2,400 series:

| | series won | relief apps a game | entering fresh / fading / gassed | innings each | finished game | no arm left (PAs) | gassed BF, G4 / G5 |
|---|---|---|---|---|---|---|---|
| B0 | 50.2% | 1.52 | 73 / 24 / 3% | 1.93 | 65% | 770 | 0.54 / 1.22 |
| B2 before | 50.0% | 2.02 | 54 / 34 / 12% | 1.48 | 49% | 2,320 | 2.75 / 4.27 |
| B2 fixed | 51.7% | 1.72 | 64 / 33 / 3% | 1.73 | 57% | 1,368 | 0.81 / 1.84 |
| B2 fixed, no early swaps | 50.9% | 1.52 | 65 / 32 / 2% | 1.93 | 64% | 991 | 0.69 / 1.37 |

Relief use is back to B0's pattern. B2 accepts a tired-but-better arm more
often (33% entering fading against B0's 24%) without shorter stints. Early
swaps add about 0.2 relief appearances a game. Series won: +1.5 points over B0,
about 1.5 standard errors -- suggestive, not established.

**Confirmed (2026-10-12):** 7,200 series (300 per pairing and side; the first
100 are the 2,400 above), opponent B0, conventions on: **B2 wins 51.5% +/- 0.6**
of series against B0 (50% by symmetry) -- about 2.5 standard errors, the first
policy measurably better than B0. Warm-ups 2.72 a game; batters faced gassed
0.36 a game (0.83 in game 4, 1.76 in game 5), 42% of them in the 7th, where
B2 now rides out the inning by design.

### The postseason command (2026-10-12)

`pixi run postseason` (`src/wpbl/postseason.py`) plays the 2026 bracket with
B2 managing both sides:

- Semifinals SFF-BOS (9, 11, 13 Sep; SFF hosts 1 and 3) and NYH-LAQ (10, 12,
  14 Sep; NYH hosts 1 and 3), best of 3; final best of 5, 16 and 17 Sep at the
  SFF-BOS winner, 19 and 20 Sep at the NYH-LAQ winner, 22 Sep back at the
  first (user). "If needed" games are skipped once a series is decided.
- Pitch counts start from the user's chart for the morning of 9 Sep and
  recover 20 every calendar day for the whole league.
- Postseason settings (user, 2026-10-12): the lineup conventions; the
  **fallback ladder** -- when a pitcher must be replaced, B2 scores only the
  first non-empty tier of (1) relievers by role who would not enter gassed,
  (2) starters by role not held for a start, who would not enter gassed,
  (3) disfavored pitchers who would not enter gassed, (4) anyone legal;
  **"guaranteed" reservation** (starters held only for games sure to be
  played, so all hands when facing elimination). The starter is the shared
  starter rule's. B2's series leverage is each series' own: a semifinal game's
  stakes do not yet count the final.
- `--until 0.01`: postseasons in batches of 100 until every team's
  championship probability has a standard error under 1 point (user's
  "reliable"); reports reaching the final, winning it, and the finals.
- `--log DIR --seed N`: one postseason, one markdown file per game (lineups,
  each staff's counts, the play-by-play) plus a README of results. Before every
  pitching change a manager's note gives the stakes (series record and
  leverage, run value, next game's weight), the ladder tier, the top options
  (count and column on entering, runs to the end, expected warm-ups, score
  against the best) and the choice. Output only: `pixi run play` cannot replay
  these logs.

**First odds (2026-10-12):** 2,500 postseasons (seeds 1-2500), stopped when
every team's title probability had a standard error under 1 point:

| team | reach the final | win the title |
|---|---|---|
| SFF | 73.8% +/- 0.9 | 41.4% +/- 1.0 |
| NYH | 63.8% +/- 1.0 | 35.4% +/- 1.0 |
| LAQ | 36.2% +/- 1.0 | 16.2% +/- 0.7 |
| BOS | 26.2% +/- 0.9 | 7.0% +/- 0.5 |

Finals: SFF v NYH 47.5%, SFF v LAQ 26.3%, BOS v NYH 16.3%, BOS v LAQ 9.9%. The
real 2026 postseason (SFF over BOS 2-0, LAQ over NYH 2-1, LAQ over SFF 3-2)
was a 26% final and a 16% champion by this model.

**On cards v0.7.0** (columns read "below", 2026-10-12), same seeds: title SFF
42.8%, NYH 34.1%, LAQ 16.4%, BOS 6.8% (reaching the final 75.2, 63.4, 36.6,
24.8); finals SFF v NYH 47.9%, SFF v LAQ 27.3%, BOS v NYH 15.4%, BOS v LAQ
9.3%. Every change is within about 1.5 standard errors. The B2 results above
(51.5% against B0) were measured on v0.6.0 and have not been rerun.

**Narasaki (ASSUMPTION, 2026-10-12).** Her batter card is NYH's (traded) but
her pitcher card is still LAQ's -- the only such split. A pitcher may come in
only for the team that holds her pitcher card and, if she has one, her batter
card; so Narasaki pitches for no one and bats for NYH. (Before the ladder let
disfavored pitchers in, this never came up.)

**Known limitation.** When a staff is so thin that the plan uses every
remaining arm to exhaustion, its total runs do not depend on the order the
arms pitch in, so the plan cannot tell "best arm now" from "best arm later"
(seen in a game 5: Gilder and Coria scored identically). Weighting each future
inning by its expected stakes would fix it.

### B2: four fixes (user, 2026-10-13)

Prompted by two postseason logs: seed 29, where B2 replaced a fading Meidlinger
with a fresh Villarreal (mostly the first v0.8.0 cards' fatigue step; refit, see
dice_game_spec.md 7.4), and seed 3, where usage piled onto a few arms (Meidlinger
and Coria 5 games each; Studer, Day Bedard and Hondras never used, though not
clearly worse).

1. **Keep is scored two ways.** She pitches until gassed (as before), or she
   finishes this half and the best arm takes the next inning; the better counts.
   Before, keeping was priced as if she could never come out later.
2. **Pitch-count spread in the runs** (`Planner.stint3`). The innings an arm
   spends in each column are expectations under PITCH_SD 6 pitches an inning
   (still an ASSUMPTION), not a straight division: a "one fresh inning" plan
   sometimes spills past 20 pitches.
3. **Pitches carried replace the flat warm-up charge.** Every pitch the plan
   puts on an arm, a warm-up's 30 included, still on her count at the next game
   after recovery, against what she would carry without pitching; a later arm by
   the chance she is needed; priced 0.0077 / 30 WP a pitch (a warm-up's price)
   times the next game's series leverage. On a rested arm with one day off, a
   warm-up and her recovery carry 30: the old price. A busy arm now pays for what
   she carries, and a longer gap charges less. Next game only.
4. **The note always shows keep**, and each option's pitches carried; the
   decision data gain `carried` and `plan`.

Measured against the old B2 on the same cards (v0.8.0) and seeds:

| 300 postseasons, B2 both sides | old B2 | fixed B2 |
|---|---|---|
| runs per team-game | 7.88 | 7.85 |
| arms per team-game | 2.57 | 2.63 |
| relief appearances per team per postseason | 7.09 | 7.29 |
| distinct relievers per team per postseason | 3.09 | 3.21 |
| busiest reliever's share of them | 52.8% | 51.1% |
| plate appearances fresh / fading / gassed | 26.6 / 73.0 / 0.4% | 28.0 / 71.8 / 0.2% |
| relief entries at a clean inning start (real 62%) | 21.9% | 21.2% |

| 7,200 series against B0, conventions on | series won |
|---|---|
| old B2, cards v0.6.0 (2026-10-12) | 51.5% +/- 0.6 |
| old B2, cards v0.8.0 | 50.9% +/- 0.6 |
| fixed B2, cards v0.8.0 | 50.5% +/- 0.6 |

The fixes spread the work a little and halve gassed batters (0.32 to 0.24 a
game; game 5 1.55 to 1.21; "nobody left" 3,335 to 2,790), but they do not change
how often B2 beats B0: most of the fall from 51.5% is the cards, where milder
fatigue leaves less to manage. Neither B2 is now clearly better than B0.

Postseason odds, fixed B2 on v0.8.0 (2,400 postseasons): title SFF 39.8%, NYH
35.3%, LAQ 18.6%, BOS 6.3% (reaching the final 74.0, 62.1, 37.9, 26.0); finals
SFF v NYH 45.8%, SFF v LAQ 28.1%, BOS v NYH 16.2%, BOS v LAQ 9.8%.

**Still OPEN: mid-inning entries.** Of B2's changes against B0, 42,278 replaced a
gassed pitcher and 7,756 were early swaps. A gassed pitcher must come out at
once, and B2 only considers an early change at a run value of 2.0 or more (user),
which an inning's start rarely reaches -- so a pitcher who will run out during
the next inning is kept into it and pulled mid-inning. Real managers changed at
the inning's start (62% of entries). The lever would be a decision at each
half-inning start, scored like any other; not built.

### Beyond the four fixes: what was tried, and the default (2026-10-14/15)

**The question (user):** make B2 spread load and put the key arms in at the right
time -- the team's best pitchers pitch as much as they can, and in the innings that
matter. Everything below was judged in the dice game against B0 on the same 7,200
series (300 per pairing and side, conventions on, best of 5), the arbiter after an
expected-value plan failed there.

**Tried in B2, each switchable and off by default (`Planner` attributes):**

| version | idea | series won vs B0 | what it did to usage |
|---|---|---|---|
| four fixes (v0.8.0 cards) | -- | 50.5% | -- |
| + series horizon + C (`horizon_c`) | later games priced by refilling their relief with the arms that would be left; today's later innings by their chance of being close, best arms to the close branches | 50.6% | best relievers saved for bigger spots (top-2 share of quiet entries 70% -> 49%), but game-5 gassed batters 1.21 -> 1.82, "nobody left" 2,790 -> 3,766 |
| + ace gate (`ace_gate`) | the best 2 arms may enter only at a half-inning run value of 0.7+ (1.5+ if entering fading), from the oracle | 50.4% | no gain: most changes are forced by gassed, and the top two already had ~70% of big entries |
| + half-inning-start decisions (`half_start`) | decide at each half start without the 2.0 gate | 50.8% | 4.55 arms in game 5, gassed batters 1.34 a game, "nobody left" 19,373: the planner's failure |
| + the same with a warm-up hurdle (`hurdle`) | an unforced change must beat keeping by one warm-up (0.0077 x next game's weight) | 50.8% | optional changes halved; game-5 gassed batters still 4.37 |
| + half starts, later-games charge x2 / x4 (`later_scale`) | test whether B2 underprices tiring the staff | 49.8% / 48.5% | MORE changes, not fewer (see below) |

**Why the series horizon backfires.** It values tomorrow by filling its relief with
the best rested arms, and one arm's stamina (60-80 pitches) covers most of a game's
relief -- so in its model only the top one or two arms matter tomorrow and every
other arm is free to tire. Raising its weight makes B2 protect the aces harder by
handing innings to the "free" depth arms. In the dice game depth is not free: long
unlucky innings and mid-inning gassing call on the whole staff, and wearing it out
is what produces "nobody left" and gassed game-5 innings. A multiplier cannot fix a
model of the later games that is wrong about depth.

**The planner and the oracle (`analysis/manager/`).**

- `series_plan.py`: plans a team's postseason in expected values (starters, their
  innings, relief by stakes). With foresight of which innings would be close it
  turned every game into a bullpen game; without (`relief_dp`, stakes bands linked
  inning to inning) it still favoured ~3-inning starts and 4-5 arms a game.
  `plan_test.py` played those plans in the dice game: **48.8% against 52.3% for
  B2 on the same seeds** -- many short stints tire the staff and leave it empty.
- `oracle.py`: the best a manager who sees how every game will go could do --
  stakes from real 2026 team-games, stints split between half-innings by a
  dynamic program, a price per pitch per arm searched across the postseason. An
  upper bound and a teacher, not a plan (user). Findings
  (`oracle_report.py`, `oracle_when.py`):
  - **when the best arms pitch** (the lesson): almost never below a run value of
    0.3 (1-3%), rarely to 0.7; about half the time from 1.2; and mostly SAVED when
    they would come in already fading (24-37% even at 1.5+). Game weight and inning
    matter little once the stakes are known. B0 is nearly backwards (its best arm
    pitches 10% of 2.0+ innings).
  - **headroom**: 0.8-1.3 stakes-weighted runs a postseason over B0-like for NYH,
    LAQ, SFF (0.3 for BOS, whose arms are alike). Forcing B0's timing (stints until
    gassed, `--b0-timing`) keeps 42-71% of it: who pitches is the larger part, when
    is 29-58%.
  - **gassed was a loophole**: with no limit beyond the gassed column, the oracle
    rode each ace exhausted (Sato 33 innings in 8 games, entering at a count of
    117). Fixed in the cards (v0.9.0: gassed is a replacement-level line for
    everyone; dice_game_spec.md 7.4).
  - its short stints (1.3-2.5 innings) are NOT a lesson: they rely on hindsight;
    played with dice, many short stints are what failed.

**Usage on v0.9.0** (`usage_report.py`, 300 postseasons, B2 both sides): the
horizon version saves its best relievers for bigger spots (Lee entering at a run
value of 1.51 against 1.25; Meidlinger 1.51 against 1.22) but overworks the depth
(Bricker 2.7 appearances a postseason, 49% entering fading, 76% leaving gassed;
BOS 3.3 arms a game); the four-fix version keeps the staff fresher but sends weak
arms into big late spots (Hondras entering at 2.05, Maximiliana 2.35).

| v0.9.0 cards, vs B0 | series won | arms a game, G1 -> G5 | gassed batters a game (G5) | "nobody left" |
|---|---|---|---|---|
| B2, horizon + C | 51.0% +/- 0.6 | 2.26 -> 4.07 | 0.30 (1.40) | 3,308 |
| **B2, four fixes (the default)** | **51.0% +/- 0.6** | 2.15 -> 3.85 | **0.16 (0.78)** | **1,589** |

**Decided (user, 2026-10-15): the four fixes are B2's default** (`horizon_c =
False`): the same wins, half the gassed batters and "nobody left", simpler to
explain. The horizon, C, the gate, half starts, the hurdle and the multiplier stay
in the code, off, as tested and documented. **Open:** a real-time manager that
captures the oracle's "who and when" without wearing out the staff -- the next
attempt should price staff depth from what simulated games actually lose when a
team starts a game tired, not from a model that assumes depth is free.

### What the lineup conventions cost (2026-10-05)

Conventions on for pitching (roles, relief from relievers), both sides B0,
same 2,400 seeded series. One team picks its nine by batting alone (the old
`best_nine`: card eligibility, the starter bats at P only if that scores more);
the opponent plays the conventions nine. SE about 1.0 overall, 2 per team.

| | all | BOS | LAQ | NYH | SFF |
|---|---|---|---|---|---|
| both play the conventions | 50.7% | 26.7% | 47.0% | 63.2% | 65.8% |
| this team bats its best nine | 55.6% | 31.2% | 50.3% | 75.3% | 65.7% |

Playing players the way the real managers did costs about 5 points of series
wins -- as much as careless bullpen management (about 6). Most of it is NYH
(12 points: the conventions bench Izumi and Ciamarro for Eccles and Perez);
SFF loses nothing.

How often the bullpen reaches into the lineup, conventions on: 62% of games
start with a DH; the DH is lost in 32% of those; 0.39 relievers a game come out
of the starting lineup. (Batting-only nines start with a DH less often, 46%,
because the starter bats more often, and lose it in 19%.)

### Two-way starters and DH-aware relief (2026-10-06)

Same setup: one team switched, the opponent on the defaults, conventions on.
The comparison is "both play the conventions" above.

| | all | BOS | LAQ | NYH | SFF |
|---|---|---|---|---|---|
| defaults | 50.7% | 26.7% | 47.0% | 63.2% | 65.8% |
| starter doesn't bat (team keeps the DH) | 49.2% | 26.7% | 44.5% | 64.3% | 61.3% |
| DH-aware relief (keep the DH unless a lineup arm saves 0.1+ runs an inning) | 50.9% | 26.7% | 45.5% | 65.7% | 65.8% |

- **Starter doesn't bat:** affects Schroder (DH Haas), Mackay (DH
  Maximiliana), Saiki (DH Lahners) and Whitmore (DH Albayati). Overall -1.5,
  within noise; SFF -4.5 (per-team SE about 2.7) -- Whitmore, SFF's best bat,
  replaced by Albayati. Rule 4 (she bats at P, as SFF and NYH did) is right or
  neutral; nothing favours sitting her. (Later found: NYH never batted Saiki,
  and BOS never batted Schroder; rule 4' follows what each team did. Sitting
  them was neutral here: NYH 64.3%, BOS 26.7%.)
- **DH-aware relief:** DH lost in 17% of DH games instead of 32%, relievers
  from the lineup 0.32 a game instead of 0.39 -- and no change in series won.
  Consistent with the user's experience that a reliever's pitching dominates
  any drop in batting.

### Where NYH's cost comes from, and batting order (2026-10-06)

Exact expected runs over 7 innings against the league pitcher, each nine in
its best order -- no dice noise. Rough scale from the series runs above:
NYH's 0.5-0.7 runs a game were worth about 12 points of series wins, so about
2 points per 0.1 run. (Superseded: about 1 point per 0.1 run, from
Pythagenpat -- see "Where each team could most easily improve".)

NYH, one swap at a time from the conventions nine:

| starter | conventions | batting-only | Izumi for Eccles | Izumi for Perez | O'Sullivan for Zettlemoyer |
|---|---|---|---|---|---|
| Saiki (bats at P) | 8.26 | 8.98 | +0.44 | +0.24 | +0.19 |
| Kim | 8.45 | 8.98 | +0.45 | +0.24 | -- |

Eccles in CF is the most expensive convention: about 0.44 runs a game, more
than half of NYH's gap. Perez at SS costs about 0.24; with Saiki starting,
Zettlemoyer at 3B (O'Sullivan has fewer than 2 starts there) about 0.19.
Swapping in Ciamarro instead gains less (+0.28 for Eccles, +0.08 for Perez).
Runs depend only on which nine bat; Izumi has no CF starts, so "Izumi for
Eccles" is a nine, not a legal conventions lineup.

Batting order, the conventions nine with a rested starter:

| team | best order | real-style (by average window lineup spot) | by bat, best first |
|---|---|---|---|
| BOS | 6.915 | 6.862 | 6.909 |
| LAQ | 7.670 | 7.639 | 7.640 |
| NYH | 8.259 | 8.175 | 8.202 |
| SFF | 8.457 | 8.405 | 8.436 |

The teams' own orders cost 0.03-0.08 runs a game against the best order --
about a point of series wins at most. Simply batting the best bats first gets
within 0.03 of the best.

### Where each team could most easily improve (2026-10-06)

One bench player in for one regular, from the conventions nine (rule 4'),
scored by exact runs over 7 innings against the league pitcher, best order.
Runs depend only on which nine bat, so positions decide legality alone; for
each (in, out) the fewest regulars who change position ("moves", 0 = straight
swap). A regular may always keep the position the conventions gave her.
`analysis/manager/easy_gains.py`.

Conventions nines under rule 4': BOS 6.754 (Schroder starts) / 6.915 (Blunt,
Benach); LAQ 7.670; NYH 8.316 (Saiki) / 8.447 (Kim); SFF 8.457. Rule 4' moved
BOS on Schroder days from 6.904 and NYH on Saiki days from 8.259.

Best changes legal under 2+ starts:

| team | change | runs | moves | days |
|---|---|---|---|---|
| SFF | Gutierrez in at DH for Day-Bedard | +0.354 | 0 | not Whitmore's (she bats at P, no DH) |
| NYH | Izumi in at SS for Perez | +0.238 | 0 | Saiki's |
| NYH | Izumi in at 2B for Willan | +0.141 | 0 | Kim's (Saiki plays SS) |
| LAQ | Benitez in for Hondras | +0.173 | 2 | all |
| LAQ | Apgar / Ibarra in at CF for Davis | +0.143 / +0.137 | 0 | all |
| BOS | H. Kim in at DH for Haas | +0.170 / +0.172 | 0 | all |
| BOS | De Leija in at DH for Haas | +0.142 / +0.144 | 0 | all |

On Whitmore days SFF has nothing above +0.03. On Schroder days BOS's best
change breaks rule 4': Schroder bats at P for Haas, +0.285.

What relaxing eligibility would add:

- **1+ start:** LAQ Benitez in for Davis, Hondras to CF (1 start there),
  +0.323; Maximiliana at CF for Davis +0.288. BOS Padgham out at SS (De Leija
  +0.195; H. Kim with Yamamoto to SS, Haas to 2B, +0.223). NYH on Kim days
  Izumi at 3B for Perez +0.241.
- **Card:** NYH Izumi in CF for Eccles +0.443, the largest single change; SFF
  on Whitmore days Gutierrez at 3B for A. Yamamoto +0.259.

Arms touched by the headline changes: Day-Bedard (SFF) and Hondras (LAQ) are
role relievers leaving the lineup; Izumi (NYH) a role reliever entering it.
Disfavored arms (Padgham, Foxx, Apgar, Narasaki, ...) never pitch, so swapping
them does not touch relief.

**Confirmation in series.** Same 600 seeded series per team as "What the
lineup conventions cost", both B0, conventions on; one team plays its swap
on every day it is legal, the opponents the defaults. Game win % on the days
the swap is legal. `analysis/manager/easy_gains_series.py`.

| team | change | series: defaults -> swap | games: defaults -> swap |
|---|---|---|---|
| BOS | H. Kim for Haas | 25.8% -> 27.5% | 36.2% -> 36.6% |
| LAQ | Benitez for Hondras | 45.8% -> 47.3% | 48.0% -> 48.3% |
| NYH | Izumi for Perez / Willan | 64.2% -> 69.8% | 57.8% -> 61.5% |
| SFF | Gutierrez for Day-Bedard | 65.2% -> 63.7% | 60.0% -> 60.2% |

SE of a difference about 2.8 points for series, 1.4 for games (1.9 for SFF's
1,400 swap days): the shared seeds hardly pair once the lineups differ. Only
NYH is clear. SFF was checked directly (`sff_runs_check.py`): the swap
survives the game (Gutierrez still batting at the end in 98%, DH kept in 98%)
and adds +0.21 runs a game (8.763 -> 8.968, SE about 0.18), consistent with
the exact +0.35. Its missing wins are noise.

**Runs to wins: Pythagenpat.** Win % = R^x / (R^x + A^x), x = (runs per game,
both teams)^0.287. In SFF's games x is about 2.2 and it fits: predicted 60.3%
against 60.0% actual on swap days, 56.0% against 55.7% on Whitmore days. Its
slope there is 0.61-0.66 game points per 0.1 run; a best-of-5 multiplies a
game edge by 1.875 at even (each game decides the series only when the other
four split 2-2, 6 times in 16), 1.73 at 60%, 1.32 at 70% -- about **1 point of
series wins per 0.1 run**, not the 2 estimated earlier from NYH. So a +0.17
change is worth about 2 points of series, which 600 series cannot resolve;
seeing it at 2 SE would take roughly 7,000 series per arm. Exact runs plus
Pythagenpat is the better tool for ranking lineup changes.

### What batting choices and an added player are worth (2026-10-06)

Exact runs over 7 innings against the league pitcher, best order, rule 4'
conventions. Starter days weighted by start share, and wins by Pythagenpat,
both at each team's runs scored and allowed in the 2,400 default series
(`team_runs.py`); series by the best-of-5 formula at the team's game win %.
Pythagenpat reproduces the simulated game win % to 0.3 points (BOS 36.0 vs
35.9, LAQ 48.0 vs 48.0, NYH 58.0 vs 58.3, SFF 57.9 vs 57.6).
`analysis/manager/lineup_value.py`.

TOSW has no fielding, so everything here is batting only: the batting price
of the teams' choices, and the most their defence would have to be worth to
justify them.

**Part 1: the conventions nine against the best nine.** Every nine from the
roster, the DH status of the day kept, Mackay kept in LAQ's nine. In every
case the best nine was the first legal one in summed-bat-score order.

| team | 2+ starts | 1+ start | card | what changes (2+) |
|---|---|---|---|---|
| BOS | +0.26 runs, +1.9 games, +3.0 series | +0.37, +2.7, +4.4 | +0.37 | De Leija, H. Kim in; Haas, S. Yamamoto out; Benach/Schroder days also Blunt at SS for Padgham |
| LAQ | +0.40, +2.8, +5.3 | +0.47, +3.3, +6.3 | +0.47 | Benitez, Maximiliana, Apgar in; Eynon, Davis, Hondras out |
| NYH | +0.33, +2.1, +3.7 | +0.37, +2.4, +4.2 | +0.53, +3.4, +5.8 | Izumi, Narasaki in; Perez, Eccles out (Kim days also Zettlemoyer for Willan) |
| SFF | +0.23, +1.5, +2.6 | +0.23 | +0.37, +2.3, +4.1 | Gutierrez for Day-Bedard on DH days; Whitmore days +0.05 |

Under the teams' own 2+ eligibility each leaves about 0.2-0.4 runs a game,
3-5 points of series wins, in batting. Arms these nines touch: Blunt (BOS),
Roche (LAQ) and Albayati (SFF), starters, in the field; Maximiliana and
Izumi, relievers, in; Hondras, Day-Bedard and Eccles, relievers, out.

**Part 2: one regular replaced by a benchmark.** The incumbent sits and a
blended card bats in her slot. A blend is the starts-weighted mean of its
players' blocks, which is exact (a batter's blocks are sums over her d100
faces); it is the expected bat drawn from the pool, not a real player.

- **Replacement:** the bench, starts-weighted: players outside their team's
  top nine by season batting starts (24 players, 133 starts), 6.841 (bat
  score, runs of nine of her), the same at every position. In a four-team
  league with every player rostered, the bench is the only cheap talent; the
  generic card (6.102, pitchers who never bat) is too low. Tryout players
  who were not signed are presumably weaker still (user), so if anything this
  level is generous.
- **Average at the position (user):** min(positional, league), each a
  starts-weighted blend over the season. League 7.666 (all non-P starts),
  which sets C (9.694 at the position), 1B (8.297), 3B (7.811), RF (7.931)
  and DH; 2B 7.011, SS 6.597. LF and CF share players (those who started at
  both made 38 of LF's 80 starts and 39 of CF's), while RF stands apart (11
  and 10 with LF, all fringe). **Revised 2026-10-08 (user):** a position's
  pool is the players who can play it. CFs also play LF, but most LFs never
  played CF (Studer, Villarreal, Park, Murphy), so LF pools LF and CF starts
  (6.925) while CF keeps its own (6.681). First published here as one LF/CF
  pool for both.

The numbers that matter are the positive ones: what a team gains if it could
find a bench bat, or an average one, who can also field the position.

| team | pos | regular | vs replacement | vs average |
|---|---|---|---|---|
| LAQ | CF | Davis | +0.235 runs, +3.2 series | +0.215, +2.9 |
| NYH | CF | Eccles | +0.235, +2.7 | +0.212, +2.4 |
| BOS | SS | Padgham | +0.232, +2.7 | +0.204, +2.4 |
| BOS | DH | Haas | +0.181, +2.1 | +0.274, +3.2 |
| LAQ | RF | Hondras | +0.087, +1.2 | +0.177, +2.4 |
| BOS | RF | Paddison | +0.044, +0.5 | +0.136, +1.6 |
| BOS | C | Greenwood | +0.037, +0.4 | +0.129, +1.5 |
| NYH | 3B | Zettlemoyer, Perez | +0.012, +0.1 | +0.105, +1.2 |
| SFF | DH | Day-Bedard | +0.031, +0.4 | +0.085, +1.0 |
| BOS | 2B | S. Yamamoto | +0.044, +0.5 | +0.063, +0.7 |
| SFF | 3B | A. Yamamoto | -0.037 | +0.057, +0.7 |
| SFF | SS | Leguizamon | +0.045, +0.5 | +0.014, +0.2 |
| LAQ | SS | Eynon | +0.038, +0.5 | +0.010, +0.1 |
| NYH | LF | Studer | +0.021, +0.2 | +0.028, +0.3 |
| BOS | 1B | Schroder, Dumais | -0.064 | +0.027, +0.3 |

- **The big holes are at SS and CF** (Padgham, Davis, Eccles): each bats
  about 0.23 runs a game below a bench bat. These are the premium defensive
  positions, consistent with teams buying defence with offence there.
- **BOS DH (Haas) is the exception:** a DH needs no glove, so that hole is a
  pure batting choice.
- **At SS and CF the benchmarks invert:** the average SS (6.597) and CF
  (6.681) bat below the bench, so "vs average" is the easier bar there; at LF
  (6.925) the two nearly agree.

The negative cells are each regular's batting runs above the benchmark. The
largest: Benites (NYH C) -0.890 vs replacement, -0.796 vs average; Lansdell
(LAQ 3B) -0.414 / -0.320; Lahners (NYH DH) -0.368 / -0.276; SFF CF (Whitmore
58% of days, Day-Bedard 42%) -0.362 / -0.386; Leblanc (SFF 1B) -0.346 /
-0.252; Jorge (SFF C) -0.327 / -0.233.

Cautions: each positional average rests on 80 starts and in effect four
regulars, so differences under about 0.1 run are not meaningful. C is the
most skewed: the min rule sets it to the league average, so "vs average"
understates how scarce catchers are (only 7 players caught).

**Units for readers (2026-10-08).** A bat score (runs of nine of her) puts
nine slots of difference into one number. The post reports each blend per slot
instead: runs a game a team gains or loses with her in one slot of an
otherwise league-average lineup, against a league-average starter
(`lineup_value.slot`). Nearly the bat-score gap divided by 9: C +0.228, 1B
+0.074, DH +0.054, RF +0.031, 3B +0.018, league 0, LF -0.049, 2B -0.067, LF
pool -0.077, bench -0.085, CF -0.105, SS -0.112. Padgham is 0.233 below the
bench per slot, matching the +0.232 above.

Weighting the bench by plate appearances instead of starts gives 6.853
against 6.841: no visible difference per slot. Starts kept: the benchmark
stands for a player who takes a regular's slot for whole games, and
plate appearances also count batting-order position and pinch-hitting.

### What losing a player costs (2026-10-06)

Each player in any of her team's conventions nines is taken off the roster
(trade, injury) and the lineup rebuilt. Batting only, exact runs a game,
starter days by start share; a lost starter's starts go to the team's other
starters in proportion. `analysis/manager/player_loss.py`.

- **Loss (conv):** the conventions response (rule 5: the next by window
  starts, positions by window starts, 2+ eligibility).
- **Loss (best):** the best 2+ nine without her against the best with her.
- **Value:** her runs over a replacement (bench) bat in her own slot, on the
  days she bats (P included).
- **Depth** = loss (conv) - value: positive means the real backup is worse
  than a bench bat.

**Positions with no viable replacement.** The most important finding: three
teams have a position that only one or two players on the roster can play,
by card.

| team | pos | who can play it (starts there) | if lost |
|---|---|---|---|
| NYH | C | Benites (18) only | no catcher at all: emergency C (Narasaki) every day |
| SFF | SS | Leguizamon (22) only | no shortstop: emergency SS (Albayati) |
| LAQ | C | Foxx (14), Mackay (9) | losing Foxx leaves no catcher on Mackay's start days: emergency C (Maximiliana) |

BOS has a backup at both (C: H. Kim, 6 starts; SS: Blunt 2, De Leija 1,
S. Yamamoto 1, Haas 0 by card). An emergency fielder is let play the first
position that makes a legal nine; the runs then count her bat only, so these
rows understate the true cost by whatever the defence is worth. Benites is
NYH's most valuable player by a wide margin even before that.

The most costly losses, conventions response:

| team | player | loss conv | series | loss best | value | depth | next in |
|---|---|---|---|---|---|---|---|
| NYH | Benites (C) | +0.953 | -12.2 | +1.043 | +0.890 | +0.064 | Narasaki C (emergency) |
| SFF | Whitmore* | +0.478 | -5.8 | +0.568 | +0.669 | -0.191 | Albayati, Gutierrez DH |
| NYH | Lahners | +0.433 | -5.3 | +0.329 | +0.368 | +0.065 | Narasaki DH |
| LAQ | Lansdell | +0.351 | -4.8 | +0.463 | +0.414 | -0.063 | Benitez 2B, Maximiliana DH |
| NYH | Yonetani | +0.335 | -4.1 | +0.455 | +0.218 | +0.118 | Narasaki RF |
| NYH | O'Sullivan* | +0.320 | -3.9 | +0.148 | +0.200 | +0.120 | Narasaki LF |
| LAQ | Edwards | +0.287 | -3.9 | +0.292 | +0.217 | +0.071 | Frank 1B |
| BOS | Geldenhuis | +0.224 | -2.5 | +0.369 | +0.187 | +0.037 | De Leija DH |
| BOS | Hastings | +0.220 | -2.5 | +0.366 | +0.183 | +0.037 | De Leija DH |
| SFF | Leblanc* | +0.211 | -2.5 | +0.340 | +0.346 | -0.136 | Albayati 1B, Gutierrez DH |
| LAQ | Mackay* | +0.196 | -2.7 | +0.271 | +0.253 | -0.057 | Maximiliana DH |

\* also an arm: the pitching loss is not counted ("What one arm is worth":
about 3.4-4.5 series points for a best reliever or ace).

**Depth is mostly one bench player.** The conventions bring in the same next
player for most losses, so each team's depth is nearly constant:

| team | usually in | typical depth |
|---|---|---|
| SFF | Gutierrez (DH; C for Jorge) | -0.14: the deepest |
| LAQ | Maximiliana (DH) | -0.06 |
| BOS | De Leija (DH) | +0.04 |
| NYH | Narasaki, a disfavored pitcher | +0.12: the thinnest |

**Some losses help the batting.** Below-replacement regulars are worth less
than the next player up: Padgham -0.162, Haas -0.144, Davis -0.137, Hondras
-0.149, Eccles -0.109, Day-Bedard -0.154 (negative loss = the team bats
better without her). The same holes as above; for Padgham, Davis and Eccles
the open question is their defence. Leguizamon's -0.182 rests on the
emergency SS and is not a real gain.

Artifacts: a few small negative "loss best" values (Padgham -0.021,
Leguizamon -0.054) come from the conventions bending eligibility after a
loss (an emergency or card-fallback fielder), which the best search may then
keep. In every case the best nine was the first legal one in summed-bat-score
order.

### Who comes in, and filling the holes (2026-10-08)

Follow-ups written for the lineup blog post. Exact runs and per-slot bats as
above (`lineup_value.slot`: runs a game in one slot of an otherwise average
lineup, against an average starter; the bench is -0.085).

**The usual lineup held up to two checks.**

- *Window start* (`window_start.py`): starting the late season after the
  August trades instead of at each team's midpoint (19-21 Aug) changes no
  usual lineup from 22 Aug; from 27 Aug only BOS's Bryant and Haas swap 3B and
  DH. Window kept (user).
- *Position-first* (`position_first.py`): taking the most-started player at
  each position (DH included) instead of the nine most-started players bats
  0.02-0.20 runs a game better (weighted: BOS +0.14, LAQ +0.12, NYH +0.02,
  SFF +0.20), mostly by putting at DH a player the team used there (De Leija,
  Gutierrez) instead of a leftover fielder (Haas, Day-Bedard). It drops
  players who moved around (Eynon, 15 of LAQ's 16 late games across 3B, SS
  and DH). Usual lineup kept (user); the post mentions the difference.

**Who comes in** (`next_up.py`). When a team loses a regular, the usual
lineup almost always brings in the first player outside the nine: De Leija
(BOS), Maximiliana (LAQ; Benitez for an infield loss when Mackay pitches),
Narasaki (NYH, for 6 of its 10 regulars) and Gutierrez (SFF; Albayati on
Whitmore's and Eckert's days). So the depth score in the section above
mostly measures one player per team. A team is thin where that player cannot
fill in and the usual lineup reaches further:

| team | position lost | who comes in (rank by starts) | bat per slot |
|---|---|---|---|
| BOS | C (Greenwood) | H. Kim (12th-13th) | -0.095 |
| BOS | 1B (Schroder) | Dumais (11th) | -0.135 |
| BOS | 1B (Dumais, Schroder's days) | Robinson (13th) | -0.181 |
| BOS | SS (Padgham) | Blunt (11th-12th), when she isn't pitching | -0.175 |
| LAQ | C (Foxx) | no one when Mackay pitches: emergency C | - |
| LAQ | 1B (Edwards) | Frank (13th-14th) | -0.154 |
| LAQ | CF (Davis) | Ibarra (11th-12th) | -0.181 |
| NYH | C (Benites) | no one: emergency C | - |
| NYH | 2B, SS or 3B | Ciamarro (11th-12th) | -0.045 |
| SFF | CF (Day-Bedard, Whitmore's days) | Eyster (11th) | -0.114 |
| SFF | SS (Leguizamon) | no one: emergency SS | - |

NYH's next player, Narasaki (-0.199), bats below every one of these deeper
replacements; SFF's, Gutierrez, above an average starter (+0.199).

**Filling the holes** (`fit_candidates.py`, `trade_fits.py`). The Part 2
holes (BOS SS, LAQ CF, NYH CF) against players on the other teams. Rules
(user): leave out each team's own top player at the position; rank by time
at the position, since a player with only 2 starts there is someone a team
could find on its own roster; DH open to anyone. A CF hole counts CF time
only: neither LAQ's LF (Villarreal) nor NYH's (Studer) has started in CF, so
an LF cannot fill it by moving someone over. Set aside (user): Ibarra to NYH
and Narasaki to LAQ, which would undo the August trade, and BOS's Geldenhuis,
who plays LF beside Hastings. Each candidate replaces the regular at the
position (others unchanged, best order); her own team rebuilds its usual
lineup without her:

| player | from -> to | replaces | receiving team gains | her team loses |
|---|---|---|---|---|
| Benitez | LAQ -> BOS SS | Padgham | +0.318 runs, +3.7 series | 0 (not in its usual lineup) |
| Eyster | SFF -> LAQ CF | Davis | +0.206, +2.8 | 0 (bench) |
| Eyster | SFF -> NYH CF | Eccles | +0.205, +2.3 | 0 (bench) |
| Day-Bedard | SFF -> LAQ CF | Davis | +0.180, +2.4 | -0.154: SFF bats better, Gutierrez at DH |
| Day-Bedard | SFF -> NYH CF | Eccles | +0.180, +2.1 | -0.154 |

Benitez alone is worth more to BOS than its whole best lineup in Part 1
(+0.26). Her cost to LAQ is in future losses: on Mackay's days, when LAQ has
no DH, she is who replaces a lost infielder or Hondras; without her, LAQ
would play Roche (a starting pitcher) in RF, and each such loss would cost
about 0.12 runs a game more on those days (0.116-0.119). Day-Bedard is also
an SFF reliever; her arm is not counted. All batting only.

### Where the saboteur loses (2026-10-05)

Two bad but legal managers against B0, conventions off, same 2,400 series as
the saboteur (SE about 1.0):

| manager | series won | pitchers per game |
|---|---|---|
| B0 vs B0 | 49.7% | 2.0-3.5 |
| worst arm, never gassed: relieve at gassed with the worst arm who would not enter gassed | 44.1% | 2.9 |
| never relieve: the starter pitches the whole game, gassed or not | 43.5% | 1.0 |
| saboteur: before every batter, the legal move that minimises WP | 27.0% | |

Picking the worst arm costs about 6 points; never relieving costs about 6
points. The saboteur's other ~17 points most likely come from churning arms
before every batter (untested: each change spends 30 pitches of warm-up,
which would run the staff into gassed arms) -- not from any decision a real
manager would make. The realistic range of bullpen management, from a
careless manager to B0, is about 6 points of series wins.

### What one arm is worth (2026-10-04)

The size of the prize. Each team in turn loses one arm (she may still bat, not
pitch); both sides play B0; same 2,400 seeded series (600 per team), SE about
1.0 point overall and 2 per team.

| | all | BOS | LAQ | NYH | SFF |
|---|---|---|---|---|---|
| full staff | 49.7% | 24.0% | 44.7% | 69.7% | 60.3% |
| without best reliever | 46.3% | 20.2% | 42.5% | 64.3% | 58.3% |
| without ace | 45.2% | 21.7% | 42.5% | 60.3% | 56.2% |

Best reliever = fewest runs per inning to a league lineup (fading column)
among arms with stamina under 70: Dumais, Meidlinger, Eccles, Coria. Ace = the
same among stamina 70+: Blunt, Sato, Saiki, Gilder.

Losing the best reliever for the whole series costs about 3.4 points of series
wins; losing the ace about 4.5 (the next rested starter fills in). A bullpen
policy can only re-allocate innings among the arms a team has, so its gain is
a fraction of what a whole arm is worth -- consistent with the sensible
policies landing within a point of B0. Team strength, by contrast, spans 24% to
70%.

### Lineup conventions: decided (user, 2026-10-04)

- **Eligibility: 2 or more starts at the position** -- the team tried her there
  once and thought it worth doing again. (Replaces "on her card", which also
  lists positions reached by a mid-game move.)
- **Starter role: 2 or more starts in the team's last 10 games**, postseason
  included. Everyone else is a reliever.

Regulars, full season against late season (most starts at the position; each
team's regular season split at its midpoint, 7 / 8 games, then the postseason):

- **Up the middle is stable.** C, SS and CF have the same regular in both
  halves for BOS (Greenwood, Padgham, Hastings -- Haas led CF early), NYH
  (Benites, Perez, Eccles) and SFF (Jorge, Leguizamon, Whitmore). The one
  exception is LAQ's SS: Eynon in the first half, Shimano in the second (6 of
  8), Eynon again in the postseason (5 of 8); 9-9 over the whole season.
- **The changes are at the corners, 2B and LF**, which batting decides under
  2+2 anyway: LAQ 3B Lansdell -> Eynon (Lansdell to RF), back for the
  postseason; LAQ 2B Hondras -> Benitez -> Shimano/Benitez; LAQ LF Maximiliana
  (her conflict, not a benching) -> Villarreal; NYH 2B Izumi -> Ciamarro/Willan,
  LF Ibarra (traded) -> Studer; BOS 2B Blunt -> Yamamoto, 1B Dumais ->
  Schroder in the postseason; SFF 3B Park -> Yamamoto, LF Albayati -> Park.

### Option 4, revealed preference (user leaning, 2026-10-04)

User: the dice game has no defensive factors to justify a weak bat, but that
is no reason for the AI not to use players the way the real managers did. Late
and postseason data. Where a position is evenly split, batting decides.

Counting position by position misses everyday players who moved around: LAQ's
Eynon started 15 of 16 late games (3B, SS, DH) and leads no single position.
Many late/postseason disagreements only swap labels within the same nine (NYH:
Lahners and O'Sullivan between 1B and DH), which the dice game cannot tell
apart. So, proposed (ASSUMPTION, for the user):

1. Window: the second half of the regular season plus the postseason, each
   game once. Late and postseason leaders that disagree are settled by the
   pooled count.
2. The nine: most starts in the window, not counting starts at P. A tie at the
   cut goes to batting.
3. Positions: among the nine, the assignment with the most starts at the
   positions given (eligibility: 2+ starts). Ties go to batting.
4. A starter who is one of the nine bats at P and the team has no DH, as SFF
   (Whitmore) and NYH (Saiki) did. Otherwise the DH is the one left over.
   **Replaced by rule 4' (user, 2026-10-06):** a starter bats at P (no DH)
   when her team batted her -- lineup spot 1-9, not 10 behind a DH -- in more
   than half of her weighted window starts at P. NYH never batted Saiki: a DH
   in all 3 of her starts. Of 11 role starters only Whitmore (9 of 9 starts)
   and Mackay (2 of 2) bat; Albayati batted in 3 of 5, but in 1 of her 3
   window starts (all postseason, weighted 2 of 6), so she does not.
   `usage.bats_at_p`.
5. A regular who is pitching or unavailable: the next by window starts.

The nine this gives (starts in 10 / 16 / 11 / 15 window games), and its cost
in runs over 7 innings against the league pitcher:

| team | in, not in the bats-only nine | out | runs vs bats only |
|---|---|---|---|
| BOS | Padgham, Haas | Kim, De Leija | 6.91 vs 7.28 |
| LAQ | Eynon, Davis, Hondras | Maximiliana, Villarreal, Roche | 7.73 vs 8.15 |
| NYH | Eccles, Perez | Izumi, Ciamarro | 8.45 vs 8.98 |
| SFF | Day-Bedard, A. Yamamoto | Gutierrez, Albayati | 8.46 vs 8.83 |

Ties at the cut settled by batting: BOS Schroder over De Leija (5 starts
each), LAQ Benitez over Villarreal (10 each). Maximiliana falls out only
because her conflict kept her out of the window.

**Decided (user, 2026-10-04):** the nine rule as above; postseason starts
count double; Maximiliana is credited at her start rate until she stopped
appearing (her conflict began then: 8 starts in LAQ's 13 games through 29 Aug,
0.62). Mackay must be in LAQ's lineup -- she is (21 weighted starts), and when
she starts she bats at P.

Built: `src/wpbl/usage.py` and `pixi run manager --conventions`. With
weighting, no tie at any cut. LAQ's ninth is Villarreal (16) over Maximiliana
(14.8) and Benitez (13). Where 2+ starts leaves a position no one in the nine
can fill, the nine bends: BOS with Schroder starting puts Dumais (the regular-
season 1B) at 1B, since no one else with 2+ starts there is free.

Starter by role (ASSUMPTION on the order): a role starter who would take the
mound fresh, the best of them; else the least tired role starter who would not
enter gassed; else the best rested arm of any role (a bullpen game).

In-game moves follow the same eligibility, and one move was missing: a
reliever from the bench while the outgoing pitcher bats (no DH) -- she moves to
a field position and the reliever takes that fielder's slot (Whitmore to CF,
as SFF did). Between moves that bring in the same arm, B0 and B1 now keep the
most bats.

Relief comes from the relief role (user caught B0 bringing in Albayati, an SFF
starter, for Whitmore): with the conventions on, B0 and B1 pick from role
relievers, and a starter only if no reliever can come in. B1's A arms are the
two best relievers: BOS Schiano, Dumais; LAQ Meidlinger, Villarreal; NYH Lee,
Reynolds; SFF Gilder, Coria.

With the conventions on (lineups, roles, relief from relievers), same 2,400
seeded series, opponent B0 with conventions:

| policy | series won | pitchers per game, G1-G5 |
|---|---|---|
| B0 vs B0 | 50.7% | 2.0 2.2 2.7 3.0 3.4 |
| B1 median rule | 51.2% | 2.1 2.3 2.6 3.1 3.8 |

B1's reliefs: A arm 9,077, B arm 3,961, A wanted but both would enter gassed
2,088; 498 plate appearances pitched gassed with no legal arm left (1,673
without conventions). Still no measurable gain over B0.

**Win-or-go-home (user, 2026-10-04):** in a game a team must win to stay
alive, it is justified in using its bullpen in atypical ways -- starters may
relieve. Built as the "guaranteed" reservation below.

**Reservation, built and tested (2026-10-04).** Before each game, plan a
starter for each later game (the best role starter fresh that day, else the
least tired; today's starter excluded). A planned starter -- flex arms
included -- is held out of relief if a typical relief outing (31 pitches,
section 7.4) would leave her short of fresh on her start day; anyone else may
relieve. So in game 1 tomorrow's starter is held, the game-3 starter is not.

In an elimination game only today is guaranteed, so the user's question --
protect the game-5 starter at 1-2, or all hands? -- is a choice between:

- **guaranteed:** hold planned starters only for games sure to be played (all
  hands when facing elimination);
- **next:** also hold the next game's starter whenever it could be played.

B0 in-game for every variant; the opponent B0 with the blanket ban; same 2,400
seeded series. "Brink" = series where the team trailed 0-2 or 1-2 with a game
to play:

| reservation | series won | won from the brink |
|---|---|---|
| ban (no starter relieves) | 50.7% | 16.7% of 1,170 |
| guaranteed | 50.6% | 17.2% of 1,165 |
| next | 50.8% | 17.0% of 1,165 |

No measurable difference, even from the brink (SE about 1.1 there). The
simulator cannot yet say which is better; if there is a difference it is under
about 2-3 points of comeback probability.

### Lineup conventions, measured (2026-10-04)

Expected runs over 7 innings against the league pitcher, best batting order,
the starter out of the lineup:

| team | bats only | 2+3: C/SS/CF to the most-started, else 3+ starts | regulars: most-started at every position |
|---|---|---|---|
| BOS | 7.28 | 7.09 (Padgham SS) | 6.90 |
| LAQ | 8.15 | 7.75 (Foxx C, Eynon SS, Davis CF) | 7.49 |
| NYH | 8.84 | 8.45 (Perez SS, Eccles CF) | 8.32 |
| SFF | 8.83 | 8.83 (same bats, positions moved) | 8.38 |

Option 4 as first stated ("each team's most common real lineup") does not
exist: every team used 16-20 different nines in 17-23 games, and the most
common exact nine started 2-3 times. "Regulars" is its nearest form.

The 3-start threshold was a judgment, not a break in the data. Card
eligibilities by starts at that position: 0 starts 20 (the card also lists
positions played after a mid-game move), 1 start 29, 2 starts 15, 3-4 15,
5-9 31, 10+ 20.

Late-season roles (user: use late-season usage). Starts / relief outings in
each team's last 10 games, postseason included:

- BOS: Blunt 3/2, Schroder 3/1, Benach 2/2, Schiano 1/4, Bricker 1/4, Dumais 0/6
- LAQ: Roche 3/1, Sato 2/3, Mackay 2/2, Villarreal 1/3, Hondras 1/2, Shimano 1/2, Meidlinger 0/5, Baird 0/1
- NYH: Kim 5/0, Saiki 3/1, Eccles 1/4, O'Sullivan 1/4, Lee 0/4, Studer 0/3, Reynolds 0/2, Zettlemoyer 0/1, Izumi 0/1
- SFF: Whitmore 4/0, Albayati 3/0, Eckert 2/2, Gilder 1/5, Coria 0/5, del Castillo 0/4, Day-Bedard 0/3, Leblanc 0/2

## Decided by the user (2026-10-04, third round): v2 direction

- **About 2-3 decisions a game:** who starts, and who relieves when a pitcher
  is gassed. What is really being decided is how many batters each arm faces.
- **No swapping for freshness.** A fresh arm being better is not a reason to
  change: the 30-pitch entry cost is there to deter frequent changes,
  especially in a best-of-5 whose schedule tests the bullpens. (v1's greedy
  policy used 4-6 arms a game; this rules that out.)
- **Lookahead:** at least until the pitcher in question is gassed, or the game
  ends.
- **Median-WP rule (B1):** 2 A arms per team to start. The final rule may need
  to depend on the staff's current fatigue.
- **Series stakes:** combine the game WP with the series state. Losing game 1
  is not losing the game that ends the series.

What that means in numbers, at a coin flip per game (best of 5):

| before the game | series leverage: P(series) if win minus if lose |
|---|---|
| 0-0, 1-0, 0-1 | 0.375 |
| 2-0, 0-2 | 0.25 |
| 1-1, 2-1, 1-2 | 0.5 |
| 2-2 | 1.0 |

Guaranteed games: from (a, b) wins, the next 3 - max(a, b) games are certain to
be played. At 0-0 that is games 1-3; at 1-1, games 3 and 4; at 2-x, only the
next one. A game that is not guaranteed is weighted by the chance it is reached
(game 5 from 0-0: 0.375).

**Proposed v2 (ASSUMPTION, for the user):**

1. Decision points: the start, and each plate appearance while the pitcher is
   gassed. Choices there: ride her, or bring in Y.
2. Value, in series-win probability: leverage of this game x the change in
   game WP, minus lambda_p x the slack each arm loses for later games, each
   game weighted by its chance of being played. Bringing in Y is valued with
   Y pitching until she is gassed or the game ends (exact chain with her pitch
   count), then B0.
3. Rotation: before each game, a planned starter for every remaining
   guaranteed game; she does not relieve if that leaves her above 0 (not
   fresh) when she starts.
4. B1 as a second baseline, at the same decision points: when the pitcher is
   gassed, an A arm if the stakes beat the cost, otherwise a B arm; she is
   always relieved. No hard leverage cut (the user doubted one at 0.5):

       A arm if  L x (1 - leader WP)  >=  k x F

   L is the series leverage, F the expected number of later games, and k is
   set per half-inning so that game 1 (0-0) reproduces the median rule exactly.
   Relative to game 1 the bar on (1 - leader WP) scales by (F/L)/(F0/L0):

   | before | game | L | F | bar vs game 1 |
   |---|---|---|---|---|
   | 0-0 | G1 | 0.375 | 3.125 | 1.00 |
   | 1-0, 0-1 | G2 | 0.375 | 2.125 | 0.68 |
   | 2-0, 1-1, 0-2 | G3 | 0.25-0.5 | 0.75-1.5 | 0.36 |
   | 2-1, 1-2 | G4 | 0.5 | 0.5 | 0.12 |
   | 2-2 | G5 | 1.0 | 0 | 0 (always an A arm) |

   F counts games, not fatigue: v2 replaces it with the slack actually lost on
   the calendar (tomorrow's game costs more than one in four days).

## Conventions

- **(a) Positions.** Eligibility is "positions on her card", and the card's C
  is exactly who caught in 2026 (user: any of them may catch).
- **(b) Disfavored pitchers.** Decided above; the candidates as reviewed:
  Rule used to find them: pitched in the regular season, last outing a week or
  more before it ended (6 Sep), and no postseason outing. Postseason games per
  team: LAQ 8, SFF 7, NYH 3, BOS 2, so absence from the postseason is weak
  evidence for BOS and NYH.

| team | pitcher | reg IP (GS) | last outing | note |
|---|---|---|---|---|
| BOS | Raine Padgham | 7.2 (2) | 15 Aug | |
| BOS | Denver Bryant | 2.1 (0) | 20 Aug | one outing |
| LAQ | Thaima Maximiliana | 8.0 (1) | 29 Aug | none in 8 postseason games |
| LAQ | Maggie Foxx | 2.1 (0) | 22 Aug | |
| LAQ | Adelaide Frank | 1.0 (0) | 14 Aug | one outing |
| LAQ | Brittany Apgar | 0.2 (0) | 7 Aug | one outing |
| NYH | Jacqui Reynolds | 12.0 (2) | 30 Aug | |
| NYH | Jaida Lee | 17.1 (2) | 29 Aug | injured (foot): out, not disfavored |
| NYH | Suzu Narasaki | 1.1 (1) | 14 Aug | pitched for LAQ before the trade |
| NYH | Keira Izumi | 4.0 (1) | 19 Aug | one postseason out (0.2 IP); probably not disfavored |
| SFF | Jua Park | 1.2 (0) | 4 Sep | none in 7 postseason games |
| SFF | Jordan Eyster | 0.0 (1) | 30 Aug | "started", faced no batter, then played LF |

Not listed: Alli Schroder (BOS, 15.2 IP, last 5 Sep, BOS played only 2
postseason games) and Alyssa Zettlemoyer (NYH, last 3 Sep).

## Open questions

1. Jordan Eyster's start with no batter faced: feed error, or an opener who
   never threw? (Moot for the AI: she has no pitcher card.)
2. Izumi can pitch (user). Whether NYH would choose to use her is a
   convention question; for now she is in the pool.
