"""Win probability timeline for a single game, one step per base-out change.

    pixi run timeline-chart <game_id>                 (defaults to the Aug 1 NY/LA game)
    pixi run timeline-chart <game_id> --n-swings 8    (how many plays each highlight pool keeps)

Looks up game_id in data/tables/ (all games, including postseason). The WP model
still trains on the default analysis scope (usually regular season).

A step is any play that changes the base-out state: a plate appearance, a
stolen base or caught stealing, a wild pitch or passed ball, a balk, or a
pickoff that actually gets the runner. A failed pickoff attempt, a
substitution, and a pitching change change nothing about the state a batter
faces, so they are not steps.

Each step's height is the *eventual winner's* win probability the instant
before that play resolves -- the same state-to-win-probability lookup used
everywhere else in this project, read from the winning side. That orientation
tells the story the right way round: the line climbs toward the team that took
the game, and its low point is the moment they came closest to losing it,
rather than tracking a team sliding toward a defeat the reader already knows
is coming.

Holding that value until the next step is exactly right at a half-inning
boundary too: the next step is the first play of the following half-inning,
already reflecting the updated score and the reset to bases empty, nobody out.

The highlighted plays get a numbered marker on the line and their detail in a
panel below, rather than a text box floating over the plot -- with the run
differential, base-out state, and pitcher, and without the pitch sequence,
which is noise for this purpose. They are chosen from two pools: the largest
win-probability swings, and the largest RE24-style expected-runs values
(independent of score or inning). WP swing alone concentrates almost
entirely in the 7th, where win probability is most sensitive to any one play;
run value finds the plays that matter in the sabermetric sense wherever in
the game they happen -- a bases-loaded double play in the 2nd, say. Each is
tagged offense or defense from its run value: whether it helped the team
batting or the team fielding.

Each half-inning's band is shaded in the batting team's own colour, made more
saturated and vivid by that half-inning's leverage: the standard deviation of
the win probability its leadoff plate appearance could produce, over the runs
that at-bat might score. That is an ex-ante property of the situation -- a
tied game in the 3rd is high-leverage regardless of what actually happens
next -- so it is a truer signal than inning number alone, which a decided
score late would still light up.

Extra innings are drawn like any other, since the model covers them: each one
starts with a runner already placed on second, and the run distribution for
that state is what drives it. Only a game called early (weather) is treated
specially -- nothing that happened on the field ended it, so the tracked line
simply stops and the actual result is marked with a separate dashed segment
rather than folded in as a swing, which would make a routine play right before
the stoppage read as deciding the game by itself.
"""

from __future__ import annotations

import re
import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt

from wpbl.markov import re_of, run_expectancy
from wpbl.parse import ALL_DIR, DATA_DIR
from wpbl.usage_chart import CODES, label_ink
from wpbl.win_probability import Model, REGULATION

DEFAULT_GAME = "8alsgvzc90ypwphl"

# Anything that leaves a batter facing a different base-out picture than the
# one before it. Substitutions, pitching changes, and failed pickoff attempts
# are deliberately excluded -- none of them move a runner or add an out.
STATE_CHANGING = {"plate_appearance", "plate_appearance_unknown",
                  "baserunning", "baserunning_out", "balk"}

TEAM_COLORS = {
    "Boston Hunters": "#2E7D46",            # green
    "Los Angeles Queens": "#D4A017",        # gold
    "New York Heights": "#1F5FA8",          # blue
    "San Francisco Firebells": "#8C2F5C",   # red-violet
}

BASE_LABEL = {"___": "empty", "1__": "1st", "_2_": "2nd", "__3": "3rd",
              "12_": "1st & 2nd", "1_3": "1st & 3rd", "_23": "2nd & 3rd", "123": "loaded"}

# Ranking the highlighted plays by |WP swing| alone strongly favours the 7th
# inning: that's where win probability is most sensitive to any single play.
# Adding a second pool ranked by |run value| -- the RE24-style expected-runs
# impact, independent of score or inning -- surfaces the plays WP-swing alone
# would bury, like a bases-loaded double play in the 2nd. Both pools keep the
# same count by default; --n-swings changes both together.
N_SWINGS = 5
PITCH_SEQUENCE = re.compile(r"\s*\(\d-\d[^)]*\)")

