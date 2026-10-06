# Two Outs, So What? — automated play

A command that plays a TOSW game by the printed rules, rolling every die and
resolving every result, and stops only where a manager has a decision. The log
file is both the record and the interface: the command reads it, plays on to
the next stop, appends what happened, and exits. The manager edits the decision
block it left and runs the command again.

Status: built 2026-10-01. `pixi run python analysis/dice/play_check.py` passes.

## 1. Scope

Automated:

- Plate appearances: d100 and d12, every table in `Two_Outs_So_What_rules.md`.
- Steals: green or red light by win probability (section 5), then the d100 on
  the rulebook's steal table.
- Pitch counts in the game, and pitcher fatigue across days.
- A team-neutral win probability after every event (section 6).

Stops for the manager:

- At the start of every half-inning, for the fielding team, the top of the
  1st included.
- Before every plate appearance while the fielding team's pitcher is Gassed,
  including a pitcher who entered already Gassed from carried fatigue, once the
  three-batter minimum allows her to leave (section 4).

One person manages both teams, or two people share the file. A computer
manager plays in-process instead (`manager.py`, `manager_spec.md`): with
`Game.every_pa` set it also gets a stop before every plate appearance at which
a change is legal.

Out of scope: bunting, pinch-hitting and pinch-running. Defensive moves and
substitutions are made only by the fielding team, at its stops (section 4).

## 2. Commands

    pixi run play new  <game.md> --date 2026-10-03 --away SFF --home LAQ [--after <prev.md> ...] [--seed N]
    pixi run play      <game.md>
    pixi run play export <game.md>          # one CSV row per event, for analysis
    pixi run play suggest <game.md> [--team SFF] [--write]   # batting order for the nine named

`suggest` reorders the nine names already in a team's `order` to maximise
expected runs over seven innings against the league-average pitcher. It is
solved exactly over (outs, bases, batting slot) and searched by swaps and
moves from 41 starts (`src/wpbl/play_lineup.py`). It ranks bats only, leaving
out steals and fielding. `--write` puts the order into the setup block, and is
refused once the game has started.

`new` writes a setup block with every league pitcher's fatigue and an empty
lineup template, then exits. With no `--after`, every pitcher starts at -30
(the Pick-Up game). With `--after`, each pitcher's count comes from the latest
listed log in which her team played, recovered by the days between that log's
date and the new date (section 7).

`play` replays the game so far, plays on to the next stop, rewrites the file,
and exits. Games live in `games/`.

## 3. The log

