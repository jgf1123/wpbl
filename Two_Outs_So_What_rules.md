# Two Outs, So What?

An unofficial Women's Professional Baseball League (WPBL) simulation board game

*Two Outs, So What?* (TOSW) is a 1- or 2-player game simulating a game, a postseason series, or even a whole season of WPBL. TOSW players will make managerial decisions (managing pitcher fatigue, picking starting line-ups, deciding to steal or bunt) while the game simulates their baseball players' performance.

To avoid confusion, we will use *manager* to refer the TOSW players managing their teams and *athlete* to refer to their baseball players.

## Components

**Board** [Keeps track of baserunners, outs, inning, score, pitch count]

**Dice:** Managers will need a d100 (or two d10) and a d12. A tabletop roleplaying game dice set should contain all of these.

**Batter Card**

**Pitcher Card**

---

## Game Setup

This describes the setup for playing a Pick-Up 7-inning game. To combine multiple games into a series or season, see the Campaign Rules.

Each manager picks one of the four WPBL teams. They may only select athletes on their team.

In a Pick-Up game, decide who will be the Away team and who the Home team. In secret, both managers pick their starting lineup and starting pitcher then simultaneously reveal them to their opponent.

### Starting Pitcher

Managers can select any of their pitchers to start the game. Place the pitcher's card beside the pitch count track for their player. This pitcher immediately gains 30 pitch count from warming up. For a Pick-Up game, all pitchers start fully rested at -30 pitch count, so they would start at pitch count 0.

### Starting Line-Up

There are 8 non-pitcher positions: C, 1B, 2B, 3B, SS, LF, CF, and RF. Managers select 9 batter cards that meet the following conditions.

- All 8 non-pitcher positions must have exactly one assigned batter.
- The 9th batter is either the Pitcher or DH.
- If a batter card is also the starting pitcher, their position is Pitcher.
- Otherwise, the batter can be assigned any of the positions listed on their card OR is Designated Hitter (DH).

Managers order their 9 batter cards in whatever order they wish. Arrange the from left to right so that their next batter is leftmost.

---

## Game Overview

A full game consists of 7 innings. Each inning has two Half-Innings: in the top of the inning, the Away team will bat and the Home team will play defense; in the bottom of the inning, they switch places.

Each Half-Inning consists of 3 or more Plate Appearances until the defenders accumulate 3 Outs, at which point the Half-Inning is over and the next Half-Inning begins.

---

## Half-Innings

**Setup:** At the start of the Half-Inning, make sure Outs are reset to 0 and the bases are empty.

The defending team places their pitcher's card on the pitchers mound on the board. The batting team places their next (leftmost) batter in batter's box on the board with a runner token. Both of these are next to the Matchup Table.

Proceed with the Plate Appearance (see below) between the pitcher and the current batter. When the Plate Appearance is done and 3 Outs have not been tallied:

- Move the batter card that just batted to the end of the line
- Move the new leftmost batter to the batter's box
- Simulate a Plate Appearance between the pitcher and the new batter

**Ending a Half-Inning**: Keep simulating Plate Appearances until 3 Outs are made. Move the last batter's card to the end of the line, clear the bases and Out tracker. Start the next inning with the teams switching batting and defending.

---

## A Plate Appearance

To simulate a plate appearance, roll d100 and d12 together and find the d100 on the Matchup Table, which may direct you to look up the same d100 on an athlete card.

**Matchup Table**
| Roll      | Result                    |
| --------- | ------------------------- |
| **00–42** | On the **pitcher's** card |
| **43–44** | **Reached on error**      |
| **45–99** | On the **batter's** card  |

A batter's card has six lines (OUT, Strikeout, Hit by pitch, Walk, Single, Home run) and the range of numbers that produce that result. A pitcher's card has those six lines plus **Double** and **Running play**, in each of her three columns (see Managing Pitchers): a tired pitcher gives up more doubles.

Below is how to resolve each result. The results use the following terminology:

**Advance**:
- When a runner on 1st advances 1 base, they move to 2nd; a runner on 2nd would move to 3rd; and runner on 3rd scores.
- When a runner on 1st advances 2 bases, they move to 3rd; runners on 2nd and 3rd score.

**Force**: If the batter moves to 1st base while a runner is already there, the runner at 1st is moved to 2nd base to make room. This can cause a chain reaction: if a runner is forced to 2nd and there is a runner already there, she gets forced to 3rd; then if there is a runner already at 3rd, that runner scores.

**Out**: Remove the runner or batter and add an Out to the scoreboard. If there are now 3 Outs, the half-inning is over.

