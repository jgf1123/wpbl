# wpbl

Local copy of the WPBL public stats feed, plus tidy tables built from it.

The raw JSON in `data/raw/` is the source of truth. Everything in `data/tables/`
is derived and can be rebuilt offline, so answering a new question never means
scraping again.

## Usage

```bash
pixi run scrape      # schedule + box scores (incremental)
pixi run build       # raw JSON -> parquet tables
pixi run check       # reconcile the tables against the raw feed
pixi run refresh     # all three
pixi run games       # date / teams / score / game_id -> data/games_lookup.csv

pixi run rosters     # who pitched, for whom, in what role
pixi run timeline    # how each team's use of its players changed over the season
pixi run chart       # data/usage.html - which innings each pitcher covered
pixi run innings     # runs scored and allowed per inning, by team
pixi run re          # run expectancy by base-out state, with its diagnostics
pixi run wp          # win probability, with structural checks and calibration
pixi run upsets      # games where a heavily favoured team lost, and the swings
pixi run pwp         # win probability added per pitcher, by stint on the mound
pixi run blowouts    # half-innings of 4+ runs, and the threshold behind it
pixi run leverage    # the leverage index, calibrated so an average inning = 1.00
pixi run bullpen     # kept in or replaced at the inning boundary
pixi run relievers   # who gets the call, and how good they are
pixi run depth       # was there a good arm available in high-leverage spots
pixi run pitches     # pitches per game, per start, per stint
pixi run batters     # RE24 and context-neutral value per plate appearance
pixi run timeline-chart <game_id>   # win probability chart for one game
```

`pixi run scrape --activity` also pulls TrackMan tracking. `--force` refetches
everything. A game is refetched only when the feed's `updated_at` changes or the
copy on disk is of a game that had not finished.

## Data as of 2026-09-06

61 scheduled games, of which 29 are played and complete, 31 are phantom
duplicates, and 1 is unplayed or in progress. 4 teams,
71 players, 2761 plays, 7828 pitches. TrackMan tracking exists for 2 games.

**Regulation is 7 innings**, not 9 — 24 of the 29 completed games went exactly
7, four went 8, and one was cut to 6 by weather. Anything that scales with game
length (innings per start, times through the order, bullpen usage) has to be
read against 7.

## Tables

| table | grain | rows |
| --- | --- | --- |
| `games` | scheduled game | 50 |
| `team_games` | team × game, with box score totals | 48 |
| `line_score` | team × game × inning | 340 |
| `batting` | player × game | 585 |
| `pitching` | pitcher × game, starter/reliever tagged | 136 |
| `pitching_stints` | continuous run on the mound, with entry context | 136 |
| `fielding` | player × game | 585 |
| `players` | player | 73 |
| `plays` | play | 2,265 |
| `pitch_events` | pitch | 6,408 |
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
traded player in two; counting distinct names reports 39 pitchers where there
are 38.

### Starting lineups

`batting.in_starting_lineup`, `lineup_spot`, and `lineup_position` come from the
feed's posted lineup, matched on name. Do not match on the player's own
`position` field — it lists every position she played that game ("lf/p"), so
anyone who moved mid-game would fail to match. Every team-game posts 9, or 10
when a DH is used and the pitcher is carried at spot 10.

### Starters and relievers

`pitching.role` is `SP`/`RP`, from the box score's `gs` flag. `appear_order` is
the order she took the mound. Both agree with the play-by-play in all 48
team-games, and no pitcher ever re-entered after leaving.

`pitching_stints` adds what the box score cannot: the inning, out, and score at
which each reliever entered, and how many runners were already on.

### Estimating on 24 games

`run_expectancy.py` builds the standard 24-cell matrix and then prints the
reasons not to trust it: 14 cells hold fewer than 50 observations, and five
orderings are logically impossible (adding a runner cannot lower expected runs),
so those cells are measuring sampling noise. Use the pooled four-group table it
also prints, and treat differences under ~0.3 runs as indistinguishable.

`win_probability.py` is where the thin matrix stops mattering. The base-out
state only affects the half-inning in progress; every later half-inning starts
bases-empty and is drawn from one distribution estimated on 288 half-innings.
Backward induction over half-inning boundaries then averages the base-out noise
down instead of compounding it -- the residual breaches of "a runner must help"
have a median size of 0.0045, and the five above 0.01 are all in the 7th, where
no future innings remain to damp them.

Note the run environment before importing any outside table: this league scores
about 1.08 runs per half-inning from bases empty and nobody out, roughly double
a major-league figure, so an MLB run-expectancy or win-probability table would be
wrong here by about a factor of two.

## What the feed gets wrong

Found by reconciling the tables against the feed and confirmed across all 24
games. `pixi run check` re-asserts each of these on every build.

**Start times are an hour early.** For 2026 `scheduled_start` is one hour before
first pitch. `games.first_pitch_utc` and `first_pitch_local` are corrected;
`scheduled_start_raw_utc` keeps the original. Recheck for any later season.

