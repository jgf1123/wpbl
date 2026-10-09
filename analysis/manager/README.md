# Manager AI analyses

The scripts behind the numbers in `manager_spec.md`. Run each from the repo
root with `pixi run python analysis/manager/<script>`. The series experiments
take 5-15 minutes each: keep them to one process and one thread
(`OMP_NUM_THREADS=1`).

## Series experiments (`pixi run manager`)

The policy comparisons are runs of the `manager` command itself. All use the
same 2,400 seeded best-of-5 series (each team against each other, on both home
schedules, 100 each), so their rows are comparable.

| command | table in `manager_spec.md` |
|---|---|
| `pixi run manager --series 100 --lambdas 0 0.0002 0.0005 0.001` | Shadow price v1 |
| `pixi run manager --series 100 --b1 --lambdas --skip-b0` | Shadow price v1 (B1 row) |
| `pixi run manager --series 100 --b1 --lambdas --conventions` | With the conventions on |

## Scripts

| script | what it computes | spec section |
|---|---|---|
| `dh_rules.py` | DH use, starting pitchers who batted, fielders brought in to pitch | Substitution rules against WPBL data |
| `three_batter.py` | relief outings under three batters that left mid-inning | Substitution rules against WPBL data |
| `disfavored.py` | every pitcher's usage, for the disfavored list | Conventions (b) |
| `catchers.py` | everyone who caught, against the cards' C | Decided by the user, second round |
| `saboteur.py` | a manager that minimises its own WP before every batter | Shadow price v1 (saboteur row) |
| `saboteur_parts.py` | worst-arm and never-relieve managers | Where the saboteur loses |
| `arm_value.py` | series won without each team's best reliever, or ace | What one arm is worth |
| `card_spread.py` | runs per inning off each arm by column | (chat, 2026-10-05: why husbanding barely shows) |
| `reservation.py` | ban vs guaranteed vs next reservation, overall and from the brink | Reservation, built and tested |
| `regulars_by_half.py` | most-started player by position, by half and postseason | Lineup conventions: decided |
| `window_starts.py` | late + postseason starts by position and by player | Option 4, revealed preference |
| `conventions_measured.py` | eligibility by starts; batting-only vs 2+3 vs regulars nines; late-season roles | Lineup conventions, measured |
| `lineup_cost.py` | series won with one team batting its best nine | What the lineup conventions cost |
| `two_way_dh.py` | two-way starter sits (keeps the DH); DH-aware relief | Two-way starters and DH-aware relief |
| `nyh_swaps_order.py` | NYH one-swap run gains; best vs real-style vs by-bat order | Where NYH's cost comes from, and batting order |
| `easy_gains.py` | every one-in lineup change, exact runs, fewest position moves, by eligibility tier | Where each team could most easily improve |
| `easy_gains_series.py` | series and game win % with each team's top swap | Where each team could most easily improve |
| `sff_runs_check.py` | SFF runs scored/allowed with and without its swap; whether the swap survives the game | Where each team could most easily improve |
| `team_runs.py` | each team's runs scored/allowed, game win % and starter shares in the default series | What batting choices and an added player are worth |
| `lineup_value.py` | conventions vs best nine by tier; each regular against replacement (bench) and average-at-position blends (LF pools LF+CF, CF its own); per-slot bat of each blend (`slot`) | What batting choices and an added player are worth |
| `player_loss.py` | each conventions player lost: runs lost (conventions and best response), her value, depth; emergency fielders | What losing a player costs |
| `window_start.py` | usual lineups with the late-season window starting after the August trades | Who comes in, and filling the holes |
| `position_first.py` | usual lineup vs the most-started player at each position | Who comes in, and filling the holes |
| `next_up.py` | who comes in for each lost regular, by rank in starts; where a team reaches past its next player | Who comes in, and filling the holes |
| `fit_candidates.py` | other teams' players by time at a weak position (each team's top there excluded) | Who comes in, and filling the holes |
| `trade_fits.py` | a candidate in place of the regular: receiving team's gain, giving team's loss | Who comes in, and filling the holes |

Some scripts were written against earlier states of `manager.py` (for example
`saboteur.py` and `arm_value.py` ran before the conventions existed, with them
off). They still run, with the conventions off unless the script turns them
on.
