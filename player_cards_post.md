My cousins gave me Strat-O-Matic Baseball for my birthday one year, which opened opened my eyes to board games simulating sports. That is by way of saying I’m working on an (unofficial) board game simulation of WPBL, tentatively named Two Outs, So What? after the LAQ phrase. (Alternate names include Worm League and Lesbian Baseball; Two Outs, So What? probably needs less explanation.)

In the game, every player has a card listing her chances of each PA (plate appearance) outcome: 1B (single), 2B (double), HR (home run), ROE (reaching on error), K (strikeout), free pass (walk or hit by pitch), or an Out. One dice roll will determine the outcome of each PA. This 1st post derives those player cards from the inaugural season. The next post will be about turning them into a game.

The obvious way to make a card is to copy each player’s season line: if she walked in 10% of her plate appearances, her card walks 10% of the time. Most of this post explains why that doesn’t work, and what we did instead.

1. The Data We Have

So far, the WPBL’s first season gives us 30 regular season games and 7 postseason games. We left out the Sept 14, game 3 between LAQ vs. NYH semifinal because both bullpens were abnormally spent, and the 26 runs scored would distort what we’re trying to measure.

That comes to 2,663 plate appearances spread over 67 batters and 37 pitchers. An everyday batter has about 80 PA; a regular pitcher has about 90 BF (batters faced). Many players have far fewer: bench players, two-way players who batted only on days they didn’t pitch, and pitchers who only made one or two appearances.

80 PA may sound like a lot until you count what they contain: at league rates, that includes about 2 HR, 4 2B, and 9 BB (walk). A few pitches could change that to 7 or 11 BBs, making the player making the player look worse or better than league average. That thinness of data drives almost every decision in this post.

2. Outcomes

The league’s play-by-play records 15 kinds of plate appearance outcome. Several of them differ only in how the ball was caught (a groundout, a flyout, a lineout, a popup), which matters to a scorer, but we do not have the luxury of fragmenting our data between that many plays, so we consolidated the 15 into the card’s 7 lines, as seen in Table 1. Our test for keeping two outcomes apart is: does it predict unseen games better? (Section 5 explains how we test predictions.) A few rows need a word:





All outs share one line. Any play where a runner or the batter is retired, including fielder’s choice and sacrifice plays, is considered an out. For simulating baseball, it’s more important to know what happens to the runners and batter rather if the out came from a fly-, ground-, line-, or pop-out.



Free pass. This combines BB with HBP (hit by pitch). They do the same thing on the bases, and keeping them apart didn’t predict any better. Batters do differ in which kind of free pass they usually get, though: Alexia Jorge was hit more often than she walked. So each card will have a mini-table to tell us which happened, which will be important when tracking pitch count.



Singles and errors separate. While 1B and ROE move runners and batters similarly, but we found keeping the two apart predicted unseen games noticeably better than merging them. We conjecture this is because singles mostly depend on the batter while ROE most depend on the fielders.





| Card line        | Play-by-play outcomes                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Strikeout        | strikeout (314), plus 3 batter's-interference outs                                                                              |
| Free pass        | walk (336), hit by pitch (94)                                                                                                   |
| Home run         | home run (69)                                                                                                                   |
| Single           | single (562), plus 1 fielder's choice where the ball reached the outfield                                                       |
| Double           | double (121); triples would count here, but there were none                                                                     |
| Reached on error | reached on error (59)                                                                                                           |
| Out              | groundout (367), flyout (282), popup (114), fielder's choice (95), lineout (91), other outs (70), foul out (54), sacrifice (31) |

Table 1: How play-by-play outcomes were consolidated into our 7 outcomes.

A card says how often each outcome happens. The game also needs to know what an outcome does to the runners, and there is considerable variation within Outs. In ground out alone with runners on and fewer than 2 outs, this season had:





80: batter out and runners advance;



38: double play;



37: batter out and runners held;



