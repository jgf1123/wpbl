Spoiler warnings for Aug 1st LAQ @ NYH, Aug 9th NYH @ BOS, Aug 22th NYH @ LAQ, Aug 30th NYH @ SFF, and really the entire season and division series

About a month into the inaugural season of WPBL, we noticed how NYH had developed a reputation for choking. Which is something we can use math to answer, so we set out to calculate win probabilities enroute to answering which games had the biggest upsets. This resulted in charts like the following:

Thanks for reading James's Hyperfixations! Subscribe for free to receive new posts and support my work.




Chart 1: Win probability timeline for the Aug 9th game NYH @ BOS
To draw these curves, we need to estimate the win probability after every play in the game based on the current game state (run differential, the inning, and the base-out situation).

Win Probability in MLB
In MLB, win probability is usually just a counting exercise. Take the game state, find every past game that passed through that state, and see how many times home and away won. With more than a century of play-by-play data, even rare states have come up many times.

We could try to apply MLB data to the 7-inning WPBL games by using innings left instead of innings played, e.g., the WPBL 5th inning lines up with the MLB 7th inning stretch. The problem is that WPBL teams score about 2.4 times as many runs per inning as MLB teams do, so a one run lead is a thinner in the WPBL:


Table 1: Differences between play in WPBL and MLB.
Nor can we apply the same approach to the WPBL because we don’t have a century of data to draw from; the WPBL has 30 regular-season games. Those games produced 2,132 plate appearances spread across 1,472 distinct game situations, and 1,100 of those situations happened exactly once. Even the start of a half-inning, which only depends on run differential and the half-inning, is split into 186 situations. Half of them came up just once, and counting outcomes from one example is not an estimate; only six came up more than five times. (For more on what small samples do to player stats, see the batter and pitcher post.)

(Aside: there are other methods for calculating win probability in MLB, some of which resemble our approach below.)

Same Idea, Shorter Horizon
The way we approached the data scarcity problem is to ask the same question (“from here, what happened?”) but over a shorter-stretch: to the end of the current half-inning. For a full half-inning, starting with the bases empty and nobody out, there is enough data: the 34 games have 441 complete half-innings, enough to see the whole spread of how many runs get scored in Table 2.


Table 2: Distribution of runs scored per half-inning.
(One half-inning is left out: the bottom of the 7th. We cannot use half-innings that never completed when the home team took the lead. As for complete bottom of the 7th, we know not enough runs were scored to win the game, so they are a biased sample.)

Stitching Half-Innings Into a Game
With a run distribution for any point in a half-inning, the rest is standard: backward induction, working from the end of the game back to the first pitch.

We start at the bottom of the 7th. Say we are trying to calculate the win probability when the home team is down by 1. Using the half-inning distribution above, they score nothing 50% of the time and lose; they score exactly one 20% of the time and go to extra innings, which (see below) is a coin flip; and they score two or more 30% of the time and win. That comes to 30% + 20% × ½ = 40%. We can similarly calculate the win probability at any run differential in the bottom of the 7th.

Now take one step back to the top of the 7th. Let’s try to calculate the probability the home team wins when the game is tied. If the visitors score 1 (20% chance), that’s bottom of the 7th with home team down 1, which we already calculated as 40%. If the visitors score nothing (50%), that’s bottom of the 7th score tied, worth 75%. Weighting each home team win probability with its chance of happening gives exactly 50.0%.

Repeat that for every run differential and every half-inning back to the 1st, and we have a win probability for the start of every half-inning and run differential.

Mid-Inning Win Probability
Now let’s say we want to calculate win probability mid-inning, say, top of the 5th, runner on 2nd, 1 out, home team down by 4. Above, we already calculated the probability of the home team winning at every run differential for the bottom of the 5th. All we need to do is find the probability we end up at each run differential.

We return to our question, “from here, what happened?” Mid-inning states are rarer, with a runner on 3rd with 0 outs happening just 9 times. Instead of using observed innings, we use each state’s run distribution from the Markov chain described in the previous post. Every play moves the game from one base-out state to another, sometimes with runs scoring on the way. The chain estimates how often each move happens from each state, then follows those moves to the third out. A runner on third with nobody out still has only 9 plays of its own, but the states those plays lead to (e.g., runner on 1st, 0 outs or bases empty, 1 out) have hundreds.

Then when we’re at the start of a half-inning, we can use the win probabilities we calculated for half-innings earlier. For this example, it turns out to be 14.5% chance of the home team winning.