# Leverage (defined below) for a half-inning's leadoff state runs roughly 0 to
# 0.38 across the season, with the bulk between .06 and .16 (25th-90th
# percentile). Clipping the visible range at .20 keeps that typical range
# spread across the ramp instead of compressed near the light end, at the cost
# of the rare more-extreme moment maxing out rather than going darker still.
LEVERAGE_CEILING = 0.20


def half_inning_leverage(model: Model, inning: int, half: str, diff: int) -> float:
    """How much a single play at this half-inning's leadoff state could swing
    the game -- the standard deviation of the win probability the batting
    team's next plate appearance could produce, over the runs that at-bat
    might score.

    This is ex-ante: a property of the situation, not of what actually
    happened. It is what "high leverage" means in the sabermetric sense, and
    it is a truer signal than inning number alone -- a lopsided score late is
    lower-leverage than a tied score in the 3rd, and this tells them apart.
    """
    # An extra inning does not lead off bases empty -- it starts a runner on
    # second, which is a materially higher-leverage state.
    extra = inning > REGULATION
    pmf = model.state[("_2_", 0)] if extra else model.state[("___", 0)]
    batting_is_home = half == "bottom"
    outcomes = []
    for runs, prob in enumerate(pmf):
        if prob == 0:
            continue
        result_diff = diff + runs if batting_is_home else diff - runs
        if half == "bottom":
            wp = (1.0 if result_diff > 0 else (0.5 if result_diff == 0 else 0.0)) \
                if inning >= REGULATION else model._lookup(model.top[inning + 1], result_diff)
        elif extra:
            wp = model._lookup(model.extra_bottom, result_diff)
        else:
            wp = model._lookup(model.bottom[inning], result_diff)
        outcomes.append((prob, wp))
    mean = sum(p * w for p, w in outcomes)
    return sum(p * (w - mean) ** 2 for p, w in outcomes) ** 0.5


def team_ramp(hex_color: str):
    """A grey-to-vivid colour scale in one team's own hue: desaturated and
    pale at 0 (low leverage), fully saturated and bright at 1 (high leverage).
    Leverage picks the point on it -- darkening toward black reads as murky
    rather than as "this mattered more," so brightness rises with saturation
    instead of falling.
    """
    hue, sat, val = mcolors.rgb_to_hsv(mcolors.to_rgb(hex_color))
    sat_lo, sat_hi = 0.10, min(sat * 1.35, 1.0)
    val_lo, val_hi = 0.93, min(max(val * 1.05, 0.85), 1.0)
    return lambda t: mcolors.hsv_to_rgb(
        (hue, sat_lo + t * (sat_hi - sat_lo), val_lo + t * (val_hi - val_lo)))


def _bases(play) -> str:
    return (("1" if pd.notna(play.first_base) else "_")
            + ("2" if pd.notna(play.second_base) else "_")
            + ("3" if pd.notna(play.third_base) else "_"))


def name_fixes() -> dict[str, str]:
    """Word-boundary text replacements for names the feed spells more than one
    way within the season ('Maggie Fox' once, 'Gabriella Haas' once). Built
    from the batting table's own player_name vs. its person's canonical name,
    rather than hardcoded, so it covers whatever the feed does this to."""
    # ALL_DIR: postseason spellings too, even when the WP model is regular-only.
    batting = pd.read_parquet(ALL_DIR / "batting.parquet")
    mismatched = batting.loc[batting["player_name"] != batting["person_name"],
                             ["player_name", "person_name"]].drop_duplicates()
    return dict(zip(mismatched["player_name"], mismatched["person_name"]))


def clean_narrative(text: str, fixes: dict[str, str]) -> str:
    """The play's own clause, spelling-corrected, without the pitch sequence.

    A fielder's choice keeps its out clause. The lead clause names only the
    batter, who reached safely -- but the run value of the play comes from the
    *runner* who was retired, so dropping that clause makes a defensive play
    read like an offensive one.
    """
    clauses = [c.strip() for c in str(text or "").split(";")]
    kept = clauses[:1]
    if "fielder's choice" in clauses[0].lower():
        kept += [c for c in clauses[1:] if " out at " in c.lower()]
    text = ", ".join(kept)
    text = PITCH_SEQUENCE.sub("", text).strip().rstrip(".")
    for wrong, right in fixes.items():
        text = re.sub(rf"\b{re.escape(wrong)}\b", right, text)
    return text


