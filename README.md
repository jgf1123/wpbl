# wpbl

The inaugural 2026 Women's Pro Baseball League season, studied three ways:

1. **Data.** A local copy of the league's public stats feed, rebuilt into
   parquet tables and reconciled against the feed's own known errors.
2. **Analysis.** Run expectancy, win probability, linear weights, pitcher
   usage and fatigue, the running game, batting orders. These were written up
   as blog posts.
3. ***Two Outs, So What?*** (TOSW). A dice-and-cards board game whose player
   cards come from that analysis. It is played by a script, managed by a
   computer manager, and used to simulate alternative postseasons that get
   written up game by game.

The raw JSON in `data/raw/` is the source of truth. Everything in
`data/tables/` is derived and can be rebuilt offline, so answering a new
question never means scraping again. **The season is complete. No more data
is coming.**

## Where things are

| | |
|---|---|
| `src/wpbl/` | the library behind every `pixi run` task |
| `analysis/dice/`, `analysis/manager/` | one-off experiments behind the specs, each folder indexed by its own README |
| `dice_game_spec.md` | how the cards are built, with every alternative tested |
| `Two_Outs_So_What_rules.md`, `Two_Outs_So_What.md` | the rulebook and its design notes |
| `tosw_play_spec.md` | automated play (`pixi run play`) |
| `manager_spec.md` | the computer manager and its series experiments |
| `stolen_base_spec.md`, `bullpen_spec.md` | stolen-base findings; the bullpen simulator TOSW replaced |
| `*_post.md` | blog-post drafts; `style_guide_post.md` is the house style |
| `data/dice/` | printed cards (CSV and PDF), one folder per card version, changelog in `dice_version.md` |
| `games/` | TOSW game logs; `games/postseason_NNNNNN/` holds simulated postseasons with `.jsonl` sidecars and `.facts.md` sheets |
| `data/sim/` | per-game, per-decision output of manager experiments |

## Commands

### Data

```bash
pixi run scrape      # schedule + box scores (incremental; --activity for TrackMan, --force to refetch)
pixi run build       # raw JSON -> parquet tables
pixi run check       # reconcile the tables against the raw feed
pixi run refresh     # all three
pixi run games       # date / teams / score / game_id -> data/games_lookup.csv
```

A game is refetched only when the feed's `updated_at` changes or the copy on
disk is of a game that had not finished.

### Season analysis

```bash
pixi run rosters / timeline / positions / chart   # who played where, and how usage changed
pixi run innings / re / markov                    # runs by inning; run expectancy two ways
pixi run wp / wpq / teams / team-chart            # win probability, one state, team strength
pixi run upsets / rollercoaster / pwp / timeline-chart <game_id>
pixi run blowouts / leverage
pixi run bullpen / relievers / depth / pitches / workload
pixi run batters / weights / batter-chart out.png
pixi run pitchers / pitcher-chart out.png
pixi run defense / running                        # runs saved by fielders; the running game
```

### Batting orders

```bash
pixi run python -m wpbl.steal_ratings / lineup_model / lineup [BOS ...] / lineup_start / lineup_state
```

### Two Outs, So What?

```bash
pixi run dice            # player cards -> data/dice/ (dice_game_spec.md s3)
pixi run advance         # base-running per card line x base-out state
pixi run card-runs       # context-neutral runs per PA for each printed card
pixi run engine          # the game by the printed rules, checked against the league
pixi run season-fatigue  # a whole schedule, to test cross-day fatigue
pixi run play new|<log>|suggest|export   # play a game from a log file (tosw_play_spec.md)
pixi run manager         # series experiments for the computer manager
pixi run postseason [--log games/sim]    # simulate the 2026 bracket with the manager
pixi run facts <folder|jsonl>            # fact sheet per simulated game, for write-ups
```

### Utilities

```bash
pixi run table out.png table.md   # markdown table -> 728px PNG
```

The series experiments take 5–15 minutes. Run one process at a time, with
`OMP_NUM_THREADS=1`.

## The season

