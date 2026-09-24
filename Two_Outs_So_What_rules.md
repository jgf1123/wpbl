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
| **00–32** | On the **pitcher's** card |
| **33–38** | **Running play**          |
| **39-40** | **Reached on error**      |
| **41–44** | **Double**                |
| **45–99** | On the **batter's** card  |

Each athlete's card has six lines (OUT, Strikeout, Hit by pitch, Walk, Single, Home run) and the range of numbers that produce that result.

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
- **FB++**: Forced and batter out with runners advancing: Double play! The runner at 1st and the batter are both Out but other runners advance. If these are the 2nd and 3rd Outs, no runs are score; otherwise the runner at 3rd will score.

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

| Column     | Pitch count          |
| ---------- | -------------------- |
| **Fresh**  | up to 20             |
| **Fading** | 21 up to her stamina |
| **Gassed** | past that            |

Check the Pitch Count *before* each batter; a pitcher who crosses a boundary mid-inning changes columns for the next batter.

*Example.* A pitcher with stamina 80 is Fresh to 20 Pitch Count, Fading to 80, Gassed over 80. She enters at 0. A walk puts her at 5, two strikeouts at 15, a groundout at 18: still Fresh. The next batter singles, and her Pitch Count reaches 21. From the following batter, she reads her Fading column.

Pitchers will recover from fatigue between games (see Between Games).

### Relieving Pitchers

If a manager wants another pitcher to take over, they can relieve their pitcher before any Plate Appearance while they are pitching. The relieving pitcher also immediately adds 30 to her Pitch Count before she faces the next batter.

Because many pitchers in the WPBL also bat and play non-pitcher positions, managers may want to the outgoing pitcher to still bat. The exact rules for switching pitchers, designated hitter, moving position players around, and pinch hitting are [complicated](https://discord.com/channels/1535452833887813756/1535467791870595153/1541290106248372346).

- The only way to keep a DH (Designated Hitter) position is to replace a pitcher-only (a pitcher who is not batting) with another pitcher-only AND who is not currently in a defensive position. In such a case, the manager's lineup is unchanged.
- Outside of this, the manager either loses the DH position or never used it to begin with. The manager rearranges defensive positions, making the 9 batters are playing a position on their card and all pitcher and the 8 non-pitcher positions are covered.

---

## Stealing

Between batters, the offence may declare a steal attempt with a runner on 1st or
2nd and the base ahead empty. Roll the d12:

| d12   | Result                            |
| ----- | --------------------------------- |
| 1–10  | Safe — the runner takes the base. |
| 11–12 | Out.                              |

*TODO: catcher and runner ratings.*

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

## Quick reference

**Matchup Table**
```
00-32  pitcher's card      39-44  running play (advance one, reroll)
33-36  double              45-99  batter's card
37-38  reached on error
```

**Outs Table**
```
no runner on 1st:  1-5 B      6-12 B+
runner on 1st:     1-6 B      7-8 B+     9-10 F+     11-12 FB+
```

**Singles Table**
Runner on 3rd always scores
```
0-1 out:  2nd scores on 8-12,  1st to 3rd on 11-12
2 outs:   2nd scores on 5-12,  1st to 3rd on 10-12
```

**Attempt Steal Table**
```
safe 1–10, out 11–12.
```

**Pitch count:** 
```
enter +30 · walk +5 · strikeout +5 · anything else +3 ·
fresh ≤ 20 · fading ≤ stamina · gassed above stamina · recover 20 a day.
```