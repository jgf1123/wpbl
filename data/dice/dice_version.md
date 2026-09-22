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
