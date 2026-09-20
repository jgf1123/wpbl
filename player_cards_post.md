Dealing the Cards
Rating WPBL players from 37 games
James
Sep 18, 2026

This is the first of two posts about a WPBL dice baseball game. In the game, every player has a card listing her chances of each outcome of a plate appearance: strikeout, free pass (a walk or a hit by pitch), home run, single, double, reaching on an error, or an out. One roll of the dice settles each plate appearance. This post is about deriving those cards from the inaugural season. The next will be about turning them into a game.

The obvious way to make a card is to copy each player's season line: if she walked in 10% of her plate appearances, her card walks 10% of the time. Most of this post explains why that doesn't work, and what we did instead.

1. The data we have

The WPBL's first season gives us 37 games to learn from: the 30-game regular season plus seven postseason games. One semifinal is left out. Both bullpens were exhausted by the time it was played, and its 26 runs would distort every average we compute.

That comes to 2,663 plate appearances spread over 67 batters and 37 pitchers. An everyday player has about 80 plate appearances; a regular pitcher faces around 90 batters. Many players have far fewer: bench players, two-way players who batted only on days they didn't pitch, and pitchers who made one or two appearances.

Eighty plate appearances sounds like a lot until you count what they contain. At league rates, a batter with 80 plate appearances hits about 2 home runs, 4 doubles, and draws about 10 walks. Whether a given player drew 8 walks or 12 is a matter of a few pitches here and there. That thinness drives almost every decision in this post.

1. From play-by-play to card lines

The league's play-by-play records 15 kinds of plate appearance outcome. Several of them differ only in how the ball was caught (a groundout, a flyout, a lineout, a popup), which matters to a scorer but not to a card. So we consolidated the 15 into the card's 7 lines. Our test for keeping two outcomes apart: does it predict unseen games better? (Section 5 explains how we test predictions.)

Table 1: How the play-by-play's outcomes become card lines (37 games)


| Card line        | Play-by-play outcomes                                                                                                           |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Strikeout        | strikeout (314), plus 3 batter's-interference outs                                                                              |
| Free pass        | walk (336), hit by pitch (94)                                                                                                   |
| Home run         | home run (69)                                                                                                                   |
| Single           | single (562), plus 1 fielder's choice where the ball reached the outfield                                                       |
| Double           | double (121); triples would count here, but there were none                                                                     |
| Reached on error | reached on error (59)                                                                                                           |
| Out              | groundout (367), flyout (282), popup (114), fielder's choice (95), lineout (91), other outs (70), foul out (54), sacrifice (31) |


A few rows need a word:

- **All outs share one line.** Fielder's choices and sacrifices are outs too: a runner or the batter is retired, and the scorer credits no hit. The kinds of out differ in what happens to the runners, which the game handles separately (below). No player differed enough in the kind of out she made to change her card.
- **Errors stay apart from singles.** An error isn't a hit, and it depends mostly on the fielders behind the pitcher, while singles depend mostly on the batter. Keeping the two apart predicted unseen games noticeably better than merging them.
- **Walks and hit-by-pitches share one line, the free pass.** They do the same thing on the bases, and keeping them apart didn't predict any better. Batters do differ in which kind of free pass they get, though: Alexia Jorge was hit more often than she walked. So each card also carries the player's own split, read off an extra ten-sided die when a free pass comes up. That keeps each batter's mix, and pitch counts come out right: a walk takes about five pitches, a hit-by-pitch about three.

What the game needs beyond the card

A card says how often each outcome happens. The game also needs to know what an outcome does to the runners, and for outs the play-by-play label doesn't say. With runners on and fewer than two outs, the season's 180 ground-ball outs broke down like this:

- **37:** the batter was out and the runners held;
- **80:** the batter was out and the runners moved up;
- **17:** a runner was forced at second and the batter reached;
- **38:** a double play;
- **8:** something unusual.

Lineouts are usually just one out, but 7 times a runner was doubled off.

So when a card's "out" comes up, the game uses one of three kinds of out:

- **Batter out:** the batter is out and the runners hold.
- **Force at second:** the runner from 1st is out at 2nd and the batter reaches.
- **Double play:** the batter and the runner from 1st are both out.

Any of the three can come with the other runners advancing, for example a sacrifice fly. How often each kind happens is measured league-wide from what the plays did to the bases. It's the same for every player, so it isn't on the cards.

Two numbers show how well the three kinds cover the season:

- **Coverage:** of 514 plate appearances with runners on, fewer than two outs, and an out recorded, the three kinds reproduce 482 (94%). The rest are unusual plays, such as a runner thrown out stretching a hit, and each is mapped to whichever kind is closest in value.
- **Which runner is out:** on fielder's choices with two forced runners, the out came at second base 20 times and on the lead runner 9 times. A lead-runner fielder's choice leaves the same situation as a batter out (the same bases occupied, one more out), so both kinds are covered.

