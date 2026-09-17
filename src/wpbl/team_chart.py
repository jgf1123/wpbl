"""Runs a game from each team's offense, from its tilted run distribution.

    pixi run team-chart                      # -> data/img/team_offense_runs_per_game.png
    pixi run team-chart out.png

One line per offense: the share of seven-inning games in which it scores each
total, batting all seven innings against a league-average defense. Each half-inning
is drawn from the league's run distribution tilted by that offense's rating
(team_strength.py), and seven of them are added up by convolution.

The convolution is done for every posterior draw of the ratings and then
averaged, because a team's strength is fixed for the length of a game: averaging
the half-inning distributions first would treat each inning as if it could come
from a different version of the team.

Defenses are left out. Their ratings sit within half a point of league on every
run total, so their lines would be indistinguishable. The league-average line is
left out too: the Queens' offense is almost exactly league average, and the two
lines would overlap.
"""

from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from wpbl.game_timeline import TEAM_COLORS
from wpbl.parse import DATA_DIR
from wpbl.team_strength import TeamStrength, tilted_pmfs

DEFAULT_OUT = DATA_DIR / "img" / "team_offense_runs_per_game.png"
INNINGS = 7
SHOW = 20                    # runs on the x-axis
INK, MUTED, GRID = "#222222", "#666666", "#e4e4e4"


def game_runs(ts: TeamStrength, tilts: np.ndarray) -> np.ndarray:
    """Share of games with each run total over INNINGS half-innings, posterior mean."""
    games = []
    for pmf in tilted_pmfs(ts.base, tilts):
        total = np.array([1.0])
        for _ in range(INNINGS):
            total = np.convolve(total, pmf)
        games.append(total)
    width = max(len(g) for g in games)
    return np.mean([np.pad(g, (0, width - len(g))) for g in games], axis=0)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = Path(args[0]) if args else DEFAULT_OUT
    out.parent.mkdir(parents=True, exist_ok=True)

    ts = TeamStrength()
    s = ts.samples
    x = np.arange(SHOW + 1)

    fig, ax = plt.subplots(figsize=(7.28, 4.4), dpi=200)
    curves = {}
    for team in sorted(ts.teams, key=lambda t: -float(np.mean(ts.offense(s, t)))):
        dist = game_runs(ts, s[:, 0] + ts.offense(s, team))
        mean = float((np.arange(len(dist)) * dist).sum())
        name = ts.names[team]
        curves[team] = (dist, mean)
        ax.plot(x, 100 * dist[:SHOW + 1], color=TEAM_COLORS.get(name, "#555555"),
                linewidth=2.2, label=f"{name}  {mean:.1f} runs a game", zorder=3)

    # No floating labels: the curves cross and bunch near their peaks, so any
    # label there is ambiguous. The legend is ordered strongest offense first,
    # which is the order the curves stack in on the right half of the chart.

    ax.set_xticks(range(0, SHOW + 1, 2))
    ax.set_xlim(0, SHOW)
    ax.set_ylim(0, None)
    ax.set_xlabel("Runs in the game", fontsize=9, color=INK)
    ax.set_ylabel("Share of games (%)", fontsize=9, color=INK)
    ax.tick_params(labelsize=8.5, colors=INK)
    ax.yaxis.grid(True, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)

    fig.suptitle("Runs a game, by offense", x=0.02, ha="left", fontsize=12,
                 color=INK, y=0.985)
    fig.text(0.02, 0.935, "Batting all seven innings against a league-average defense. "
             "The Queens are almost exactly league average.",
             ha="left", va="top", fontsize=8.5, color=MUTED)
    ax.legend(loc="upper right", fontsize=8.5, frameon=False)

    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(out)
    plt.close(fig)
    print(f"-> {out}")
    for team, (dist, mean) in curves.items():
        print(f"  {ts.names[team]:26s} mean {mean:.2f}  most likely {int(dist.argmax())}")


if __name__ == "__main__":
    main()