17: forced out at 2nd and batter reached;



8: something unusual.

So when a card’s Out comes up, the game uses 1 of 3 kinds:





Batter: batter out and runners hold.



Force: force out at 2nd and the batter reaches.



Double play: both force at 2nd and the batter are out.

Any of the three can come with the other runners advancing, for example a sacrifice fly is Batter out with runners advancing. How often each kind happens is measured league-wide from what the plays did to the bases. It’s the same for every player, so it isn’t on the cards. Together, these cover almost all cases:





Coverage: Of 514 plate appearances with runners on, fewer than 2 outs, and a play where an out was recorded, the three kinds can reproduce 482 (94%). The rest are unusual plays, such as a runner thrown out stretching a hit, and those are mapped to whichever kind is closest in value.



Which runner is out: on fielder’s choices with two forced runners, the out came at 2nd base 20 times and on the lead runner 9 times. A lead-runner fielder’s choice leaves the same situation as a batter out (the same bases occupied, 1 more out), so both kinds are covered.

1B need a rule too: with fewer than 2 outs, a 1B scored the runner from 2nd 42% of the time. With 2 outs, runners go on contact and she scored 67% of the time, so the game will use a “2 outs, run on anything” rule.

3. Why Smoothing?

Most fans will expect a card to match the season line, but here’s why it can’t.

Let’s start with the extreme cases: one pitcher faced 7 batters all season, walked 4, and allowed a HR; a card copied from her line would walk 57% of batters and give 1-in-7 a HR. One batter came to the plate twice and struck out both times; her card would always K. Nobody would believe either card; we have a rough idea of how often pitchers BB and batters K, and handful of PA isn’t going to overturn it.

The same thing happens, less visibly, to team mainstays. 80 PA is small enough that luck shapes every line: a few bloopers that fall in, a few line drives caught, and a batter’s 1B rate moves by several points.

We can see this directly by splitting each batter’s games into two sets, odd-numbered and even-numbered games, and comparing her two halves. Take the 10 batters with the highest rate of some outcome in one set, then look at how the same 10 did in their other set. (We only consider batters with at least 20 plate appearances in each set. We use odd and even games rather than early and late so the comparison isn’t affected by players improving over the season, injury, etc.)

| Outcome           | Top 10, ranking set | Same 10, other set | League |
| ----------------- | ------------------- | ------------------ | ------ |
| Walks             | 18.0%               | 12.3%              | 12.6%  |
| Hit by pitch      | 6.7%                | 4.6%               | 3.5%   |
| Singles           | 31.0%               | 24.1%              | 21.1%  |
| Doubles           | 8.4%                | 5.9%               | 4.5%   |
| Fewest strikeouts | 4.8%                | 9.7%               | 11.9%  |
| Home runs         | 7.5%                | 4.9%               | 2.6%   |

Table 2: The top 10 batters in one set of games, and the same 10 in their other games.

Every row falls back toward the league. The best walkers in one set walked no more than an average batter in the other. The home-run leaders kept about half their edge, the contact leaders about a third. Nobody got worse at walking halfway through the season: the two sets are interleaved, so there is no before and after. The top 10 in any one set are simply the players whose luck ran hot there, as well as the players who are genuinely good.

Every row falls back toward the league: the players best at drawing BB were average in the other half; the HR leaders kept roughly half their edge; the K leaders kept about a third. The top 10 in any one set contain both players who are genuinely good and those whose luck ran hot there.





This is regression to the mean, and the standard remedy is smoothing: each player’s card is a blend of her own record and the record of a comparison group. We can think of the blend as adding to player’s PA a number of “phantom” PA that play at the group rate. A player with few real PA is mostly their group; a player with many is mostly herself. Let k be how many phantom plate appearances we add; choosing it well is most of the work, and sections 5 to 8 are about how we did it.

So a card is a forecast: our best guess at how a player would do in games we haven’t seen. That’s why cards pull toward the middle, and section 10 looks at who that affects most.