1 August to 22 September 2026: 4 teams, one ballpark. 30 regular-season games
ran 1 Aug to 6 Sep, with every pair of teams meeting five times. 10
postseason games followed: best-of-3 semifinals 9–14 Sep and a best-of-5
final 16–22 Sep. The feed also carries a phantom duplicate of every game and
one orphan row (see below).

**Regulation is 7 innings**, not 9. Anything that scales with game length
(innings per start, times through the order, bullpen usage) has to be read
against 7.

## Tables

| table | grain | rows |
| --- | --- | --- |
| `games` | scheduled game | 71 |
| `team_games` | team × game, with box score totals | 80 |
| `line_score` | team × game × inning | 566 |
| `batting` | player × game | 966 |
| `pitching` | pitcher × game, starter/reliever tagged | 233 |
| `pitching_stints` | continuous run on the mound, with entry context | 233 |
| `fielding` | player × game | 966 |
| `players` | feed `player_id` (70 people) | 143 |
| `plays` | play | 3,723 |
| `pitch_events` | pitch | 10,574 |
| `tracking` | TrackMan event | 766 |

Counting stats absent from the feed are stored as 0, since the feed omits a key
rather than sending zero. Rates (`obp`, `whip`, …) and decisions (`win`, `loss`,
`save`) stay null when absent, where missing genuinely means not applicable.

### Identity: use `person_id`, not `player_id`

`player_id` is per-team. The feed mints a **new** one when a player changes
teams, and three players have (Diana Ibarra, Emi Saiki, Suzu Narasaki, all
between LA and NY). It also spells one player two ways under a single id
("Maggie Fox" once, "Maggie Foxx" twelve times; Foxx is correct).

So neither key alone identifies a person. `person_id` unions ids that share an
id and ids that share a name; `person_name` is the most-used spelling. **Group
season-long player aggregates on `person_id`.** Grouping on `player_id` splits a
traded player in two.

### Starting lineups

`batting.in_starting_lineup`, `lineup_spot`, and `lineup_position` come from the
feed's posted lineup, matched on name. Do not match on the player's own
`position` field — it lists every position she played that game ("lf/p"), so
anyone who moved mid-game would fail to match. Every team-game posts 9, or 10
when a DH is used and the pitcher is carried at spot 10.

### Starters and relievers

`pitching.role` is `SP`/`RP`, from the box score's `gs` flag. `appear_order` is
the order she took the mound. Both agree with the play-by-play in all 80
team-games, and no pitcher ever re-entered after leaving.

`pitching_stints` adds what the box score cannot: the inning, out, and score at
which each reliever entered, and how many runners were already on.

### Which games each analysis reads

`tables.read(name, scope)` has three scopes:

| scope | games | used by |
| --- | --- | --- |
| `default` | `WPBL_GAMES`: regular season unless set to `all` | descriptive season tables |
| `training` | every game except `tables.TRAINING_EXCLUDED` | model fits: run expectancy, Markov chain, win probability, team strength, leverage calibration, linear weights, FIP weights and constant, the bullpen logistic model, the blowout threshold |
| `all` | every game | pitcher workload and pitch counts (fatigue) |

`TRAINING_EXCLUDED` holds semifinal G3 (14 Sep, `r1slo258zh4c0mwg`, LAQ 15–11).
Both bullpens were exhausted, which shows in the high on-base rate and run total,
so it would skew league and team averages and is kept out of every model fit.
For the same reason it is useful data on how fatigued pitchers perform: its
pitches count toward workload, and fatigue work should read it. Training therefore covers 39 games, the 30-game regular
season plus nine of the ten postseason games.

Where a report is both a fit and a season table, only the fit moves. The batter
and pitcher tables, the defense split and the blowout list still report
regular-season plays, but price them with weights, run expectancy and league
constants fit on the training games. The bullpen report is the logistic model's
own data, so all of it uses the training games.

### Estimating on 39 games

`run_expectancy.py` builds the standard 24-cell matrix and then prints the
reasons not to trust it: 7 cells hold fewer than 50 observations, and nine
orderings are logically impossible (more outs cannot raise expected runs, and
neither adding a runner nor advancing one can lower them),
so those cells are measuring sampling noise. Use the pooled four-group table it
also prints, and treat differences under ~0.3 runs as indistinguishable.