**Score:** Remove the runner or batter from the board, and the batting manager receives a Run on the scoreboard.

### Results

**Strikeout:** The batter is out, the runners stay in place.

**Walk OR Hit by pitch:** The batter moves to 1st base, runners advance only if forced.

**Reached on error:** A fielder error allows the batter to move to 1st base and every runner advances 1 base.

**Home run:** All runners and the batter score!

**Double:** The batter moves to 2nd base and all runners advance 2 bases.

**Single:** The batter reaches 1st and all runners advance 1 base, though runners may advance an addition base: look up the d12 on the Singles Table. Which column managers use depends on the current number of Outs.

**Singles Table**
| Runner                     | 0 or 1 out | 2 outs |
| -------------------------- | ---------- | ------ |
| Runner on 2nd scores       | 8–12       | 5–12   |
| Runner on 1st moves to 3rd | 11–12      | 10–12  |

**OUT:** This result include any play that makes an Out, including fly out, ground out, line out, pop out, fielder's choice, and sacrifice plays. With 2 Outs, the Out ends the inning and no runs are scored.

Otherwise, look up the d12 on the Outs Table. Which column managers use depends on whether there is a runner on 1st base.

**Outs Table**
| Flavor | No runner on 1st | Runner on 1st |
| ------ | ---------------- | ------------- |
| FB+    |                  | 1-2           |
| F+     |                  | 3-4           |
| B      | 1-5              | 5-10          |
| B+     | 6-12             | 11-12         |

- **B**: Batter out with runners holding: the batter is out and the runners stay in place.
- **B+**: Batter out with runners advancing: A productive out, the batter is out but all runners advance, with a runner on 3rd scoring.
- **F+**: Force out with runners advancing: the runner on 1st is out at 2nd but all other runners advance, with a runner on 3rd scoring; the batter moves to 1st base.
- **FB+**: Forced and batter out with runners advancing: Double play! The runner at 1st and the batter are both Out but other runners advance. If these are the 2nd and 3rd Outs, no runs are score; otherwise the runner at 3rd will score.

**Running play:** This represent a wlid pitch, passed ball, or balk. This is the only result that does not end the plate appearance. Advance all the runners then reroll on the Matchup Table with the same batter.

---

## Managing Pitchers

### Pitch count and Fatigue

Every pitcher has a running Pitch Count and a Stamina number printed on
her card. When she enters a game, add 30 to her Pitch Count before she faces anybody.

After each Plate Appearance, add to her Pitch Count:

| Result        | Pitches |
| ------------- | ------- |
| Walk          | 5       |
| Strikeout     | 5       |
| Anything else | 3       |

A pitcher's card has three columns. During a Plate Appearance, use the column corresponding to her Pitch Count:

| Column     | Pitch count                   |
| ---------- | ----------------------------- |
| **Fresh**  | below 20                      |
| **Fading** | 20, up to but not her stamina |
| **Gassed** | her stamina or more           |

Check the Pitch Count *before* each batter; a pitcher who crosses a boundary mid-inning changes columns for the next batter.

A pitcher's Gassed column is still her own, but batters hit her much harder: once she is Gassed, even an ace is worse than a Fresh teammate.

*Example.* A pitcher with stamina 80 is Fresh below 20 Pitch Count, Fading from 20 to 79, Gassed from 80. She enters at 0. A walk puts her at 5, two strikeouts at 15, a groundout at 18: still Fresh. The next batter singles, and her Pitch Count reaches 21. From the following batter, she reads her Fading column. A Pitch Count of exactly 20 is already Fading, so her first 20 pitches (give or take the last batter) are Fresh.

Pitchers will recover from fatigue between games (see Between Games).

### Relieving Pitchers

If a manager wants another pitcher to take over, they can relieve their pitcher before any Plate Appearance while they are pitching. The relieving pitcher also immediately adds 30 to her Pitch Count before she faces the next batter.

**Three-batter minimum.** Every pitcher, starter or reliever, must face three batters or pitch until the end of a half-inning. A pitcher who finishes a half-inning having faced fewer than three may be replaced before the next half-inning; if she starts it instead, she must finish her three (counting the batters she already faced) or that half-inning.