4. Smoothing Toward Whom?

Above, we mentioned a group that a player is blended toward, and the choice matters; blending a bench player with the league average overrates her: there is a reason why bench players did not get much play time, and we see that the players with the fewest plate appearances struck out far more and homered far less than the league average. Likewise, blending an everyday player with the league average underrates her.

We ranked players by how much their team chose to use them. For batters, that’s the share of her team’s games she started; for pitchers, it’s the share of her team’s BF. Each player’s comparison group, her cohort, is the set of players nearest her in that ranking: excluding the player herself, we add players who saw similar usage until the group has about 300 plate appearances. Two tempting alternatives don’t work:





Ranking players by performance is circular. A batter who ran hot would be grouped with other hot hitters, and their cards would repeat that bias.



Ranking by share of the team’s PA ended up sorting everyday players by lineup order since leadoff hitters get more at bats. Using the share of games started avoids that: the league’s eight everyday starters tie at 100% and form a group of their own.

Usage isn’t a perfect measure. A player who missed games for work, school, or an injury looks less used than the team wanted, and the box scores for every game include the team’s entire roster, so we can’t tell an absence from a benching. But by and large a manager’s lineup card reflect how well they feel each player is playing.

We also tested a range of cohort sizes. A cohort of 150 PA was clearly worse than 300: when there are only 2-3 players, the cohort’s own average doesn’t measure a group but individual players, becoming too noisy to be a useful target. A cohort of 600 was no better than 300.

5. How Much Smoothing?

Here’s how we chose k:





Split the 37 games into two random halves.



Build every player card from one half.



Use those cards to predict their PA in the other half.



Repeat with 20 different splits.

The k that predicts the unseen games best wins.

We scored predictions in runs rather than in raw accuracy: A card that gets a player’s HR rate wrong by one point costs more than missing her BB rate by a point because a home run is worth far more runs. Scoring in runs makes the smoothing care most about what matters most on the field.

Most choices turned out to barely matter. For most parts of the card, a wide range of k values predicts the unseen games about equally well. One choice is sharp: how many of a batter’s balls in play are base hits (see Figure 1). It’s the most luck-driven rate on a batter’s card (of the spread between batters, only about a seventh is real) and it needs strong smoothing. Smoothing it less than the best value costs prediction quickly, and costs more than getting any other step wrong.