(Note the similarity to how run expectancy is calculated, with one difference: while run expectancy finds the average number of runs scored through the end of the inning, win probability needs the distribution of runs scored. An inning that averages 1 run might be 1 run every time, or 5 runs once and 0 runs four times every five innings, and those are very different when your team is down by 2.)

Extra Innings
Both teams start their extra innings in the same situation: runner on 2nd, 0 outs. Like regular innings, we use our Markov model to find the run distribution from this state. Since both teams draw from the same distribution, a tie going into extra innings is exactly 50/50, so the calculation never has to play extra innings out. When teams differ (see team strength below), a tie is worth each team’s chance of winning one such inning outright since a tied inning simply starts the same situation over.

Does It Hold Up?
Some things must be true of any sensible win probability, and the model can be checked against them. A bigger lead should never lower your chances, and our model never does across every inning, half, base state and out count. Adding a runner should never hurt the batting team; here the model slips in 8 of 462 comparisons, 7 of them in the 7th inning, where one run decides the game. The biggest, 4.2 points, rates a runner on third alone above runners on first and third in the bottom of the 7th with one out. This traces back to that runner on third, 0 outs state with only 9 plays, where not one was an out with the runner holding, so our model believes at least one run is always scored from this state: the chain can borrow what happens after a state’s first play, but that first play still comes from the state’s own record.

The more important check is whether games the model called 70% were won about 70% of the time. Weighting by game, rather than by plate appearance, matters here: a team that blows a lead racks up plate appearances while it’s ahead, which would count each collapse many times over. Scored by the Brier score (the average squared miss between the probability and the result), the model is 31% better than calling every game a coin flip. It is also overconfident at the extremes: situations it rated 90–100% for the home team ended in home wins 82% of the time, and 80–90% situations 75% of the time. Part of that is the home teams themselves, who won only 15 of the 34 games, within the range of a coin flip but enough to pull most of the calibration table below its predictions. 80-90% and 90-100% groups cover only 16 and 17 games, respectively, so two or three late collapses move them a lot. Treat the current calibration as provisional until we have more data.

Team Strength
Everything so far treats every team as league-average. Team strength adjusts the
run distributions for who is batting and who is in the field.

We use exponential tilting so that a good offense slides the run distribution toward bigger innings, and a good defense slides it toward empty ones, keeping the shape of the league’s distribution of runs: the pile-up at zero and the long tail. A half-inning’s shift is the batting team’s offense plus the fielding team’s defense, and the same shift applies to every base-out state. Table 3 shows how many runs each team scores against a league-average defense and how many runs they allow against a league-average defense, which average 1.17 runs per inning.


Table 3: How much each team scores and allows against league-average opponents.
A plot of run distributions for a single inning would have graphs nearly indistinguishable. So instead Figure 1 shows the run distribution for each offense after 7 innings. As the LAQ offense’s rating is the same as the league average, the run distributions for the defense will look similar.




Figure 1: The run distribution for each offense over 7 innings.
Applying the same backward induction but instead using these exponentially tilted run distributions, Table 4 gives the probability of a home team win before the first pitch for each matchup.


Table 4: The win probability for the home team for each matchup.
How the numbers are found. The 8 numbers, 4 offenses and 4 defenses, are fit simultaneously to the 441 half-innings. Every half-inning is one observation: it knows who batted, who fielded, and how many runs were scored. Since we will shift the league’s half-inning run distribution up or down using exponential tilting, this fit looks for a set of 8 numbers that makes each matchup’s half-inning distribution as likely as possible. This is ordinary maximum likelihood on the same kind of model as a Poisson regression.

What makes it work with four teams is the schedule: every offense bats against every other defense. A team whose innings run high against everyone has a higher offense ratings, not that the other 3 teams had lower defense. Without that overlap, the math cannot tell how much came from offense and how much from defense.

Then the ratings are smoothed toward average because 110 half-innings a side is still thin: a team’s raw scoring rate is uncertain by about 0.16 runs per half-inning, as large as the differences we are finding between teams. We figured out how strongly to smooth by asking how much of the spread between teams is more than sampling noise can explain (the tool is a multilevel model). That’s why Boston’s offense averaged 0.85 runs per half-inning but is rated 0.98 relative to the league average of 1.17: most of the gap is real, some of it is 110 innings of luck. The smoothing toward the mean is much stronger on defense because the data finds almost no real spread at all; it’s better than even odds that the four defenses are indistinguishable. For offenses, the data finds the standard deviation of the spread of offenses is about 0.3 runs per half-inning.

