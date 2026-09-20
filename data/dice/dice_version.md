2026-09-20: v0.1.0
  - First public set of player cards
  - Batter tree structure:
    - True outcomes (BB/HBP, HR, K) vs ball in play (1B, 2B, Out, ROE)
      - True outcomes: chain HR, K, BB/HBP
      - Ball in play: chain 1B, Out, 2B, ROE
  - Pitcher chain: K, BB/HBP, Out, ROE, HR, 1B, 2B
  - Cohort: grow based on team usage; aim for 300 PA
  - Smoothing k: calculated at each branch
  - HR exceptions for Benites, Whitmore