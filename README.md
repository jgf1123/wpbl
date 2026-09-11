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
pixi run workload    # rolling 7-day pitch load, rest between starts, staff weeks
pixi run batters     # RE24 and context-neutral value per plate appearance
pixi run pitchers    # RE24 per batter faced, beside a league-calibrated FIP
pixi run timeline-chart <game_id>   # win probability chart for one game

pixi run table out.png table.md     # render a markdown table as a 728px PNG
```

`pixi run scrape --activity` also pulls TrackMan tracking. `--force` refetches
everything. A game is refetched only when the feed's `updated_at` changes or the
copy on disk is of a game that had not finished.

## Data as of 2026-09-10 — regular season complete

61 schedule rows, of which 30 are the real regular season, 30 are phantom
duplicates, and 1 is an orphan row with no teams. 4 teams, 71 players,
2845 plays, 8078 pitches. TrackMan tracking exists for 2 games.

The season ran 1 August to 6 September: every pair of teams met exactly five
times, so the schedule is perfectly balanced and there is one ballpark. A
postseason is scheduled but had not appeared in the feed as of 10 September;
`validate.py` fails if a completed game ever lands outside the regular season.

**Regulation is 7 innings**, not 9 — 25 of the 30 completed games went exactly
7, 4 went 8, and 1 was cut to 6 by weather. Anything that scales with game
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

### Estimating on 30 games

`run_expectancy.py` builds the standard 24-cell matrix and then prints the
reasons not to trust it: 8 cells hold fewer than 50 observations, and ten
orderings are logically impossible (more outs cannot raise expected runs, and
neither adding a runner nor advancing one can lower them),
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

**`event_type: "unknown"` is a grab bag.** 562 plays, mixing real plate
appearances (reaching on an error, infield flies) with substitutions, pitching
changes, pickoffs, balks, and extra-inning placed runners. `plays.play_kind`
splits them, and `is_plate_appearance` ties exactly to batters faced in all 60
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
  pitch strings for 5 of 174 pitcher-games, by at most 6.

## Open judgement: attributing errors and hit-by-pitch

Unsettled, recorded here rather than buried in a constant. It decides the
middle of the batter table (`pixi run batters`) and nothing at the ends.

**Reaching on an error** — 54 plate appearances, **2.51%**, one in forty, and
roughly four to five times the major-league rate because this league makes a
lot of errors. Two defensible treatments:

| `--error=` | The claim it makes |
|---|---|
| `credit` (default) | value it at its own run value, +0.547 — what RE24 does natively, and what the original wOBA does |
| `drop` | remove the plate appearance from the rate: the fielder's doing, not attributable to the batter |

A note on the literature, because it is easy to get backwards. Tango's original
wOBA carries a reached-base-on-error term. The familiar public formula omits
it, which leaves ROE an at-bat with no numerator weight — arithmetically an
out. That omission is a **data-availability compromise**, since ROE is not in
standard historical stat lines, and not a judgement that the event is
worthless. There is no third option here pricing ROE as an out; an earlier
draft had one on the strength of that misreading.

Two findings support crediting:

- **It is worth what a single is worth.** +0.547 against a single's +0.566 — a
  difference of −0.019, 95% interval [−0.117, +0.079]. Not distinguishable.
- **It is partly a batter skill.** If reaching on an error were purely the
  defence's doing, batters would differ only by chance. They differ by more:
  roughly half the observed spread is real, with a stabilization point near
  **40 plate appearances** — better measured than batting average (90) or walk
  rate (119). Not settled, though: 18% of bootstrap resamples find no talent
  spread at all.

**Hit by pitch** — 74 plate appearances, 3.4%, roughly triple the major-league
rate and concentrated: five batters are above 11%. Crediting it is conventional
and internally consistent, because a walk and a hit batter put the same runner
on first and force runners identically; crediting walks while dropping HBP
cannot be justified. So it is credited and **pooled with walks into one "free
pass" weight** (n=348). Weighted apart they come out +0.455 and +0.389, a gap
the events cannot produce mechanically, so it is situational contamination of a
74-event weight. `--hbp=split` or `--hbp=drop` to see it the other ways.

### Both columns cover the same plate appearances

Because ROE is credited by default, RE24 and the context-neutral column are
computed over the same set. That matters for two reasons: RE24 keeps its ledger
property — every plate appearance's value is charged to someone and the totals
reconcile against real scoring — and the gap between the columns means
sequencing alone, rather than sequencing plus a difference in which plate
appearances each column saw.

### What it actually changes

Rank correlations across the option grid stay above **+0.9**, and the two
columns agree at **+0.910**. The top and bottom of the table are stable under
every combination. Four batters are not, and the table flags them with `!`:
Day-Bédard (moves 0.153), Narasaki (0.143), Kim (0.134), Zettlemoyer (0.112).

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