For all this work, the team strength model doesn’t clearly predict better yet. Using hold-one-out cross-validation, the team-adjusted model's probabilities sat closer to the actual result for the plate appearances in 22 of the 34 games, but the average gap is well within noise. The team strength model is kept because the direction of the ratings is plausible, and because a question like “who wins the series?” has no interesting answer without them. Their uncertainty is carried along: the 53.6% for the Queens at the Heights has a 90% confidence interval from 39% to 72%.

Highlight Reel
We’ve eaten our vegetables, let’s talk about what happened this season.

Timeline chart
The timeline chart at the top is built from the league-average model, deliberately leaving team strength out so every game starts at 50/50. This makes the chart a matter of only what happened on the field: a low win probability reads as “they were this behind” rather than “they were this far down, and they’re already not the favored team.” Since team strength barely predicts better anyway, adding it would tilt every line slightly without changing the story.

Each step is one play that changes the base-out situation. That includes steals and wild pitches but not pitching changes or failed pickoffs, which change nothing about the situation the next batter faces.

The line follows the team that eventually won, so it climbs toward the winner, and its low point is the moment they came closest to losing.

Bands show which team is batting. They’re brighter the higher leverage the half-inning is, judged at the start of the half-inning. A tied game in the 3rd can be brighter than a blowout in the 7th.

Highlight reel plays come from two lists:

The largest win probability swings, the plays that really changed the game. By the nature of win probability, these are concentrated in the later innings of the game.

The largest changes in run expectancy, independent of score or inning. This finds plays like home runs or a bases-loaded double plays to end the inning. Because most of the time in baseball 0 runs score, the biggest plays are almost always offensive plays, so we enforce at least 1 defensive play in the list.

Comebacks
A comeback is defined as a team reaching a low point before coming from behind to win. Table 5 shows the 7 biggest comebacks this season.




Table 5: Largest comebacks out of the regular season and the two division playoffs.
The Aug 30 game, or rather its 7th inning, is the one to see. SFF comes in down 5, cuts the lead to 3 (against Claire O’Sullivan, who isn’t Jaida Lee, but her RE24/BF is slightly above league-average). Then the situation every kid dreams about: 2 outs, bases loaded, full count, Andreanne Leblanc hits a walk-off grand slam. That was the largest swing in win probability (80%) in all the games thus far; we still get shivers thinking about it.




Chart 2: Andreanne Leblanc’s walk-off home run on Aug 30, NYH @ SFF.
For comparison, on Aug 1st, LAQ @ NYH, top of the 7th, 2 outs, NYH up by 2, runners at 1st and 2nd: Michelle Roche RBI single to right field (11% swing). Now with runners at the corners, Amira Hondras RBI single to center (another 24%). Again with runners at the corners, tied game, Isabella Villareal 2 RBI double into center (another 35%) is the 2nd largest swing in win probability this season.




Chart 3: Opening day, LAQ come back from down 2 with 2 outs in the top of the 7th.
Chokes and Rallies
We note that in the 3 largest comebacks this season, NYH were the team that got upset. That said, if we look at all the comebacks before Sept 6th, NYH was involved in the top 6, twice the team doing the comeback. Chart 4 shows NYH’s largest comeback:




Chart 4: NYH’s biggest comeback, Aug 22 NYH @ LAQ, after LAQ increased their lead to 4 runs in the bottom of the 4th with just 1 out so far.
Rollercoasters
We remember watching game 2 of the Heights-Queens division series on Sept 12th and thinking how wild the game was with its ups and downs. After the game, we posted on the fan Discord it was the 2nd most “rollercoaster” game so far; after updating our run expectancy table to the Markov model, we now rank it 4th, but it being a win or go home game for NYH made every play feel that much more exciting.




Chart 5: Sept 12 NYH @ LAQ, game 2 of their best-of-3 playoff series. The most rollercoaster game so far of the playoffs.
We acknowledge that this is an arbitrary measure, but to measure “rollercoaster”-ness we summed the absolute win probability movement up and down to capture how swing-y a game was. The least rollercoaster game was Aug 5th BOS @ LA:, LAQ led by 5 in the first inning; every out, walk, and single moved win probability up and down a tiny bit, but LAQ’s lead we never under threat, growing to 9 runs in the 4th. The total movement was 85% (i.e., 17.5% toward BOS, 67.5% toward LAQ). The median game had 280% movement; the Aug 9th game in Chart 1 had double that.