Because many pitchers in the WPBL also bat and play non-pitcher positions, managers may want to the outgoing pitcher to still bat. The exact rules for switching pitchers, designated hitter, moving position players around, and pinch hitting are [complicated](https://discord.com/channels/1535452833887813756/1535467791870595153/1541290106248372346).

- The only way to keep a DH (Designated Hitter) position is to replace a pitcher-only (a pitcher who is not batting) with another pitcher-only AND who is not currently in a defensive position. In such a case, the manager's lineup is unchanged.
- Outside of this, the manager either loses the DH position or never used it to begin with. The manager rearranges defensive positions, making the 9 batters are playing a position on their card and all pitcher and the 8 non-pitcher positions are covered.

---

## Stealing

Before a PA is rolled, a player may green-light a runner to steal 2nd or 3rd base. A runner may steal only if the next base is empty, and at most one steal is attempted per PA: with runners on 1st and 2nd, only the runner on 2nd may go, and if she steals 3rd the runner on 1st must wait for a later PA. Roll d100.

| Base, Attempt rating | No attempt | Success Low | Success League vs Benites | Success League otherwise |
|---|---|---|---|---|
| 2nd, Goes | 00-63 | 64-81 out, 82-99 safe | 64-75 out, 76-99 safe | 64-66 out, 67-99 safe |
| 2nd, League | 00-93 | 94-96 out, 97-99 safe | 94-95 out, 96-99 safe | 94 *, 95-99 safe |
| 3rd, Goes | 00-87 | 88-93 out, 94-99 safe | 88-91 out, 92-99 safe | 88 out, 89-99 safe |
| 3rd, League | 00-98 | 99 * | 99 safe | 99 safe |

On a * result, flip a coin or roll with 50/50 out or safe.

---

## Bunting

*TODO*

---

## Ending the Game

After the top of the 7th inning, if the Home team is ahead in runs, they win and the last half-inning isn't played. Otherwise, play the bottom of the 7th as usual.

If the 7th or later inning ends with runs still tied, the game goes into extra innings: play a full inning but with both teams starting with a runner on 2nd base; this runner is whoever is currently last in the batting order.

---

## Optional Rules

### Draft/All-Stars Game

Managers do a sepentine draft of 15 players among all available pitchers and batters before picking their starting pitcher and batting lineup. If a player has both a pitcher and batter card, they are drafted together.

---

## Between games

After a game, do *not* reset each pitcher's Pitch Count. At the end of every day, all pitchers reduce their Pitch Count by 20 to a minimum of -30. If a pitcher is put in a game before they have fully recovered their stamina, the 30 Pitch Count cost will mean their Pitch Count starts above 0.

*Example.* A pitcher with Stamina 80 finishes a game at 83 Pitch Count. She recovers 40 over that night and the following day, leaving 43. If she then pitches a game 2 days after her last outing, warming up puts her at 73: deep into Fading and only 7 pitches from Gassed.

---

## Design Notes

"Two outs, so what?" (TOSW) is a Los Angeles Queens saying to rally their batters, that the inning isn't over even if they're down with two outs. Indeed, once there are 2 outs in MLB, the batting team scores a run just 12% of the time, while WPBL scores twice as often. The motto also reflects the spirit of the league, made up of women who had been told all their lives to play softball instead of baseball and who refused to give up on their dream.

I received *Statis Pro Baseball* as a birthday present when I was a kid, and it was my introduction to board game sports simulations. One might think it is straightforward to create the cards for such a baseball simulation: the probability of an outcome for a player equals the percentage of plate appearances / batters faced with that outcome. While that is fine for MLB, which can draw on 162 regular-season games per team per season, the inaugural WPBL season had just 15 games per team.

The following table shows Denae Benites's 73 plate appearances across the regular- and post-season (except the semifinals Game 3 LAQ @ NYH on Sept 14, when both bullpens were exhausted). The table also shows the performance of her TOSW card against a league-average pitcher. A card is a forecast of games we haven't seen, not a replay of 2026, because a short season is full of luck. Adelaide Frank walked 5 of the 7 batters she faced, but no one believes she'd walk 71% of batters forever. So each card blends a player's record with those of players her team used about as much, and Benites keeps an excellent card with fewer of the home runs and singles that fell her way.

| Outcome | 2026 Season | TOSW |
|---------|-------------|------|
| HR      | 16%         | 11%  |
| 2B      | 3%          | 4%   |
| 1B      | 33%         | 23%  |
| ROE     | 1%          | 2%   |
| Out     | 26%         | 36%  |
| BB      | 8%          | 11%  |
| K       | 8%          | 10%  |
| HBP     | 4%          | 3%   |

### Who owns what

Batters differ from each other more than pitchers do. Among regulars, batter cards run from 0 to 9 cells of home runs, while every pitcher has exactly 1, so home runs are effectively a batter's skill. Hit by pitch leans the same way, at 0-9 cells for batters and 1-3 for pitchers. Strikeouts and walks are where pitchers matter most (1-10 and 1-7 cells), though batters still vary more (2-14 and 4-12).

Some outcomes aren't anyone's. Doubles sit on the pitcher's card but are the same for every pitcher, because no one's record of doubles predicted her future ones better than a flat rate. Running plays are also the same for everyone, and reaching on an error depends on the fielders, so it's on neither card.

### Why not 50/50

Many games split the roll evenly: in Strat-O-Matic, half the rolls read the batter's card and half the pitcher's. TOSW gives 43 rolls to the pitcher's card, 2 to errors and 55 to the batter. Only 33 of a Fresh pitcher's 43 are her own lines, so among rolls that depend on who's playing, the batter gets about 62%. That follows from the section above, and when we tested different splits on held-out games, giving pitchers about 35-45% predicted best.

### The fatigue system

Managers always pull a tiring pitcher, so we never see what would have happened next. The fatigue system therefore doesn't try to predict her decline; it gives you a reason to pull her on about a real manager's schedule.

Fresh ends at 20 pitches because the data shows a step after a pitcher's first inning, not a slow slide. Tired pitchers don't lose the strike zone: strikeouts, walks and contact rate barely move, but outs turn into hits. Our first estimate of the cost was inflated, because pitchers shelled early had dropped out of the comparison, so 0.08 runs a batter became 0.026. Stamina is designed rather than measured, set just past each pitcher's longest real outing.

Past stamina the data runs out, since only 1.1% of real plate appearances happened there, so Gassed keeps the measured direction but its size had to be chosen. At the measured step, a Gassed Sato still beat most of her bullpen, and a test manager with perfect hindsight pitched her 33 innings in 8 games. My first fix made every Gassed pitcher identical, which stopped that but erased her identity and cost the league's worst arms almost nothing.

Now each pitcher keeps her own card, moved the same amount in the same direction, and the size is the smallest we tried that leaves even an ace worse than a Fresh teammate. Jaida Lee keeps nearly all her strikeouts (10 cells to 9), but her outs fall from 13 cells to 7 and her singles double from 5 to 10, taking her from 0.86 runs an inning to 1.38.

The 30-pitch warm-up closes a separate loophole: without it, a manager could cycle eight arms for 14 pitches each and keep everyone Fresh. One thing remains open: nothing in the game rewards pulling a pitcher a little early, the way real managers do.

### The game that started it

The original impetus for creating this game came when watching the semifinals Game 1 LAQ @ NYH on Sept 10. In the top of the 5th, NYH's Emi Saiki allowed two straight doubles, leaving NYH down 4-0 with a 5th run in scoring position with just 1 out. NYH manager Rocky Henley visited the mound, which wasn't surprising. The question is who she would call to the mound: Jaida Lee was injured, but otherwise the entire NYH bullpen was fresh. On the one hand, if NYH put one of their better relievers in, NYH would still probably lose the game, and the reliever would be out for the rest of the series. On the other hand, not contesting game 1 in a best-of-3 series would put NYH in a tight spot.

Rocky Henley chose London Studer, who allowed 3 runs before getting replaced by Keira Izumi in the 7th, who allowed 3 more. Meanwhile, when LAQ was up 6-1 in the bottom of the 6th, they felt safe enough to call Isabella Villarreal to relieve, who loaded the bases, before putting the game in the safe hands of Meggie Meidlinger.

---

## Quick reference

**Matchup Table**
```
00-42  pitcher's card (her lines, double, running play: advance, reroll)
43-44  reached on error
45-99  batter's card
```

**Outs Table**
```
no runner on 1st:  1-5 B       6-12 B+
runner on 1st:     1-2 FB+     3-4 F+     5-10 B     11-12 B+
```

**Singles Table**
Runner on 3rd always scores
```
0-1 out:  2nd scores on 8-12,  1st to 3rd on 11-12
2 outs:   2nd scores on 5-12,  1st to 3rd on 10-12
```

**Steal Table** (d100, before the PA; next base must be empty; one per PA)
```
              no attempt   Low                 League vs Benites   League otherwise
2nd, Goes     00-63        64-81 out  82+ safe 64-75 out  76+ safe  64-66 out  67+ safe
2nd, League   00-93        94-96 out  97+ safe 94-95 out  96+ safe  94 coin    95+ safe
3rd, Goes     00-87        88-93 out  94+ safe 88-91 out  92+ safe  88 out     89+ safe
3rd, League   00-98        99 coin             99 safe              99 safe
```

**Pitch count:** 
```
enter +30 · walk +5 · strikeout +5 · anything else +3 ·
fresh below 20 · fading below stamina · gassed at stamina or more · recover 20 a day.
```