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
  the pitcher's card on 00-32, shared lines on 33-44 and the batter's card on
  45-99, with steals by the steal table.
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
  and DH; 2B 7.011, SS 6.597; LF and CF pooled, 6.925, since they share a
  pool (players who started at both made 38 of LF's 80 starts and 39 of
  CF's), while RF stands apart (11 and 10 with LF, all fringe).

The numbers that matter are the positive ones: what a team gains if it could
find a bench bat, or an average one, who can also field the position.

| team | pos | regular | vs replacement | vs average |
|---|---|---|---|---|
| LAQ | CF | Davis | +0.235 runs, +3.2 series | +0.244, +3.3 |
| NYH | CF | Eccles | +0.235, +2.7 | +0.243, +2.8 |
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
- **At SS the benchmarks invert:** the average SS (6.597) bats below the
  bench, so "vs average" is the easier bar there; at LF/CF (6.925) the two
  nearly agree.

The negative cells are each regular's batting runs above the benchmark. The
largest: Benites (NYH C) -0.890 vs replacement, -0.796 vs average; Lansdell
(LAQ 3B) -0.414 / -0.320; Lahners (NYH DH) -0.368 / -0.276; SFF CF (Whitmore
58% of days, Day-Bedard 42%) -0.362 / -0.355; Leblanc (SFF 1B) -0.346 /
-0.252; Jorge (SFF C) -0.327 / -0.233.

Cautions: each positional average rests on 80 starts and in effect four
regulars, so differences under about 0.1 run are not meaningful. C is the
most skewed: the min rule sets it to the league average, so "vs average"
understates how scarce catchers are (only 7 players caught).

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