def diff_label(diff: int, home_code: str, away_code: str) -> str:
    if diff == 0:
        return "tied"
    leader, margin = (home_code, diff) if diff > 0 else (away_code, -diff)
    return f"{leader} +{margin}"


def build(model: Model, game_id: str) -> tuple[pd.DataFrame, dict]:
    # A named game_id is looked up in the full tables so postseason (and any
    # other game outside the default regular-season OUT_DIR) still resolves.
    # The win-probability model itself stays on OUT_DIR -- usually regular.
    plays = pd.read_parquet(ALL_DIR / "plays.parquet")
    games = pd.read_parquet(ALL_DIR / "games.parquet").set_index("game_id")
    people = pd.read_parquet(ALL_DIR / "players.parquet").set_index("player_id")["person_name"]
    if game_id not in games.index:
        raise SystemExit(f"No game {game_id} in {ALL_DIR / 'games.parquet'}")
    game = games.loc[game_id]
    fixes = name_fixes()

    steps = plays[(plays["game_id"] == game_id)
                  & (plays["play_kind"].isin(STATE_CHANGING))].sort_values("sequence")

    rows = []
    for play in steps.itertuples():
        diff = int(play.home_score_before - play.away_score_before)
        wp_home = model.win_probability(play.inning, play.half, int(play.outs_before),
                                        _bases(play), diff)
        rows.append({
            "sequence": play.sequence,
            "inning": play.inning,
            "half": play.half,
            "outs_before": int(play.outs_before),
            "bases": _bases(play),
            "diff": diff,
            "wp_home": wp_home,
            "runs_scored": int(play.runs_scored),
            "pitcher": people.get(play.pitcher_id, play.pitcher_name),
            "narrative": clean_narrative(play.narrative, fixes),
        })

    # How the tracked line ends depends on how the game actually finished.
    # Extra innings are now modelled, so the only case that still cannot be
    # carried to a result is a game called early: nothing that happened on the
    # field ended it, so there is no play to attribute the outcome to. An
    # in-progress game is the same: do not invent a Final row from the live score.
    played_innings = int(game["innings"]) if pd.notna(game["innings"]) else REGULATION
    called_early = played_innings < REGULATION
    finished = bool(game["is_final"]) and not called_early
    if finished:
        home_won = game["home_score"] > game["away_score"]
        rows.append({
            "sequence": rows[-1]["sequence"] + 1, "inning": rows[-1]["inning"],
            "half": rows[-1]["half"], "outs_before": 3, "bases": "___",
            "diff": int(game["home_score"] - game["away_score"]),
            "wp_home": 1.0 if home_won else 0.0, "runs_scored": 0, "pitcher": None,
            "narrative": f'Final {int(game["away_score"])}-{int(game["home_score"])}',
        })

    frame = pd.DataFrame(rows).reset_index(drop=True)

    # Plot the eventual winner's probability, not the home team's. Both carry
    # the same information, but this orientation tells the story the right way
    # round: the line climbs toward the team that took the game, and its low
    # point is the moment they came closest to losing it -- rather than
    # tracking a team sliding toward a defeat the reader already knows is
    # coming. wp_home is kept as the model's native output. In progress (or
    # tied), fall back to the side currently ahead, else home.
    if game["home_score"] != game["away_score"]:
        home_leading = game["home_score"] > game["away_score"]
        frame["wp"] = frame["wp_home"] if home_leading else 1 - frame["wp_home"]
    else:
        frame["wp"] = frame["wp_home"]

    # The swing a play causes is the move from its own state to the next row's
    # state -- forward-looking. A backward diff() attributes each transition to
    # the row after the one that caused it, which is wrong whenever a no-op
    # play (a substitution, a failed pickoff) sits between two real ones, and
    # this game has several.
    frame["swing"] = frame["wp"].shift(-1) - frame["wp"]

    # RE24: the expected-runs value of the play itself, independent of score
    # or inning -- a bases-loaded double play in the 2nd shows up here even
    # though it barely moves win probability that early. This is what makes a
    # good defensive play findable outside the 7th inning.
    re_table = run_expectancy()
    next_bases = frame["bases"].shift(-1)
    next_outs = frame["outs_before"].shift(-1)
    same_half = ((frame["inning"] == frame["inning"].shift(-1))
                & (frame["half"] == frame["half"].shift(-1)))
    frame["run_value"] = [
        (re_of(re_table, nb, int(no)) if same and pd.notna(nb) else 0.0) + runs
        - re_of(re_table, bases, outs)
        for bases, outs, runs, same, nb, no in zip(
            frame["bases"], frame["outs_before"], frame["runs_scored"],
            same_half, next_bases, next_outs)
    ]

    return frame, dict(game)


