"""Win probability timeline for a single game, one step per base-out change.

    pixi run timeline-chart -- <game_id>       (defaults to the Aug 1 NY/LA game)

A step is any play that changes the base-out state: a plate appearance, a
stolen base or caught stealing, a wild pitch or passed ball, a balk, or a
pickoff that actually gets the runner. A failed pickoff attempt, a
substitution, and a pitching change change nothing about the state a batter
faces, so they are not steps.

Each step's height is the home team's win probability the instant before that
play resolves -- the same state-to-win-probability lookup used everywhere else
in this project. Holding that value until the next step is exactly right at a
half-inning boundary too: the next step is the first play of the following
half-inning, already reflecting the updated score and the reset to bases empty,
nobody out.
"""

from __future__ import annotations

import sys

import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from wpbl.parse import OUT_DIR
from wpbl.win_probability import Model, REGULATION

DEFAULT_GAME = "8alsgvzc90ypwphl"

# Anything that leaves a batter facing a different base-out picture than the
# one before it. Substitutions, pitching changes, and failed pickoff attempts
# are deliberately excluded -- none of them move a runner or add an out.
STATE_CHANGING = {"plate_appearance", "plate_appearance_unknown",
                  "baserunning", "baserunning_out", "balk"}

TOP_COLORS = plt.cm.Blues(np.linspace(0.45, 0.85, REGULATION))
BOTTOM_COLORS = plt.cm.Oranges(np.linspace(0.45, 0.85, REGULATION))
N_SWINGS = 6


def _bases(play) -> str:
    return (("1" if pd.notna(play.first_base) else "_")
            + ("2" if pd.notna(play.second_base) else "_")
            + ("3" if pd.notna(play.third_base) else "_"))


def build(model: Model, game_id: str) -> tuple[pd.DataFrame, dict]:
    plays = pd.read_parquet(OUT_DIR / "plays.parquet")
    games = pd.read_parquet(OUT_DIR / "games.parquet").set_index("game_id")
    game = games.loc[game_id]

    steps = plays[(plays["game_id"] == game_id) & (plays["inning"] <= REGULATION)
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
            "batter": play.batter_name,
            "pitcher": play.pitcher_name,
            "event_type": play.event_type,
            "narrative": play.narrative,
            "runs_scored": int(play.runs_scored),
        })

    # Extend the last step to the settled result, so the chart's final segment
    # reads as a result rather than trailing off at whatever it last measured.
    home_won = game["home_score"] > game["away_score"]
    rows.append({
        "sequence": rows[-1]["sequence"] + 1, "inning": rows[-1]["inning"],
        "half": rows[-1]["half"], "outs_before": 3, "bases": "___",
        "diff": int(game["home_score"] - game["away_score"]),
        "wp_home": 1.0 if home_won else 0.0,
        "batter": None, "pitcher": None, "event_type": "final",
        "narrative": f'Final: {game["away_team_name"]} {int(game["away_score"])}, '
                    f'{game["home_team_name"]} {int(game["home_score"])}',
        "runs_scored": 0,
    })

    frame = pd.DataFrame(rows).reset_index(drop=True)
    frame["swing"] = frame["wp_home"].diff().fillna(0.0)
    return frame, dict(game)


def plot(frame: pd.DataFrame, game: dict, game_id: str, out_path: str) -> None:
    fig, ax = plt.subplots(figsize=(15, 7))

    x = np.arange(len(frame))
    ax.step(x, frame["wp_home"], where="post", color="#333333", linewidth=1.4, zorder=3)

    # One coloured band per half-inning, so the eye can chunk the game without
    # reading every tick label.
    half_groups = frame.assign(half_key=list(zip(frame["inning"], frame["half"])))
    seen = []
    for key, group in half_groups.groupby("half_key", sort=False):
        seen.append((key, group.index.min(), group.index.max()))
    for (inning, half), start, end in seen:
        color = (TOP_COLORS if half == "top" else BOTTOM_COLORS)[inning - 1]
        ax.axvspan(start - 0.5, end + 0.5, color=color, alpha=0.35, zorder=0)
        mid = (start + end) / 2
        label = f'{"Top" if half == "top" else "Bot"} {inning}'
        ax.text(mid, 1.035, label, ha="center", va="bottom", fontsize=8.5,
                color="#555555", clip_on=False)

    ax.axhline(0.5, color="#999999", linewidth=0.8, linestyle="--", zorder=1)

    # Annotate the largest swings, alternating above/below so labels do not
    # collide when two big plays land close together.
    biggest = frame.reindex(frame["swing"].abs().sort_values(ascending=False).index)
    biggest = biggest[biggest.index > 0].head(N_SWINGS)
    for rank, (idx, row) in enumerate(biggest.iterrows()):
        y_before = frame.loc[idx - 1, "wp_home"]
        y_after = row["wp_home"]
        y_mid = (y_before + y_after) / 2
        above = rank % 2 == 0
        text_y = min(y_mid + 0.16, 0.97) if above else max(y_mid - 0.16, 0.03)
        note = str(row["narrative"] or row["event_type"])
        if len(note) > 62:
            note = note[:59] + "..."
        ax.annotate(
            f"{row['swing']:+.2f}  {note}",
            xy=(idx, y_after), xytext=(idx, text_y),
            fontsize=8, ha="center",
            va="bottom" if above else "top",
            arrowprops=dict(arrowstyle="-", color="#666666", lw=0.8,
                            shrinkA=0, shrinkB=3),
            bbox=dict(boxstyle="round,pad=0.25", fc="white", ec="#999999", lw=0.6),
        )

    ax.set_xlim(-0.5, len(frame) - 0.5)
    ax.set_ylim(0, 1)
    ax.set_ylabel(f'{game["home_team_name"]} win probability')
    ax.set_xlabel("Base-out state change, in order")
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
    ax.set_xticks([])

    result = "won" if game["home_score"] > game["away_score"] else "lost"
    ax.set_title(
        f'{game["away_team_name"]} at {game["home_team_name"]}, {game["game_date"]}  '
        f'({game["home_team_name"]} {result}, '
        f'{int(game["away_score"])}-{int(game["home_score"])} away-home)',
        fontsize=13, pad=28)

    legend = [Line2D([0], [0], color=TOP_COLORS[3], lw=6, alpha=0.6,
                     label=f'{game["away_team_name"]} batting'),
             Line2D([0], [0], color=BOTTOM_COLORS[3], lw=6, alpha=0.6,
                     label=f'{game["home_team_name"]} batting')]
    ax.legend(handles=legend, loc="lower left", fontsize=9, framealpha=0.9)

    fig.tight_layout()
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def main() -> None:
    game_id = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_GAME
    model = Model()
    frame, game = build(model, game_id)

    out_path = OUT_DIR.parent / f"timeline_{game_id}.png"
    plot(frame, game, game_id, str(out_path))

    print(f"{len(frame) - 1} state changes -> {out_path}")
    print(f'peak {game["home_team_name"]} win probability: '
          f'{frame["wp_home"].max():.3f} at step {frame["wp_home"].idxmax()}')
    print(f'lowest: {frame["wp_home"].min():.3f} at step {frame["wp_home"].idxmin()}')
    print("\nlargest swings:")
    biggest = frame.reindex(frame["swing"].abs().sort_values(ascending=False).index)
    for idx, row in biggest[biggest.index > 0].head(N_SWINGS).iterrows():
        print(f'  {row["swing"]:+.3f}  inning {row["inning"]} {row["half"]}  '
              f'{str(row["narrative"])[:80]}')


if __name__ == "__main__":
    main()