Singles need one rule too. With fewer than two outs, a single scored the runner from second 42% of the time. With two outs, runners go on contact and she scored 67% of the time, so the game treats every two-out single as scoring her.

1. Why a card shouldn't copy the box score

Most fans will expect a card to match the season line. Here's why it can't.

Start with the extreme cases. One pitcher faced 7 batters all season, walked 4 of them, and gave up a home run. A card copied from her line would walk 57% of batters and give up a home run to one in seven. One batter came to the plate twice and struck out both times; a card copied from her line would never put the ball in play. Nobody believes either card. We have a rough idea of how often pitchers walk batters and how often batters strike out, and 7 batters or 2 plate appearances isn't enough to overturn it.

The same thing happens, less visibly, to regulars. Eighty plate appearances is short enough that luck shapes every season line. A few bloopers that fall in, a few line drives caught, and a batter's single rate moves by several points.

We can see this directly by splitting each batter's games into two sets, odd-numbered and even-numbered games, and comparing her two halves. Take the 10 batters with the best rate of some outcome in one set — the most walks, or the fewest strikeouts — then look at how the same 10 did in their other set. We do it in both directions, ranking on the odd games and reading the even, then the reverse, so nothing hangs on which set we picked.

Table 2: The top 10 in one set of games, and the same 10 in their other games


| Outcome           | Top 10, ranking set | Same 10, other set | League |
| ----------------- | ------------------- | ------------------ | ------ |
| Walks             | 18.0%               | 12.3%              | 12.6%  |
| Hit by pitch      | 6.7%                | 4.6%               | 3.5%   |
| Singles           | 31.0%               | 24.1%              | 21.1%  |
| Doubles           | 8.4%                | 5.9%               | 4.5%   |
| Fewest strikeouts | 4.8%                | 9.7%               | 11.9%  |
| Home runs         | 7.5%                | 4.9%               | 2.6%   |