`win_probability.py` confines the thin matrix to one half-inning. The base-out
state only affects the half-inning in progress; every later half-inning starts
bases-empty and is drawn from one distribution estimated on 506 half-innings.
Within the half-inning in progress, runs to its end come from the Markov chain
(`markov.run_distributions`), the same chain behind the run expectancy used
everywhere else, rather than from each state's own record blended toward its
group. In 10-fold cross-validation by game on the 30 regular-season games, the
chain predicted held-out runs-to-end-of-inning better than that blend at any
strength (by about 146 log points over 2,056 plate appearances against the best
blend, SE 51), and blending it back toward each state's own record only made it
worse.

One state is exempt. Bases empty, nobody out *is* a fresh half-inning, so it uses
the 506 observed half-innings rather than the chain's estimate of the same thing:
they agree within sampling error (51.2% scoreless against the chain's 52.6%, on a
standard error of 2.2), leave-one-game-out win probability could not tell them apart
when this was decided on 34 games (Brier 0.1744 against 0.1739, SE 0.0006), and the direct measurement needs no
memorylessness assumption. Holding a single distribution for that state also keeps
the model coherent. While the boundary tables used the observed half-innings and a
query rebuilt the same inning from the chain, P(home wins) and P(away wins) with
the teams swapped did not sum to 1. `validate()` now checks that a query at the
start of a half-inning returns exactly the boundary table's value.

"A runner must help" still fails in 10 of 462 comparisons, 8 of them in the 7th,
where one run decides the game and the chance of scoring at least once matters
more than the average. The largest, 0.037, is the bottom of the 7th with 1 out,
where a runner on third outranks first and third. The chain cannot fix this
because a state's first step still rests on its own plays: runner on third with
nobody out has 9, and none was an out with the runner holding.

Note the run environment before importing any outside table: this league scores
about 1.09 runs per half-inning from bases empty and nobody out, roughly double
a major-league figure, so an MLB run-expectancy or win-probability table would be
wrong here by about a factor of two.

## What the feed gets wrong

Found by reconciling the tables against the feed and confirmed across all 40
games. `pixi run check` re-asserts each of these on every build.

**Start times are an hour early.** For 2026 `scheduled_start` is one hour before
first pitch. `games.first_pitch_utc` and `first_pitch_local` are corrected;
`scheduled_start_raw_utc` keeps the original. Recheck for any later season.

**Pitch codes `P` and `K` are mislabelled.** The feed calls `P` a pitchout and
`K` unknown. `P` is a ball put *in play* — 1,855 of 1,858 batted-ball outcomes end on
it, and the other 3 look miscoded at source (the cut-short game below adds 23
more) — and `K` is a *called strike*: all 330 strikeouts end on `K` or `S`
(swinging), and all 358 walks end on `B`. `pitch_events.result` is the corrected label;
`feed_type` keeps the original.

**`runs_scored` omits the batter's own run.** A solo home run comes back as 0
runs and `is_scoring_play: false`. `plays.runs_scored` adds the batter's run
back on home runs, which reconciles 564 of 566 half-innings against the line
score; `runs_scored_feed` keeps the raw value. The running score columns are
re-anchored to the line score at each half-inning boundary, so they are exact at
every boundary and cannot drift.

**`event_type: "unknown"` is a grab bag.** 675 plays, mixing real plate
appearances (reaching on an error, infield flies) with substitutions, pitching
changes, pickoffs, balks, and extra-inning placed runners. `plays.play_kind`
splits them, and `is_plate_appearance` ties exactly to batters faced in all 80
team-games.

**Some `out` rows are outs on the bases, not at the plate.** Three rows read
like "out at third p to 3b, picked off". A real trip to the plate always carries
a ball-strike count in parentheses; these do not.

**The `position` field does not reliably include `p`.** Jua Park is listed
`3b/cf` in a game where she pitched to nine batters. Identify pitchers from the
`pitching` table, and two-way players from whether they batted in games they did
not pitch — not from this field.