**Pitch codes `P` and `K` are mislabelled.** The feed calls `P` a pitchout and
`K` unknown. `P` is a ball put *in play* — all 1,131 batted-ball outcomes end on
it — and `K` is a *called strike*: strikeouts end on `K` or `S` (swinging), and
all 215 walks end on `B`. `pitch_events.result` is the corrected label;
`feed_type` keeps the original.

**`runs_scored` omits the batter's own run.** A solo home run comes back as 0
runs and `is_scoring_play: false`. `plays.runs_scored` adds the batter's run
back on home runs, which reconciles 338 of 340 half-innings against the line
score; `runs_scored_feed` keeps the raw value. The running score columns are
re-anchored to the line score at each half-inning boundary, so they are exact at
every boundary and cannot drift.

**`event_type: "unknown"` is a grab bag.** 444 plays, mixing real plate
appearances (reaching on an error, infield flies) with substitutions, pitching
changes, pickoffs, balks, and extra-inning placed runners. `plays.play_kind`
splits them, and `is_plate_appearance` ties exactly to batters faced in all 48
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
recovered. Three roster names never carry an id anywhere and never played.

**Every played game has a phantom duplicate.** A stale never-played copy with
the same date and matchup, stuck on "Not Started". `games.is_phantom_duplicate`
flags all 24; filter on it or on `is_final`.

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
  pitch strings for 3 of 136 pitchers.

## Open judgement: attributing errors and hit-by-pitch

Unsettled, recorded here rather than buried in a constant. It decides the
middle of the batter table (`pixi run batters`) and nothing at the ends.

Two events are not clearly the batter's doing.

**Reaching on an error** — 51 plate appearances, 2.5%, high because this league
makes a lot of errors. Three defensible treatments, none obviously right:

| `--error=` | Effect | The claim it makes |
|---|---|---|
| `drop` (default for the neutral column) | remove the PA from the rate | we cannot attribute it, so we decline to — understates any real component, since hard contact and speed do generate errors |
| `credit` | value it at +0.541, near a single | what RE24 does natively — overstates the batter, it is mostly the defence's doing |
| `out` | value it at −0.557, as wOBA does | the batter earned a debit for a ball the defence muffed — the strongest claim, and not the default |

**Hit by pitch** — 71 plate appearances, 3.4%, roughly triple the major-league
rate and concentrated: five batters are above 11%. Crediting it is conventional
and internally consistent, because a walk and a hit batter put the same runner
on first and force runners identically; crediting walks while dropping HBP
cannot be justified. So it is credited, and **pooled with walks into one "free
pass" weight** (+0.400, n=339). Weighted apart they come out +0.462 and +0.384,
a gap of +0.078 with 95% interval [+0.010, +0.150] — distinguishable, but the
events cannot differ mechanically, so the gap is situational contamination of a
71-event weight, not a real difference. `--hbp=split` or `--hbp=drop` to see it
the other ways.

### Why the two columns get different defaults

RE24 always uses every plate appearance; `--error` governs only the
context-neutral column. The asymmetry is deliberate and follows from what each
column is for:

- **RE24 is a ledger.** Every plate appearance's value is charged to someone
  and the totals reconcile against real scoring. Dropping the 51 error plate
  appearances would delete **+27.6 runs** of genuine contribution from the books
  without reassigning it.
- **Context-neutral is a rate estimate.** There is no ledger to keep, so an
  unattributable outcome is better left out than guessed at.

This is a judgement, not a result, and the competing view — that both columns
should cover the same plate appearances — is coherent. Worth knowing before
re-litigating it: the gap column barely notices. Computing it with both columns
on all plate appearances versus both on the dropped set differs by **0.005** per
batter.

### What it actually changes

Rank correlations across the whole option grid stay between **+0.92 and +0.98**.
The top three (Benites, Whitmore, Lansdell) and bottom three (Blunt, Padgham,
Eccles) are stable under every combination. Seven batters are not, and the table
flags them with `!`: Narasaki (moves 0.220), Kim (0.150), Zettlemoyer (0.144),
Park (0.139), Day-Bédard (0.139), Mackay (0.120), Lahners (0.114).

Lahners in particular swings from +0.156 to +0.042 between the loosest and
strictest settings — enough to move her from fourth to mid-table.

### The wider problem this is a case of

A linear weight is only context-neutral if that event's mix of situations
matches the league's. Rare events do not have the occurrences to guarantee it:
home runs (55), HBP (71), reached-on-error (51). Their weights carry situational
noise. Pooling walks with HBP is one fix. Re-weighting each event's situations
to the league distribution would be a more thorough one, and is **not** done.

## Source

`https://stats.womensprobaseballleague.com/v1` — no key, no signup. Endpoints:
`/games`, `/games/{id}/boxscore`, `/games/{id}/activity`. Documented at
<https://sportydolphin.fun/wpbl/api>, a fan project not affiliated with the
league. CORS blocks browser calls; scrape server-side.