def plot(model: Model, frame: pd.DataFrame, game: dict, out_path: str,
         n_swings: int = N_SWINGS) -> None:
    home_name, away_name = game["home_team_name"], game["away_team_name"]
    final = bool(game["is_final"])
    home_ahead = game["home_score"] > game["away_score"]
    tied = game["home_score"] == game["away_score"]
    # Side the line is drawn for: eventual winner if final, else current leader
    # (home when tied).
    focus_is_home = True if tied else home_ahead
    focus_name = home_name if focus_is_home else away_name
    other_name = away_name if focus_is_home else home_name
    home_color = TEAM_COLORS.get(home_name, "#555555")
    away_color = TEAM_COLORS.get(away_name, "#999999")
    home_ramp, away_ramp = team_ramp(home_color), team_ramp(away_color)
    home_code = CODES.get(home_name, home_name[:3].upper())
    away_code = CODES.get(away_name, away_name[:3].upper())

    # Pick the highlighted plays before laying out the figure: how many there
    # are depends on how much the two selection pools overlap, and the panel
    # has to be sized to hold them rather than squeezing ten entries into a
    # box built for six. Both pools use n_swings -- they were sized together
    # on purpose, and one knob keeps them that way. Rows with no successor
    # (the synthetic Final, or the last live play of an in-progress game)
    # have no swing and are not candidates.
    candidates = frame[frame["swing"].notna()]
    if candidates.empty:
        candidates = frame.iloc[:0]
    top_wp = candidates.reindex(
        candidates["swing"].abs().sort_values(ascending=False, na_position="last").index
    ).head(n_swings)
    by_run_value = candidates.reindex(
        candidates["run_value"].abs().sort_values(ascending=False, na_position="last").index)
    top_re = by_run_value.head(n_swings)

    # Ranking by magnitude alone can return an all-offense run-value list, since
    # a hit moves expected runs further than the typical out does. If it has,
    # trade its weakest entry for the best defensive play available, so a game
    # decided partly in the field does not present as if it were all bats.
    if not (top_re["run_value"] < 0).any():
        best_def = by_run_value[by_run_value["run_value"] < 0]
        if len(best_def):
            top_re = pd.concat([top_re.iloc[:-1], best_def.iloc[:1]])

    chosen = sorted(set(top_wp.index) | set(top_re.index))
    biggest = candidates.loc[chosen]

    panel_share = 1.6 + 0.28 * len(biggest)
    fig, (ax, panel) = plt.subplots(
        2, 1, figsize=(15, 7 + panel_share),
        gridspec_kw={"height_ratios": [7, panel_share]})

    x = np.arange(len(frame))
    ax.step(x, frame["wp"], where="post", color="#2a2a2a", linewidth=1.5, zorder=3)

    # One band per half-inning, in the batting team's own hue, saturated by
    # how much a single play there could swing the game -- leverage, not just
    # inning number, so a decided score late reads as pale, not vivid.
    #
    # With steps-post, row i's flat runs [i, i+1) and its result marker sits at
    # i+1. A half spanning rows [start, end] therefore ends on a play whose
    # marker is at end+1 -- the same x as the next half's first row. Put the
    # colour boundary halfway between those two plays (end+1.5 / start+0.5)
    # so it falls in the gap rather than on the out that ended the half.
    half_groups = frame.assign(half_key=list(zip(frame["inning"], frame["half"])))
    groups = list(half_groups.groupby("half_key", sort=False))
    for position, ((inning, half), group) in enumerate(groups):
        ramp = away_ramp if half == "top" else home_ramp
        entering_diff = int(group.iloc[0]["diff"])
        leverage = half_inning_leverage(model, inning, half, entering_diff)
        t = min(leverage / LEVERAGE_CEILING, 1.0)
        start, end = group.index.min(), group.index.max()
        left = start - 0.5 if position == 0 else start + 0.5
        right = end + 1.5
        ax.axvspan(left, right, color=ramp(t), alpha=0.55, zorder=0)
        ax.text((left + right) / 2, 1.035, f'{"Top" if half == "top" else "Bot"} {inning}',
                ha="center", va="bottom", fontsize=8.5, color="#555555", clip_on=False)

    ax.axhline(0.5, color="#999999", linewidth=0.8, linestyle="--", zorder=1)

    # Numbered markers only -- no floating text on the plot. Full detail sits
    # in the panel below. Rows without a successor (Final, or the last live
    # play of an in-progress game) have no swing and are already excluded.
    offense_wins = defense_wins = 0
    panel_lines = []
    for rank, (idx, row) in enumerate(biggest.iterrows(), start=1):
        y_after = frame.loc[idx + 1, "wp"]
        batting_is_home = row["half"] == "bottom"
        # Who a play benefited is a property of the play itself -- its
        # expected-runs value -- not of the score context, so this drives
        # both the marker colour and the offense/defense tag, independent of
        # how much win probability happened to be riding on it.
        offense_won = row["run_value"] > 0
        winner_is_home = batting_is_home if offense_won else not batting_is_home
        marker_color = home_color if winner_is_home else away_color
        offense_wins += offense_won
        defense_wins += not offense_won

        ax.scatter([idx + 1], [y_after], s=280, color=marker_color,
                  edgecolor="white", linewidth=1.3, zorder=5)
        ax.text(idx + 1, y_after, str(rank), color=label_ink(marker_color),
               ha="center", va="center", fontsize=9.5, fontweight="bold", zorder=6)

        differential = diff_label(row["diff"], home_code, away_code)
        situation = f'{row["outs_before"]} out, {BASE_LABEL[row["bases"]]}'
        half_label = f'{"Top" if row["half"] == "top" else "Bot"} {row["inning"]}'
        pitcher = f'vs {row["pitcher"].split()[-1]}' if row["pitcher"] else ""
        tag = "OFF" if offense_won else "DEF"
        criteria = "+".join(c for c, pool in (("WP", top_wp), ("RUNS", top_re)) if idx in pool.index)
        panel_lines.append(
            f'{rank}.  {half_label} · {situation} · {differential} · {pitcher}\n'
            f'      {row["narrative"]}   ΔWP {row["swing"]:+.2f}  ΔRE {row["run_value"]:+.2f}'
            f'  [{tag} · {criteria}]')

    ax.set_xlim(-0.5, len(frame) + 0.5)
    # A marker sitting exactly on 0 or 1 -- a game-ending play -- would be
    # halfway outside the axes, so leave room for it.
    ax.set_ylim(-0.04, 1.04)
    ax.set_ylabel(f"{focus_name} win probability")
    ax.set_xlabel("Base-out state change, in order")
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xticks([])

    # A game that was called early or went to extra innings needs a visible
    # break between what the model tracked and what actually happened, rather
    # than folding the real outcome silently into the line -- that is exactly
    # what produced a false swing on the last captured play.
    played_innings = int(game["innings"]) if pd.notna(game["innings"]) else REGULATION
    ending_note = None
    if final and played_innings < REGULATION:
        # The line tracks the eventual winner, so the settled result is 1.
        actual = 1.0
        last_x, last_y = len(frame) - 1, frame["wp"].iloc[-1]
        ax.plot([last_x, last_x + 1], [last_y, actual], color="#8a8a8a", linewidth=1.3,
               linestyle=(0, (2, 2)), zorder=4)
        ax.scatter([last_x + 1], [actual], s=70, color="#8a8a8a", marker="s", zorder=4)
        reason = game["status"].split(" - ")[-1].lower() if " - " in game["status"] else "called early"
        ending_note = (f'Called after {played_innings} innings ({reason}) -- dashed segment is the '
                      f'actual result, not a tracked swing.')
    elif final and played_innings > REGULATION:
        ending_note = (f'Went to extra innings, where both teams start a runner on second. Those '
                      f'innings are modelled like any other, drawing on the same runner-on-second '
                      f'run distribution.')
    elif not final:
        ending_note = "Game still in progress -- line tracks the side currently ahead (home if tied)."

    focus_score = int(game["home_score"] if focus_is_home else game["away_score"])
    other_score = int(game["away_score"] if focus_is_home else game["home_score"])
    if final:
        score_bit = f'{focus_name} beat {other_name} {focus_score}-{other_score}'
    elif tied:
        score_bit = f'in progress, tied {focus_score}-{other_score}'
    else:
        score_bit = f'in progress, {focus_name} leads {focus_score}-{other_score}'
    ax.set_title(
        f'{away_name} at {home_name}, {game["game_date"]}  ({score_bit})',
        fontsize=13, pad=28)

    handles = [plt.Rectangle((0, 0), 1, 1, color=away_color, alpha=0.5, label=f"{away_name} batting"),
              plt.Rectangle((0, 0), 1, 1, color=home_color, alpha=0.5, label=f"{home_name} batting")]
    ax.legend(handles=handles, loc="lower left", fontsize=9, framealpha=0.9,
             title="  brighter = higher-leverage half-inning", title_fontsize=8.5,
             alignment="left")

    # The detail panel: one entry per numbered marker, plus the offense/
    # defense tally. Baseball is not an even game -- a big hit swings more
    # win probability than almost any single out -- so expect this to lean
    # offense; the tally just makes that visible instead of implied.
    panel.axis("off")
    panel.set_xlim(0, 1)
    panel.set_ylim(0, 1)
    panel.text(0, 1.0, f"Largest plays   —   {offense_wins} offense, {defense_wins} defense",
              fontsize=10.5, fontweight="bold", va="top", transform=panel.transAxes)
    top = 0.90
    if ending_note:
        panel.text(0, top, ending_note, fontsize=9, va="top", style="italic",
                  color="#555555", wrap=True, transform=panel.transAxes)
        top -= 0.08
    # Each play is two lines. Place them with an explicit rhythm rather than
    # one text() call at linespacing 1.5: that left a moderate gap inside a
    # play and almost none between plays. Slot each play evenly, put the
    # narrative less than halfway down the slot so the between-play gap is
    # at least as large as the within-play one.
    n = max(len(panel_lines), 1)
    step = top / n
    within = 0.42 * step
    for i, entry in enumerate(panel_lines):
        header, detail = entry.split("\n", 1)
        y = top - i * step
        panel.text(0, y, header, fontsize=9.5, va="top",
                   family="DejaVu Sans", transform=panel.transAxes)
        panel.text(0, y - within, detail, fontsize=9.5, va="top",
                   family="DejaVu Sans", transform=panel.transAxes)

    fig.tight_layout(rect=(0.01, 0, 1, 1))
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main() -> None:
    game_id = DEFAULT_GAME
    n_swings = N_SWINGS
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--n-swings":
            if i + 1 >= len(args):
                sys.exit("--n-swings needs a value")
            n_swings = int(args[i + 1])
            if n_swings < 1:
                sys.exit("--n-swings must be at least 1")
            i += 2
            continue
        if arg.startswith("-"):
            sys.exit(f"unknown option: {arg}")
        game_id = arg
        i += 1

    model = Model()
    frame, game = build(model, game_id)

    # Sort-friendly filenames: timeline_YYYYMMDD_<game_id>.png
    date_tag = pd.Timestamp(game["game_date"]).strftime("%Y%m%d")
    out_path = DATA_DIR / f"timeline_{date_tag}_{game_id}.png"
    plot(model, frame, game, str(out_path), n_swings=n_swings)

    final = bool(game["is_final"])
    home_ahead = game["home_score"] > game["away_score"]
    tied = game["home_score"] == game["away_score"]
    focus = (game["home_team_name"] if tied or home_ahead
             else game["away_team_name"])
    low = frame["wp"].idxmin()
    n_steps = int(frame["swing"].notna().sum())
    print(f"{n_steps} state changes -> {out_path}")
    verb = "won" if final else ("leads" if not tied else "tied; tracking")
    print(f'{focus} {verb}; win probability bottomed out at '
          f'{frame["wp"].min():.3f} in the {frame.loc[low, "half"]} of the '
          f'{frame.loc[low, "inning"]}')
    print(f'  ({frame.loc[low, "narrative"]})')


if __name__ == "__main__":
    main()
