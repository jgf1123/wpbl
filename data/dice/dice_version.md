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
