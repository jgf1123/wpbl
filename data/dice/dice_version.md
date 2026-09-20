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