Markdown. The command reads only fenced blocks tagged `tosw-...`, which hold
TOML (Python's `tomllib`, so no new dependency). Every other line is output.

````markdown
# SFF @ LAQ, 2026-10-03

```tosw-setup
seed = 4821                    # written by `new`; change it for a different game
date = 2026-10-03
cards = "v0.6.0"               # play refuses to run against other cards
away = "SFF"
home = "LAQ"

[lineup.SFF]                   # batting order; position from the card, or DH or P
order = ["Amanda Gianelloni 2B", "Kelsie Whitmore P", "..."]
pitcher = "Kelsie Whitmore"

[lineup.LAQ]
order = ["..."]
pitcher = "Ayami Sato"

[fatigue]                      # pitch count before the game, whole league
"Ayami Sato" = -30
"Kelsie Whitmore" = 12
```

## Top 1 · SFF batting · Sato (LAQ) pitching   <!-- illustrative rolls and WP -->
- 0 out ___ · Gianelloni · d100 57 → batter OUT · d12 4 → B · 1 out · Sato 3 fresh · LAQ 0 SFF 0 · WP home 51.2%
- 1 out ___ · Whitmore · d100 12 → pitcher BB · Sato 8 fresh · WP home 50.1%
- 1 out 1__ · steal 2nd: green (+1.4%) · d100 70 → safe · WP home 48.7%
...

```tosw-decision
# Bottom 1. LAQ batting, SFF fielding. SFF 0, LAQ 0. WP home 50.4%.
# Whitmore: 54 pitches, fading (gassed past 89).
# SFF bullpen: <name> <count> (stamina <n>), ...
[SFF]
pitcher = "keep"               # or a pitcher's name
```
````

The decision block is written with `keep` already filled in, so re-running
without editing means "no change". `#` comments are allowed anywhere in a block.

When the game ends, the command writes the box score and a `tosw-fatigue-after`
block: the date and every league pitcher's count after the game, before any
recovery.

**Replay, not resume.** On every run, the command rebuilds the game from the
seed, the setup, and the decision blocks in order, and regenerates the whole
text. If the regenerated text differs from the file's text up to the last
decision block, the command stops and shows the first line that differs and does
not write anything. That catches an edited play-by-play, a changed engine, and
changed cards. Dice come from one seeded `numpy` generator, drawn in a fixed
order, so the same inputs always give the same game.

## 4. The game

The rules are `engine.py`'s, which `analysis/dice/rules_check.py` already
checks against the rulebook: `Table.read`, `apply_line`, `move`, `enter`,
`column_for`, `recover`. Play is new code around them, because
`engine.half_inning` steals at league rates and does not track a lineup.

Pitch count after each plate appearance: walk and strikeout +5, anything else
+3. A running play and a steal add nothing. Her column is read from her count
before each batter.

Pitching changes in v1, at a stop:

- **Three-batter minimum** (OBR 5.10(g)): the pitcher on the mound must face
  three batters or pitch to the end of a half-inning. One who finished a
  half-inning under three may be replaced at the next half's start; if she
  starts it, the rest of her three carries on. A change she is not yet allowed
  is refused, and a Gassed stop waits until she is.
- The new pitcher must be a teammate with a pitcher card who has not pitched
  in this game and has not left it. She adds 30 to her count on entering.
- With `pitcher` alone, the new pitcher comes from outside the lineup. If the
  outgoing pitcher was batting (no DH), the new pitcher takes her lineup slot.
  Otherwise the DH stays and the lineup is unchanged.
- With `lineup = [...]` as well, the decision gives the whole new nine in
  batting order. This is how a player already in the game moves to pitch, how
  positions change, and how a bench player comes in. The stop's notes list the
  current nine to copy. The rules:
  - Each slot keeps its player or takes a newcomer. Nobody changes her place
    in the order.
  - A player who leaves the game cannot come back. A pitcher who moves to a
    field position stays in the game but cannot pitch again.
  - Positions are checked against the cards as in the setup, with the
    pitcher at P.
  - The DH stays only if the pitcher is outside the lineup. Once lost, it
    does not return.
  - A `lineup` with `pitcher = "keep"` is a defensive change alone.
- From cards v0.6.0, a pitcher who never batted (Schiano and Bricker) has a
  generic batter card, marked PA 0, so she can bat. A pitcher with no batter
  card at all can still pitch only when her team uses a DH.
- A log is played on the cards it was set up with. `play` refuses a log whose
  `cards` version differs, so a game in progress is finished on its own
  version. A finished log still seeds the next game through `new --after`,
  because that reads only its fatigue block.
- The outgoing pitcher keeps her count, which goes into the fatigue footer.

Each change is checked when the decision block is read. An invalid change
stops the command with the reason, and the block stays as it is to be fixed.

## 5. Steals

Before each plate appearance's first roll, at most one steal is considered.
Only a runner whose next base is empty may go, and there is no steal of home.
So exactly one runner is ever eligible:

| bases | eligible |
|---|---|
| 1__, 1_3 | runner on 1st, stealing 2nd |
| _2_, 12_ | runner on 2nd, stealing 3rd |
| others | none |

With 1st and 2nd occupied, if the runner on 2nd steals 3rd, the runner on 1st
gets no chance in that plate appearance. She may go before a later one.

**Green light** when the attempt, at the runner's success rate p, is net
win-probability positive for the batting team:

    p · WP(safe) + (1 − p) · WP(caught) − WP(no attempt) > 0

A net value of exactly zero is a red light ("positive" means greater than
zero). The no-attempt faces on the d100 scale the value but cannot change its
sign (`stolen_base_spec.md` §9), so they are left out.

p is read off the rulebook's steal table: of the attempt faces, the share
that are safe, with a `*` face counting as half safe. So the decision and the
dice always agree.

| base, attempt rating | `success_low` | `success_league` vs Benites | `success_league` otherwise |
|---|---|---|---|
| 2nd, Goes | 18/36 = 0.500 | 24/36 = 0.667 | 33/36 = 0.917 |
| 2nd, League | 3/6 = 0.500 | 4/6 = 0.667 | 5.5/6 = 0.917 |
| 3rd, Goes | 6/12 = 0.500 | 8/12 = 0.667 | 11/12 = 0.917 |
| 3rd, League | 0.5/1 = 0.500 | 1/1 = 1.000 | 1/1 = 1.000 |

The code derives these from the table rather than hard-coding them.

The catcher is whoever the fielding lineup has at C. On a green light, the
command rolls the d100 on the rulebook's steal table with the runner's card
ratings, and rolls again with a coin flip on a `*`. The log shows the decision
and its WP margin on every eligible plate appearance, red lights included, so
the rule can be audited.

## 6. Win probability

Team-neutral means league-average batter against league-average pitcher
(`cards_league.csv`), played by the same rules as the game. It does **not**
come from the real-game model behind `pixi run wp`, so that WP describes the
game being played.

The method is the one in `win_probability_post.md`, computed exactly rather
than sampled:

1. The distribution of runs to the end of the half-inning, from every
   (outs, bases), for one league plate appearance: d100 bands, card lines, and
   d12 tables enumerated, with the running-play reroll solved as a geometric
   series.
2. Backward induction over half-innings 7 to 1, by run difference. Runs scored
   in a walk-off do not affect who wins, so the run distribution is enough and
   there is no truncation.
3. Extra innings, each half starting with a runner on 2nd. Every extra inning
   is the same, so tied at the start of one: W = P(home wins the inning) /
   (1 − P(tied after it)).

Steals are left out of the WP model. The steal rule uses WP, so leaving them in
would make the model depend on itself. This is the same simplification as a
run-expectancy table without steals.

The table is rebuilt from `cards_league.csv` on every run, in about a second,
so it cannot go stale and needs no cache. The league pitcher is the
`season card` row, with no fatigue column. Checks: the exact run distribution
matches `engine.half_inning`'s simulation to within sampling error. WP never
falls as the home lead grows. A tied start is exactly 50%, which is what two
identical teams should give.

## 7. Fatigue across days

The rulebook says: "At the end of every day, all pitchers reduce their Pitch
Count by 20 to a minimum of -30." Days are counted between game dates, so a
same-day doubleheader recovers nothing. `engine.recover(count, days)` does the
arithmetic.

On a given date the four teams play two games, which share no pitchers. So
`new --after` takes several logs and, for each pitcher, uses the most recent
one in which her team played. Two logs on the same date for the same team is
an error. The new log's `[fatigue]` block can still be edited by hand. The
command trusts what it reads there.

## 8. Code

- `src/wpbl/play.py`: CLI, log parsing and writing, replay, the game loop,
  substitutions, steals.
- `src/wpbl/play_wp.py`: the exact WP table.
- `pixi.toml`: `play = "python -m wpbl.play"`.
- Tests in `analysis/dice/play_check.py`, in the style of `rules_check.py`:
  - The steal table matches the rulebook cell for cell. Steal eligibility for
    all 8 base states. p for every cell.
  - The WP checks in section 6.
  - The log: a game played stop by stop is the same game played straight
    through. A finished log is left alone. An edited play-by-play, seed or
    past decision is refused, and nothing is written.
  - Pitching changes:
    - With a DH the lineup is unchanged; without one, the new pitcher takes the
      slot.
    - Refused: re-entry, a fielder brought in to pitch, and a pitcher with no
      batter card when there is no DH.
    - Three-batter minimum: the starter cannot leave before her first batter;
      five cases of (batters faced, finished a half, at a half's start); no
      stop is offered mid-half before three; a reliever who finished a half
      under three can leave between halves.
  - 400 whole games:
    - Runs and pitch counts add up, and no game ends tied.
    - The home team does not bat when already ahead.
    - The extra-innings runner is the team's last batter.
    - Caught stealing for the third out: the same batter leads off next time.
    - A green light exactly when the net WP is greater than zero.
  - Fatigue across days, a doubleheader, and two games on one date.

## 9. Rules the rulebook does not state

Confirmed by the user on 2026-10-01.

1. **Caught stealing for the third out:** the batter has not finished her plate
   appearance, so she leads off the next inning.
2. **Walk-off:** the game ends as soon as the home team leads in the bottom of
   the 7th or later.
3. **No re-entry:** a pitcher who has left the game cannot come back in it.
4. **Three-batter minimum** (user, 2026-10-04): as OBR 5.10(g), without its
   injury exception. Now in the rulebook.

Not a rule, only how the log keeps score: every run on a walk-off play is
counted. Who wins does not depend on it.