**Roster rows for players who did not appear carry an empty `player_id`** — 248
of 833 rows, in every game. None of them has a hitting, pitching, or fielding
line, so no stat row is affected. Ids are pooled by (team, name) across games
anyway, and `player_id_source` records whether an id came from the feed or was
recovered. `pixi run check` lists the roster names that never carry an id
anywhere; none of those entries has a stat row.

**Every played game has a phantom duplicate.** A stale never-played copy with
the same date and matchup, stuck on "Not Started". `games.is_phantom_duplicate`
flags all 30; filter on it or on `is_final`.

**Pitch strings are cut short in one game.** In SF–BOS semifinal G1 (9 Sep,
`ucwyhv1ki318nni5`, listed in `parse.PITCH_STRING_GAPS`) 32 of 66 plate
appearances carry a string that cannot have produced their result (a walk
without four balls, a ball in play not ending on P), mostly in innings 1–4. The
box-score pitch counts come from the same strings, so they are too low.
`parse.estimate_pitch_counts` fills each cut-off plate appearance with the mean
length of complete strings from other games with the same kind of result and at
least as many pitches as were recorded. The estimates sit beside the feed's
counts, never replacing them: `plays.n_pitches_est` (flag
`n_pitches_estimated`), `pitching.pitches_est`, `pitching_stints.pitches_est`.
Blunt 66 → ~99, Whitmore 70 → ~101, Bricker 30 → ~35; the game ~283 pitches
against a league mean of 267. Workload, pitch counts and the bullpen model read
the estimates; `pixi run check` checks the feed's own counts.

**A pitcher is sometimes named "/".** Championship G2 (17 Sep,
`3q3q8b72pszobk7b`) names the pitcher "/" for the seven plays of the top of the
7th after Andreanne Leblanc took the mound; her box-score line (6 batters faced,
3 outs) matches them exactly. Any pitcher name that resolves to nobody is taken
to be whoever was last on the mound that half-inning. `plays.pitcher_inherited`
flags those rows, `plays.pitcher_name_feed` keeps what the feed said, and
`pixi run check` lists every one. The rule is re-applied on each build, so a
corrected feed simply stops triggering it.

**Postseason box scores sometimes drop accents or misspell names.**
Postseason games carry new player ids, and ids join only through a shared
spelling, so "Ela Day-Bedard", "Maika Dumais" and "Thaima Maximiliana" each
became a second person. Roster entries in six games also spell Suzu Narasaki
"Naraski", and single games misspell five more (Alexi Jorge, Gabriella Haas,
Maggie Fox, Emi Saki, Isabella Villareal) under the right ids. All are corrected
in `parse.RAW_NAME_FIXES`, matching whole names only, so "Maggie Fox" never
turns "Maggie Foxx" into "Foxxx". `pixi run check` fails if two people ever
share a name apart from accents; a pairwise edit-distance sweep of every
spelling in the tables (17 Sep) found nothing further within three letters.

**Handedness contradicts itself between games.** Every box-score player row
carries `bats` and `throws`, but 10 of 80 players are listed more than one way:
Jordan Eyster is R/R in some games and L/L in others. Both columns are resolved
to the person's most-used value, like a misspelled name, and stamped on
`players`, `batting`, `pitching` and `fielding`, so a matchup can be read off
any of them. Of the league's 70 people, 51 bat right, 17 left and 2 switch, and
57 throw right and 13 left; of the 40 who pitched, 30 are right-handed and 10
left-handed.

**The box score's tracking is capped at 200 events.** `/games/{id}/activity` is
the uncapped source and adds hit distance. The `tracking` table comes from
there. Only 2 games have any tracking, and more may never arrive — treat its
absence as normal.

## Known gaps in the data

Real losses in the feed, not parsing artifacts.

- **`dtksss0az7dpa97f`**: 14 plays across innings 5–7 lost their narrative and
  batter name, keeping only the pitch sequences. They are counted as plate
  appearances with an unknown outcome (`play_kind = plate_appearance_unknown`),
  which makes the game's team-level batters faced tie. Their outcomes and 3 hits
  are unrecoverable, and the feed misassigns one of them between two pitchers,
  so per-pitcher totals for that game are off by one.