Table 5: Top “rollercoaster” games so far, measuring how far up and down win probability moved.
Using timeline charts
The highlighted plays in each timeline chart are effectively the video clips a broadcaster would assemble to produce a highlight reel. However our personal opinion is this is not the best way to watch baseball: a home run is an impressive physical feet, but the importance of the home run is undercut if the audience doesn’t internalize the context before seeing it: was it on 2 outs and prevented runners from being stranded? Did it help the team come back from behind? Did it come late in the game to clench it?

Furthermore, we feel a lot of the enjoyment in watching baseball is the anticipation, watching the count inch toward full, wondering if something big is about to happen or not (the reason we like WPBL is something does happens more often than it does in MLB). So we recommend watching full plays or even full half-innings to see the situation develop. Here are some innings we recommend, especially the first two; we’re intentionally not listing why each was chosen because of spoilers, but there is no new machinery involved.

Aug 22nd, NYH @ LAQ, bottom of 6th to end of game

Sept 12th, NYH @ LAQ, bottom of 6th to end of the game

Aug 30th, NYH @ SFF, top and bottom of 7th

Aug 1st, LAQ @ NYH, top of 7th

Aug 22nd, SFF @ BOS, bottom of 5th

Aug 9th, NYH @ BOS, full 8th inning

Sept 9th, BOS @ SFF, bottom of 3rd to top of 4th

Assumptions and Limitations
Several assumptions do a lot of work here:

Half-innings are independent. The model knows the score, inning, outs, and runners, but not who is pitching, how many pitches they’ve thrown, where in the batting order it is, or whether a team is playing for one run late in a close game.

Team strength is fixed for the season, though rosters are only 15 players and teams changed how they used them as the season went on, especially when injuries take players out of commission.

A few half-innings are missing where the league’s data feed lost plays.

With 34 games, every number here has real uncertainty, and the calibration table is a reminder of it. The approach works because it splits the problem so the thinnest data only has to cover one half-inning, and everything beyond that rests on estimates the season can actually support.

Series Predictions?
Using the team strength model, we can estimate the win probability of each matchup (see Table 4) and then extrapolate to a whole series. Our assumptions increasingly farll apart here, as fans watching LAQ vs. NYH division series witnessed decisions in games 1 and 2 affecting game 3, so take these with a grain of salt.

Before the playoffs, we would have predicted SFF beats BOS 74/26%, and NYH beats LAQ 55/45%, with each teams winning the championship series at SFF 43%, NYH 30%, LAQ 19%, and BOS 7%.

In the best-of-5 championship series between LAQ and SFF, we place SFF as the favorite 64/36: a decent edge but not indominable, especially with all the upsets we’ve seen this season. Broken down:


Table 6: Estimated probability of various outcomes of the 2026 Championship Series
So very likely that both teams will need to find pitchers for game 4 and maybe 5. If SFF wins game 1, we estimate their chances go up to 79/21; if LAQ wins game 1, we then believe LAQ would be the favorites 57/43.

A New Age
One big reason I wanted to develop win probabilities with team strengths was the call made in game 1 of NYH vs. LAQ best-of-3: top of the 5th, runner on 2nd, 1 out, NYH down by 4. Ignoring team strength, we estimate NYH had a 15% chance to win the game (with team strength, slightly higher); in 5 of the 31 games up to that point, teams had beat bigger odds. If NYH loses, their probability of winning drops to 29%. If NYH instead won the game, our model says they would have a 74% chance to win the series. But our model is flawed here because it assumes no game affects any other, which is false because any pitchers NYH use in these last 3 innings is borrowed from their pitchers for game 2. But remember LAQ are in the same boat, which is why they only briefly put in Villareal to pitch.

There are two universes: one where NYH takes the 15% chance and fights back; 15% of the time they’ll have a strong lead in the series (let’s say less than 74%) and 85% of the time they’ll face an uphill battle (let’s say less than 29%). In the other universe, they stop fighting and accept an easier uphill battle (let’s say greater than 29%). NYH manager Henley chose the latter. We cannot, mathematically, say whether this is the right or wrong call; the above is as far as our model takes us. But we can say that the part of us that is a NYH fan felt this was the wrong call.