![Prediction error by k for each step of a batter's card.](img/dice_k_curve.png)

Figure 1: Prediction error in runs vs. k. For the step that splits balls in play into hits and outs, there is a clear minimum with error rising steeply to the left.

Pitchers are what you might expect: their strikeout rates are a real, stable skill; their walk rates are partly. Almost nothing else a pitcher produces can be told apart from luck in 37 games: which balls in play become hits, and what kind of hit, depend mostly on their defense and on chance. This is the pattern Voros McCracken identified as defense-independent pitching. So a pitcher’s card is mostly her strikeouts and walks, with the rest of it close to her cohort’s.

6. Smoothing How?

A card’s probabilities have to add up to 100%, so when smoothing pulls one of a player’s outcomes down, something else must go up. Deciding what goes up turns out to be a real design choice.

Our first version smoothed each outcome separately and let outs absorb every change. Pulling a batter’s BB rate up meant turning some of her Outs into BB. But BB more often doesn’t mean putting fewer balls in play; rather BB tend to come from other ways a PA ends without a ball in play, i.e., a K or HBP.

The method we arrived on through testing is to work in steps. Like a binary tree, each step splits a group of outcomes in two, with that split being smoothed separately from other branches. A batter’s card starts with:





True outcomes (K, BB, HBP, HR) vs balls in play (Outs, 1B, 2B, ROE). The latter are plays where the fielders touch the ball.



Within true outcomes: HBP, then HR, then K vs BB.



Within balls in play: 1B, then Out, then ROE vs 2B.

Because each step only divides what’s inside it, a change stays within its own group. When smoothing decides Denae Benites’s singles were partly luck, those PA become mostly Outs. The share of her PA that are true outcomes barely moves (37.0% to 35.8%). Figure 2 shows how the probabilities on her card shift as we progress through the tree.





![Benites's card as a tree, her own record then her card.](img/dice_card_tree.png)

Figure 2: Denae Benites’s card as a tree. Each branch show the percentage of share of their parent, showing her own record → her card. Benites’s 1B fell from 52% to 41% of balls in play without moving the balls not in play much.

7. What Gets Smoothed With What?

Why did we split K, BB, HBP, and HR from everything else first? We measured how players’ season lines move together: whether a batter who hits more HR than her cohort also K’s more, 1B less, etc. This needs care: in every player’s record, an extra 1B is automatically one fewer of everything else, so raw rates look negatively related even when the underlying skills aren’t; we removed that built-in effect before looking. What remained was:





HR trade against Out, not against 1B. Batters with more power made fewer outs. Their single rates weren’t lower; if anything, they were slightly higher.



K and HBP lean the same way as HR. The evidence is slightly weaker, but both tend to trade against Outs. K does weakly come out of 1B.

That puts K, HBP, and HR on one side, and Out and 1B on the other, then we assigned BB based on their association with K and HBP, and we assigned 2B and ROE based on their association with Out and 1B. That’s the first split.

It also turned out to be one of the most reliable things we measured. How often a batter’s PA end without the defense involved needs only light smoothing to predict her performance in held out games well. Once that total is smoothed, the mix inside it needs very little more.

8. Keeping Us Honest

In developing our approach, we tried a lot of structures: different step orders, different groupings, and smoothing outcomes separately. With enough attempts, one will look good by luck, so we used two checks keep that honest:





Nested testing. A structure with more adjustable settings has more ways to fit the particular games it’s tuned on. So each structure’s settings were chosen using only one half of the games, and the result was judged only on the other half, which played no part in tuning. Under this test, a proposal that smoothed every outcome separately, which had looked clearly better, turned out to be tied with a simpler one.



Counting tries. The structure we chose above predicted better than the next best by a margin we’d see by chance about one time in 35. But it was one of eight we tried. We also tested an automatic version of the same idea (find the most reliable group to split off first): it predicts about as well but picks a different structure every time it sees a different half of the games. So our structure is among the best, stable, and easy to explain. It isn’t proven best, and we'd welcome others finding or suggesting a better one.

9. Exceptional, Literally

Two batters needed special handling: the Denae Benites and Kelsie Whitmore HR derby ended the regular season at 11 apiece then 1 more through their second semifinal games. Nobody else hit more than 5 during that period. Benites and Whitmore homered on about 20% of her balls in play, compared to 3% for the other everyday starters, let alone bench players. Without these two, the rest of the league shows no home-run spread we can tell apart from luck.

Smoothing them toward their cohort would have pulled them toward hitters with a fraction of their power. For non-HR outcomes, their cohorts and cohorts they belong to are derived the usual way, for HR specifically Benites and Whitmore’s cohort are the other plus the league’s next two power hitters (Ashton Lansdell and Jamie Mackay), intentionally undersized cohorts of 228-241 AP, to make the cohorts HR-heavy. Conversely, they are not in anyone else’s HR cohort except their rival’s.

10. Look What They Did to My Girl

Every regular has a signature: among the 16 batters who played at least 17 games, the outcome where each stands furthest from the league varies widely:





Power: Benites and Whitmore.



HBP: Alexia Jorge, hit in 16.2% of her plate appearances, more than four times the league rate.



Contact: Andreanne Leblanc and Skylar Kaplan, who struck out once each across regular and postseason.



1B: Samaria Benitez, 37.7% of her plate appearances.



Avoiding Outs: Lansdell, who was out just a quarter of the time against 41% for the league.

Most of these signatures point in a good direction; that’s partly selection: managers keep playing the hitters who are hot, so likely some luck earned playing time.

What a card keeps and what it trims follows from sections 3 and 7:

Mostly kept: true outcomes. Benites’s HR rate goes from 16.4% to 14.3%. Jorge’s card still has her HBP 11.5% of the time, still more than three times the league rate. Kept doesn’t mean untouched, however: Leblanc and Kaplan struck out once in 85 and 79 PA, respectively; their cards strikes out 5.1% and 4.6% of the time, respectively, still under half the league rate. One K is too few to separate a contact hitter from a lucky one.

Trimmed hardest: balls in play. Benites’s 1B and 2B fell in on .565 of her balls in play compared to .370 for the league. Her card keeps her well above average at .489 of balls in play, but a rate that high is the kind Table 2 shows falling back.

Table 3 shows the number of runs (x1000) each batter contributes above a league-average PA, comparing their actual season line to what their card says:





Benites is still the league’s best hitter on her card, by a wide margin.



Whitmore rises because her actual balls in play fell in only .306 of the time. Section 7 found that power doesn’t come at the expense of 1B, so that low rate looks like bad luck, not a trade-off.



Eynon falls furthest: 2B are the outcome where we could find the least real difference between batters, so her 9.7% 2B rate is treated as mostly luck. The same happens, less severely, to Natsuki Yonetani.



Leguizamon rises most: a season with 1 HR and few BB is treated as a slump, not her level.





| Player           | Season | Card | Change | Main reason                                        |
| ---------------- | ------ | ---- | ------ | -------------------------------------------------- |
| Denae Benites    | 356    | 279  | -77    | hits on balls in play                          |
| Ashton Lansdell  | 187    | 109  | -77    | hits on balls in play; doubles                 |
| Kelsie Whitmore  | 172    | 192  | +20    | her low rate of hits on balls in play looks unlucky     |
| Alexia Jorge     | 128    | 79   | -49    | hit by pitch (16.2% to 11.5%), and a little power  |
| Caitlin Eynon    | 53     | -52  | -105   | doubles (9.7% to 4.2%)                             |
| Jamie Mackay     | 55     | 77   | +23    | walks and singles, both low                        |
| Joely Leguizamon | -108   | -33  | +75    | one home run and few walks in 81 plate appearances |

Table 3: Runs above an average plate appearance (x1000), comparing the player’s season line to their card.

The cards pull toward the middle because they’re built to forecast games we haven’t seen, and they do that better than season lines (see Section 3). This is the best we are able to predict given the small number of games; given more data, Eynon could show she can consistently hit 2B.

Meanwhile, someone playing the board game might reasonably want to replay 2026 as it happened, with Benites hitting .565 on balls in play and Eynon doubling one time in ten. The trade-off is clear: cards closer to the season lines describe 2026 better and forecast worse; we may offer multiple cards for each baseball player and let the board game players choose.

11. Still Open

A peek behind the curtain: we did a lot of testing just to reach this point because we were continually worried the degree of smoothing would make the players look too average and angry fans would beat down our door about how we mangled their favorite players. (Through many iterations, Benites’s card had her RE24/PA much lower.)

So nothing is set in stone, and we could use some additional eyes:





Forecast or replay? Should the default cards replay this season or forecast next season?



Absences: can they be identified another way so that a player who missed games for work or school isn’t treated as a bench player?



A better structure: can anyone find a method for computing cards that forecasts unseen games better than ours?



League totals: the current batter cards produce 72 home runs over this season’s plate appearances compared to 69 actual. How close should cards be required to match the league’s totals?



2B and ROE: is there any real batter skill in them, or is 37 games simply too few to see it? The cards currently treat them as mostly luck. (We call this the 2B or not 2B problem.)

The design, and every test behind it, is documented alongside the code. If you think a card is wrong, tell us which one and why.