- **`mksw641s8uwrx6vp`**, 1st inning: a narrative is truncated mid-sentence,
  losing one run.
- The feed's per-pitcher `pitches` differs by 1–4 from the length of its own
  pitch strings for 5 of 233 pitcher-games, by at most 6.

## Open judgement: attributing errors and hit-by-pitch

Unsettled, recorded here rather than buried in a constant. It decides the
middle of the batter table (`pixi run batters`) and nothing at the ends.

**Reaching on an error** — 54 plate appearances, **2.51%**, one in forty, and
roughly four to five times the major-league rate because this league makes a
lot of errors. Two defensible treatments:

| `--error=` | The claim it makes |
|---|---|
| `credit` (default) | value it at its own run value, +0.533 — what RE24 does natively, and what the original wOBA does |
| `drop` | remove the plate appearance from the rate: the fielder's doing, not attributable to the batter |

A note on the literature, because it is easy to get backwards. Tango's original
wOBA carries a reached-base-on-error term. The familiar public formula omits
it, which leaves ROE an at-bat with no numerator weight — arithmetically an
out. That omission is a **data-availability compromise**, since ROE is not in
standard historical stat lines, and not a judgement that the event is
worthless. There is no third option here pricing ROE as an out; an earlier
draft had one on the strength of that misreading.

**The case for crediting rests on value, not skill.** ROE is worth +0.533 runs,
against +0.614 for a single and −0.584 for an average out — about 87% of a
single and **1.12 runs better than the out** it is conventionally priced as.
Pricing all 54 as outs would misassign ~60 runs.

**It is not established as a batter skill**, and an earlier version of this
section said it was. A variance decomposition finds about half the spread
between batters to be real, but leave-one-out shows that rests on one player:
Suzu Narasaki reached on an error 4 times in 20 plate appearances, and without
her the talent share falls from **48% to 2%**.

**Hit by pitch** — 74 plate appearances, 3.4%, roughly triple the major-league
rate and concentrated: five batters are above 11%. Crediting it is conventional
and internally consistent, because a walk and a hit batter put the same runner
on first and force runners identically; crediting walks while dropping HBP
cannot be justified. Unlike ROE, **HBP holds up as a batter skill**: about 54%
of the spread between batters is real, and it survives leave-one-out — removing
any single batter leaves at least 47%. So it is credited and **pooled with walks
into one "free pass" weight** (n=446 in the training games). Weighted apart
they come out +0.483 for a hit batter and +0.457 for a walk. The events are
identical on the bases, so the gap is situational noise in a 98-event weight. `--hbp=split` or `--hbp=drop` to see it the other ways.

### Both columns cover the same plate appearances

Because ROE is credited by default, RE24 and the context-neutral column are
computed over the same set. That matters for two reasons: RE24 keeps its ledger
property — every plate appearance's value is charged to someone and the totals
reconcile against real scoring — and the gap between the columns means
sequencing alone, rather than sequencing plus a difference in which plate
appearances each column saw.

### What it actually changes

Rank correlations across the option grid stay above **+0.98**, and the two
columns agree at **+0.925**. No qualified batter's rating moves more than 0.10
across the options, the threshold for the table's `!` flag; the largest swing is
Lahners at 0.077. (On the 34-game fit four batters were flagged: Day-Bédard,
Narasaki, Kim and Zettlemoyer.)

### The wider problem this is a case of

A linear weight is only context-neutral if that event's mix of situations
matches the league's. Rare events do not have the occurrences to guarantee it:
home runs (57), HBP (74), reached-on-error (54). Their weights carry
situational noise. Pooling walks with HBP is one fix. Re-weighting each event's
situations to the league distribution would be a more thorough one, and is
**not** done.

## Source

`https://stats.womensprobaseballleague.com/v1` — no key, no signup. Endpoints:
`/games`, `/games/{id}/boxscore`, `/games/{id}/activity`. Documented at
<https://sportydolphin.fun/wpbl/api>, a fan project not affiliated with the
league. CORS blocks browser calls; scrape server-side.