(The 22 batters with at least 20 plate appearances in each set. Odd and even games rather than early and late, so the comparison isn't affected by players improving over the season. Strikeouts are ranked fewest-first: these are the contact leaders, not the batters who struck out most.)

Every row falls back toward the league. The best walkers in one set walked no more than an average batter in the other. The home-run leaders kept about half their edge, the contact leaders about a third. The top 10 in any one set are simply the players whose luck ran hot there, as well as the players who are genuinely good.

This is regression to the mean, and the standard remedy is shrinkage. Each player's card is a blend of her own record and the record of a comparison group. We can think of the blend as adding a number of "phantom" plate appearances, played at the group's rates, to her real ones. A player with few real plate appearances is mostly group; a player with many is mostly herself. How many phantom plate appearances to add is called k. Choosing it well is most of the work, and sections 5 to 8 are about how we did it.

So a card is a forecast: our best guess at how a player would do in games we haven't seen. That's why cards pull toward the middle, and section 10 looks at who that affects most.

1. Smoothing toward whom?

The comparison group matters. Blending a bench player's short record with the league average overrates her: batters with the fewest plate appearances struck out far more and homered far less than the league as a whole. Blending an everyday player with the league average underrates her.

We grouped players by how much their team chose to use them. For batters, that's the share of her team's games she started; for pitchers, the share of her team's batters she faced. Each player's comparison group, her cohort, is the set of players nearest her in that ranking. It grows until it holds about 300 plate appearances, and it never includes the player herself.

Two tempting alternatives don't work:

- **Ranking players by how well they hit** is circular. A batter who ran hot would be grouped with other hot hitters, and her card would simply repeat her record.
- **Ranking by share of the team's plate appearances** ends up sorting everyday players by lineup spot, since leadoff hitters come up more often. Share of games started avoids that: the league's eight everyday starters tie at 100% and form a group of their own.

Usage isn't a perfect measure. A player who missed games for work, school or an injury looks less used than she was, and the box scores list every rostered player each game, so we can't tell an absence from a benching. But a manager's lineup card reflects far more information than the stat sheet does.

We also tested the cohort size. A cohort of 150 plate appearances is clearly worse than 300: the group's own average becomes too noisy to be a useful target. A cohort of 600 is no better than 300.

1. How much smoothing? Let other games decide

Here's how we chose k.

1. Split the 37 games into two random halves.
2. Build every card from one half.
3. Use those cards to predict every plate appearance in the other half.
4. Repeat with 20 different splits.

The k that predicts the unseen games best wins.

We scored predictions in runs rather than in raw accuracy. A card that gets a player's home run rate wrong by one point costs more than one that misses her walk rate by a point, because a home run is worth far more runs. Scoring in runs makes the smoothing care most about what matters most on the field.

Most choices turned out to barely matter. For most parts of the card, a wide range of k values predicts the unseen games about equally well. One choice is sharp: how many of a batter's balls in play fall for hits. It's the most luck-driven rate on a batter's card — of the spread between batters, only about a seventh is real — and it needs strong smoothing. Smoothing it less than the best value costs prediction quickly, and costs more than getting any other step wrong.

![Prediction error by k for each step of a batter's card. The two steps that divide up balls in play rise steeply when k is small; the other five are nearly flat.](img/dice_k_curve.png)

*Figure 1: what each step's k costs in prediction. `pixi run python analysis/dice/fig_k_curve.py`*

Pitchers show a familiar pattern. Their strikeout rates are a real, stable skill. Their walk rates are partly one. Almost nothing else a pitcher allows can be told apart from luck in 37 games: which balls in play become hits, and what kind of hit, depend mostly on the defense and on chance. This is the pattern Voros McCracken identified as defense-independent pitching. So a pitcher's card is mostly her strikeouts and walks, with the rest of it close to her cohort's.

1. Every adjustment has to come from somewhere

A card has to add up to 100%. So when smoothing pulls one of a player's outcomes down, something else must go up. Deciding what goes up turns out to be a real choice.

Our first version smoothed each outcome separately and let outs absorb every change. Pulling a batter's walk rate up meant turning some of her outs into walks. That's rarely what we mean: walking more often doesn't mean she put fewer balls in play. Those plate appearances should come from the other ways a trip to the plate ends without a ball in play — a strikeout, or a hit by pitch.

So cards are built in steps. Each step splits a group of outcomes in two, and each is smoothed on its own. A batter's card starts with:

1. **Did the plate appearance end in a strikeout, free pass or home run, or in a ball in play?**
2. **Within the first group:** home run, then strikeout vs free pass, then the player's own walk vs hit-by-pitch split.
3. **Within balls in play:** single, then out, then error vs double.

Because each step only divides what's inside it, a change stays within its own group. When smoothing decides Benites's singles were partly luck, those plate appearances become mostly outs in play. The share of her plate appearances ending in a strikeout, free pass or home run barely moves (37.0% to 35.8%).

![Benites's card as a tree. Each percentage is a share of the group to its left, her own record then her card. Her singles fall from 52% to 41% of balls in play, while the split above stays at 37% and 36%.](img/dice_card_tree.png)

*Figure 2: the same steps, with Benites's numbers on them. `pixi run python analysis/dice/fig_card_tree.py`*

1. What goes with what

Why split strikeouts, walks, hit-by-pitches and home runs from everything else first? Because of which outcomes trade places across players.

We measured how players' true rates move together: whether a batter who hits more home runs than her cohort also strikes out more, singles less, and so on. This needs care. In any one player's record, a random extra single is automatically one fewer of everything else, so raw rates look negatively related even when the underlying skills aren't. We removed that built-in effect before looking.

What remained:

- **Home runs trade against outs in play, not against singles.** Batters with more power made fewer outs in play. Their single rates weren't lower; if anything, slightly higher.
- **Strikeouts and hit-by-pitches lean the same way.** The evidence is weaker, but both tend to trade against outs in play.

That puts strikeouts, walks, hit-by-pitches and home runs, the plate appearances that end without the defense getting involved, on one side, and balls in play on the other. That's the first split.

It also turned out to be one of the most reliable things we measured. How often a batter's plate appearances end without the defense involved needs only light smoothing to predict her other games well. Once that total is smoothed, the mix inside it needs very little more.

1. Don't fool yourself

We tried a lot of structures: different step orders, different groupings, and outcomes smoothed separately. With enough attempts, one will look good by luck. Two checks keep that honest.

**First, nested testing.** A structure with more adjustable settings has more ways to fit the particular games it's tuned on. So each structure's settings were chosen using only one half of the games, and the result was judged only on the other half, which played no part in tuning. Under this test, a version that smoothed every outcome separately, which had looked clearly better, turned out to be tied with a simpler one.

**Second, a count of tries.** The structure we chose predicted better than the next best by a margin you'd see by chance about one time in 35. But it was one of about eight we tried. We also tested an automatic version of the same idea (always split off the most reliable group first). It predicts about as well, but picks a different structure every time it sees a different half of the games. So our structure is among the best, stable, and easy to explain. It isn't proven best, and we'd welcome anyone who finds a better one.

1. A class of two

Two batters needed special handling. Denae Benites and Kelsie Whitmore hit 12 home runs each; nobody else hit more than 6. Each homered on about 20% of her balls in play, against 3% for the other everyday starters. Without them, the rest of the league shows no home-run spread we can tell apart from luck.

Smoothing them toward their cohort would have pulled them toward hitters with a fraction of their power. So at the home-run step, each is smoothed toward the other plus the league's next two power hitters, Ashton Lansdell and Jamie Mackay. Neither is part of anyone else's comparison group at that step.

We also checked a common suspicion: that big home-run totals come mostly off weak pitching. Ten of their 24 home runs came off the weakest third of pitchers, where 7 or 8 would be expected if the pitcher didn't matter. But the rest of the league homered more off those pitchers by a similar proportion. Their totals weren't built unusually on weak pitching.

1. What fans will notice

Every regular has a signature. Among the 16 batters who played at least 17 games, the line where each stands furthest from the league varies widely:

- **Power:** Benites and Whitmore.
- **Hit by pitch:** Alexia Jorge, hit in 16.2% of her plate appearances, more than four times the league rate.
- **Contact:** Andreanne Leblanc and Skylar Kaplan, who struck out once each all season.
- **Singles:** Samaria Benitez, 37.7% of her plate appearances.
- **Avoiding outs:** Lansdell, who made an out in play a quarter of the time against 41% for the league.

Most of these signatures point in a good direction. That's partly selection: managers keep playing the hitters who are hitting, so some of what makes this list is luck that earned playing time.

What a card keeps and what it trims follows from sections 3 and 7:

- **Mostly kept:** outcomes that don't involve the defense. Benites's home run rate goes from 16.4% to 14.3%. Jorge's card still has her hit by a pitch 11.5% of the time, down from 16.2% but more than three times the league rate. Kept doesn't mean untouched, though. Leblanc and Kaplan each struck out once, in 85 and 79 plate appearances; their cards strike out 5.1% and 4.6% of the time, still well under half the league rate. One strikeout is too few to separate a contact hitter from a lucky one.
- **Trimmed hardest:** what happens to balls in play. Benites's singles and doubles fell in on .565 of her balls in play, against .370 for the league. Her card keeps her well above average at .489, but a rate that high is the kind Table 2 shows falling back.

Table 3: Runs above an average plate appearance (x1000), season line vs card


| Player           | Season | Card | Change | Main reason                                        |
| ---------------- | ------ | ---- | ------ | -------------------------------------------------- |
| Denae Benites    | 356    | 279  | -77    | hits on balls in play                          |
| Ashton Lansdell  | 187    | 109  | -77    | hits on balls in play; doubles                 |
| Kelsie Whitmore  | 172    | 192  | +20    | her low rate of hits on balls in play looks unlucky     |
| Alexia Jorge     | 128    | 79   | -49    | hit by pitch (16.2% to 11.5%), and a little power  |
| Caitlin Eynon    | 53     | -52  | -105   | doubles (9.7% to 4.2%)                             |
| Jamie Mackay     | 55     | 77   | +23    | walks and singles, both low                        |
| Joely Leguizamon | -108   | -33  | +75    | one home run and few walks in 81 plate appearances |


Benites is still the league's best hitter on her card, by a wide margin.

Whitmore rises because her balls in play fell in only .306 of the time. Section 7 found that power doesn't come at the expense of singles, so that low rate looks like bad luck, not a trade-off.

Eynon falls furthest. Doubles are the outcome where we could find the least real difference between batters, so her 9.7% doubles rate is treated as mostly luck. The same happens, less severely, to Natsuki Yonetani.

Leguizamon rises most: a season with one home run and few walks is treated as a slump, not her level.

The cards pull toward the middle because they're built to forecast games we haven't seen, and they do that better than season lines. But a player of the game might reasonably want to replay 2026 as it happened, with Benites hitting .565 on balls in play and Eynon doubling one time in ten. The trade-off is clear: cards closer to the season lines describe 2026 better and forecast worse. We may offer both.

1. Still open

Some of this is unsettled, and more eyes would help.

- **Forecast or replay?** Should the default cards forecast, or replay the season? Or should players choose?
- **League totals:** the batter cards produce 72 home runs over the season's plate appearances, against 69 actual. Should cards be required to add up to the league's totals?
- **Doubles and errors:** is there any real batter skill in them, or is 37 games simply too few to see it? The cards currently treat them as mostly luck.
- **Absences:** can they be identified another way, so that a player who missed games for work isn't treated as a bench player?
- **A better structure:** can anyone find a card structure that forecasts unseen games better than ours?

The design, and every test behind it, is documented alongside the code. If you think a card is wrong, tell us which one and why.