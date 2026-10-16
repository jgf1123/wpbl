2026-10-15: v0.9.0
  - Rule: gassed means done. Every pitcher's Gassed column is the same line: the
    season card of the league's worst pitcher who is not disfavored (Addisyn
    Baird, LAQ), against the league-average batter -- about 1.52 runs an inning.
    On v0.8.0 an ace gassed was still better than most of her bullpen fresh
    (Sato gassed 1.09 against six of LAQ's eight others fresh; Lee 1.07 against
    five of NYH's eight), so riding her exhausted looked like a bargain: an
    oracle with perfect hindsight pitched Sato 33 innings in 8 games, entering at
    a count of 117. Now every team's best arm gassed is worse than every
    teammate fresh and fading
  - Fresh and fading are re-centred with the new gassed line in the average, so
    each pitcher's usage-weighted columns are still her season card. Steps in
    runs per PA: fresh to fading 0.020, fading to gassed 0.053 (0.019 on v0.8.0).
    A few fresh columns move: Lee 0.91 -> 0.86 runs an inning
  - Season simulation: 7.71 runs per team-game (v0.8.0 7.78, season 7.64)
  - The replacement is chosen on each build (dice.replacement_card);
    dice.GASSED_EXCLUDE copies manager.DISFAVORED and rules_check holds them equal
  - v0.8.0 cards archived in data/dice/v0.8.0/ (its PDFs are the older layout's;
    the CSVs are v0.8.0's)

2026-10-12: v0.8.0
  - Layout: the Matchup Table is 00-42 pitcher's card, 43-44 reached on error,
    45-99 batter's card. The Double and the Running play move off the table onto
    the pitcher card, in every column: doubles 4/5/6 cells (fresh/fading/gassed)
    and running plays 6/6/6, the same for every pitcher. Her own six lines take
    the rest, 33/32/31 cells. Running plays do not rise with fatigue once the
    first-inning baseline counts every outing (6.9% per PA with a runner on,
    later innings 6.3%)
  - Fatigue shape: one hierarchical step per column (fading 1, gassed 2). Its
    DIRECTION is the 2026 season's, removal innings kept and shrunk: step (a)
    over K/BB/HBP/ball in play K x0.969, BB x0.962, HBP x1.023, in play x1.002;
    step (b) within balls in play OUT x0.916, 1B x1.135, HR x1.052. Fatigue
    shows as harder contact, not lost control. Its SIZE is refit: those
    multipliers are raised to FATIGUE_SCALE 0.25 a step. The fit compared later
    innings with first innings only from outings that reached a second inning,
    a lucky baseline (-0.063 runs per PA against the matchup; all first innings
    -0.010). Against all first innings fatigue is +0.026 per PA, not +0.079
    (dice_game_spec.md 7.4)
  - The shape applies to the whole plate appearance against the league-average
    batter, and the columns are centred exactly: the usage-weighted columns
    give her season card, line by line, except singles: 4 / 5 / 6 doubles
    average 0.35 cells more than the season's 4.54% of plate appearances (running
    plays re-roll, so the rate is of the 94.4 other faces), and that excess comes
    out of singles, keeping hits at the season's total. The game scores 7.78
    runs per team-game, against v0.7.0's 7.72 on the same simulation and the
    season's 7.64. Each of her lines keeps at least 1 cell
  - League pitcher, fresh/fading/gassed cells (K/BB/HBP/HR/1B/OUT/2B/RUN):
    4/5/1/1/7/15/4/6, 4/5/1/1/7/14/5/6, 4/4/1/1/8/13/6/6. Step in runs per
    PA: fresh to fading 0.021, fading to gassed 0.019. A fading Meidlinger
    (1.06 runs an inning against a league lineup) is again better than a fresh
    Villarreal (1.09); on the first build she was 1.13 against 0.98
  - Batter cards, the Outs and Singles Tables and the d12 are unchanged
  - v0.7.0 cards are archived in data/dice/v0.7.0/ (its PDFs print the v0.6.0
    layout, which is the same table); old logs replay on their own cards
  - PDFs need regenerating in nanDECK for the new pitcher layout

2026-10-12: v0.7.0
  - Rule: the fatigue columns read "below" instead of "up to". Fresh while the
    Pitch Count is below 20, Fading from 20 to below her stamina, Gassed at her
    stamina or more. The column is read before each batter and a batter costs 3
    or 5, so a pitcher now throws 20-24 fresh pitches where she threw 21-25
    (user: the defensible reading of "her first 20 pitches"). Stamina numbers
    are unchanged: no real plate appearance starts at or past her stamina
  - Column shares, replayed from the real outings: fresh 0.392, fading 0.597,
    gassed 0.011 (were 0.412, 0.579, 0.010). Every pitcher card is centred on
    them, so pitcher columns move slightly; batter cards are unchanged
  - v0.6.0 cards are archived in data/dice/v0.6.0/; `pixi run play` replays a
    log on the cards and the column rule it was played with

2026-10-02: v0.6.0
  - Fix: a batter's usage share counted starting as a pitcher who does not
    bat. In a DH game the feed lists the starting pitcher at lineup spot 10,
    flagged as a starter. Only spots 1-9 now count as batting starts. Sato
    (1 PA) had ranked as a batter who started 32% of LAQ's games, and was
    smoothed toward bench position players instead of other non-hitters
  - Seven pitchers now have share 0 (Sato, Reynolds, Coria, Benach, Gilder,
    Eckert, Meidlinger), with 12 PA between them. Their cohort fills to 250 PA
    from the nearest shares up to 0.353. It is 22 players and 257 PA: 16
    pitchers with 150 PA, and 6 position players with 107 (Beppu, Robinson,
    Murphy, Gutierrez, Eyster, Ciamarro)
  - 47 of the 67 batter cards print different cells. Most moved only because
    their cohort changed. On runs per PA, the mean change is 0.010 and the
    largest is 0.030 (Kim, Narasaki, Gutierrez, Padgham)
  - Pitcher and league cards are unchanged; pitcher usage was never affected
  - New: GENERIC batter cards, marked PA 0, for a pitcher who never batted.
    Schiano and Bricker get one, so they can pitch without a DH. A generic card
    is the smoothed card of the share-0 cohort, and it changes no other card
  - Open: whether the generic card, and the cohort of the pitchers who do not
    bat, should be limited to pitchers. As built, 42% of its PA are from
    position players, which pulls it toward bench-hitter levels

2026-10-01: v0.5.4
  - Batter cards gain stolen-base ratings: attempt (Goes or League) and
    success (League or Low). Derived each build from the chance and success
    bins in steals.py / stolen_base_spec.md section 4, not a frozen name list.
    Default for both is League

2026-09-24: v0.5.3
  - Printed names are letters and spaces. Accents fold, apostrophes drop,
    a hyphen becomes a space: Day Bedard, Maika Dumais, Thaima Maximiliana,
    Mone Davis, Claire OSullivan. The stored name is unchanged

2026-09-24: v0.5.2
  - A pitcher is one row. Fresh, fading and gassed sit side by side on it,
    each in the low-to-high line order, instead of three rows per pitcher

2026-09-23: v0.5.1
  - The number of cells on a line did not change. What changed is which numbers
    they own, so a card reads low to high in a fixed order
  - Pitcher cards, low to high: HR, 1B, BB, HBP, K, OUT
  - Batter cards, low to high: OUT, K, HBP, BB, 1B, HR
  - Batter cards gain a position list: every position she played in the games
    the cards are built from, DH excluded, most innings first. Abbreviations
    P, C, 1B, 2B, 3B, SS, LF, CF, RF. An equal number of innings is broken by
    that same order; no 2026 card ties

2026-09-21: v0.5.0
  - The d100 gains a RUNNING-PLAY block: 00-32 pitcher, 33-36 double, 37-38
    error, 39-44 running play, 45-99 batter. A wild pitch, passed ball or balk
    advances every runner and the roll is taken again
  - Those six cells do not end a plate appearance, so a card is now a
    distribution over the 94 cells that do. Bands divide by 94: doubles 4/94 =
    4.26%, errors 2/94 = 2.13%
  - Six cells, not the four "4.2% of rolls" implied. All 117 running plays on
    record happened with a runner on, so the block is dead 39% of the time and
    must be larger to land the same rate. Four cells would give 69 plays a
    season against 117
  - The line is on neither card. Best k against the league is 1024, beating the
    flat band by 0.48 SE; smoothing toward the usage cohort is worse than
    ignoring pitcher identity entirely
  - Balks kept at the post-changepoint rate. The balk rate falls 3.6x after game
    22, consistent with an umpire being replaced, though only at p = 0.17. Both
    ways of acting on that give 6 cells; keeping all 18 balks gives 7
  - Blocks 35/58 -> 33/55, so alpha = 33/88 = 0.375 exactly, up from 0.3763. The
    move is 0.003 inside a flat region, so k was not refitted
  - Counts corrected to 87 wild pitches / 12 passed balls / 18 balks: six were
    folded into a plate-appearance narrative rather than given their own row
  - League home runs: cards 69.3, printed table 71.3, actual 69

2026-09-21: v0.4.0
  - Cards are now printed as d100 CELLS, not just percentages. One roll of a
    d100 resolves a plate appearance: 00-34 read the pitcher's card, 35-39 a
    double, 40-41 an error, 42-99 the batter's card
  - Which card the roll lands on IS the combination rule. It is a mixture,
    p = 0.3763 * pitcher + 0.6237 * batter, and it beat no mixing by 4.5 SE,
    as well as log5, the additive shortcut and every zero-sum shift
  - 0.3763 = 35/93. Runs put the weight near 0.15-0.20 and log loss near
    0.375-0.43, with both curves flat; the round-cell point inside that range
    was chosen (user)
  - Doubles and errors are printed as 5 cells and 2 cells, against measured
    rates of 4.54% and 2.22%. The round levels score no worse than the measured
    ones and nominally better
  - k fell across the board, because mixing is itself shrinkage and the cards
    are now built to be mixed: batter true-outcome step 16 (was 64), HR step 2
    (was 4), 1B step 45 (was 64), K step unchanged at 16; pitcher K step 1
    (was 32), free-pass step 64 (was 1024). Fitted jointly with the weight,
    from six starts, all reaching the same fixed point
  - The BB | HBP step was refitted on the full two-sided grid instead of one
    shared value: it returns 2.83 on each side independently (batters were 8,
    pitchers 16)
  - Rounding rule: nearest, then spend the leftover cells wherever the card's
    run value lands closest to the unrounded card -- never on the largest line,
    which would let Out absorb every rounding error
  - Pitcher cards get at least one cell per line; batter cards get no floor.
    Flooring batters too would inflate league home runs by 16%, and the pitcher
    floor alone closes every hole: 0 of 2,479 matchups have a line that cannot
    happen
  - League home runs: cards 68.8, printed table 70.6, actual 69

2026-09-21: v0.3.0
  - Walks and hit-by-pitches are separate card lines again. They were merged
    because runs could not tell them apart (0.45 vs 0.49), but that test was
    blind by construction. Asked whose card a line should be read from, they
    are opposites: walks want the pitcher (a=0.70), HBP wants the batter (0.20)
  - Doubles are a fixed 4.54% band on neither card: a flat league rate predicts
    better than the batter's own (3.9 SE) and the pitcher is worse still
  - The 1% floor moved to the END, after batter and pitcher are combined. The
    combined distribution is what a d100 represents; flooring the cards too
    floored twice
  - Card structures lost their 2B steps and k was re-tuned. Batter HR step 8->4
  - League home runs now 68.2 against 69 actual, from 72.3

2026-09-20: v0.2.0
  - Cohort target 300 -> 250 PA/BF, for batters and pitchers alike
  - Chosen on a finer grid (150 to 600 in eight steps): batters bottom out at
    250, pitchers are flat from 250 up and worse below. The old grid was
    150/300/600, which stepped over the minimum
  - Smoothing k re-tuned at the new target: 4 of 10 step values moved. The
    walk/HBP d10 split is unchanged (batters 8, pitchers 16)
  - Cards move little: the largest line change is 4 points, and most of the
    movement is in the HBP share, the entry with the least data behind it

2026-09-20: v0.1.1
  - Adds cards_league.csv: a league-average batter and a league-average pitcher
  - Both are the league's own line over every PA, so they are identical: each
    PA has a batter and a pitcher, so the season is one distribution
  - Not the mean of the player cards. Under flat log5 this card is the L the
    matchup divides by, so a player facing it keeps her own card exactly;
    the mean of the cards would shift her by up to 1.9 points

2026-09-20: v0.1.0
  - First public set of player cards
  - Cards forecast unseen games; they do not replay 2026, so a card will not
    match a player's season line
  - Built from 37 games (30-game regular season, semifinal G1-G2 of both
    series, championship G1-G3); semifinal G3 excluded, both bullpens spent
  - Batter tree structure:
    - True outcomes (BB/HBP, HR, K) vs ball in play (1B, 2B, Out, ROE)
      - True outcomes: chain HR, K, BB vs HBP
      - Ball in play: chain 1B, Out, ROE vs 2B
  - Pitcher tree structure:
    - Chain K, BB/HBP vs not K/BB/HBP
    - Not K/BB/HBP: Out | ROE | hit
    - Hit: HR | 1B | 2B
  - BB vs HBP is one "free pass" card line plus the player's own split, read
    off an extra d10 (the "HBP share of FP" column)
  - Cohort: grow based on team usage; aim for 300 PA
  - Smoothing k: calculated at each branch
  - HR exceptions for Benites, Whitmore; batters only (Whitmore's pitcher card
    is built like anyone else's)
  - Every card line floored at 1%; the excess comes from the other lines in
    proportion, so a card still sums to 100%
