"""The drawing shared by the batter and pitcher charts.

Both are the same picture: a few text columns naming the player and her
counting stats, then two ratings drawn on one axis -- a dot for the estimate
and a bar for its 95% interval. A table of intervals makes the reader subtract
one bracket from another to tell whether two players differ; bars that overlap
answer it at a glance, which is the whole reason these exist.

Sized like table_image output -- exactly WIDTH_PX wide, no title, no caption --
so the images drop into a post beside the tables.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.textpath import TextPath

from wpbl.table_image import (BAND, DPI, INK, MARGIN_PX, MONOSPACE, MONOSPACE_BOLD,
                              PROPORTIONAL, PROPORTIONAL_BOLD, RULE, WIDTH_PX)

FONT_PX = 11.5          # smaller than table_image's 13: text columns and a plot share 728px
ROW_PX = 21
GAP_PX = 13             # between text columns
TICK = 0.2              # axis gridline spacing, runs
BAR_PX = 2.6
DOT_PX = 5.5
OFFSET_PX = 3.6         # how far each series sits from the row's centre line

SITUATIONAL = "#d97706"  # amber: what actually happened (RE24)
MODELLED = "#1d4ed8"     # blue: what the player did, stripped of context


def points(px: float) -> float:
    """Matplotlib sizes type, lines and markers in points; the layout is in pixels."""
    return px * 72 / DPI


def measure(text: str, prop) -> float:
    return TextPath((0, 0), text, size=FONT_PX, prop=prop).get_extents().width


def signed(value: float, digits: int) -> str:
    return f"{value:+.{digits}f}".replace("-", "−")


def draw(out: Path, headers, numeric, cells, series, tick: float = TICK) -> int:
    """Render one chart and return its pixel height.

    headers/numeric/cells describe the text columns, one tuple per row; series
    is a list of (label, colour, estimates, lows, highs), drawn top to bottom
    within each row and named in a legend that doubles as the plot's header."""
    columns, x = [], MARGIN_PX
    for j, header in enumerate(headers):
        body = MONOSPACE if numeric[j] else PROPORTIONAL
        head = MONOSPACE_BOLD if numeric[j] else PROPORTIONAL_BOLD
        width = max([measure(header, head)] + [measure(c[j], body) for c in cells])
        columns.append((x, width))
        x += width + GAP_PX

    # Fit the axis to the bars rather than to the next round tick beyond them:
    # rounding the ends out can waste a seventh of the plot's width.
    x0, x1 = x + 8, WIDTH_PX - MARGIN_PX - 14
    low = min(np.min(lo) for _, _, _, lo, _ in series)
    high = max(np.max(hi) for _, _, _, _, hi in series)
    vmin, vmax = low - 0.02, high + 0.02

    def place(value: float) -> float:
        return x0 + (value - vmin) / (vmax - vmin) * (x1 - x0)

    header_y = MARGIN_PX + ROW_PX / 2
    top_ticks = MARGIN_PX + ROW_PX * 1.5
    body_top = MARGIN_PX + ROW_PX * 2
    body_bottom = body_top + len(cells) * ROW_PX
    bottom_ticks = body_bottom + ROW_PX / 2
    height = int(round(body_bottom + ROW_PX + MARGIN_PX))

    figure = plt.figure(figsize=(WIDTH_PX / DPI, height / DPI), dpi=DPI)
    ax = figure.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH_PX)
    ax.set_ylim(height, 0)
    ax.axis("off")
    size = points(FONT_PX)

    for i in range(0, len(cells), 2):
        ax.add_patch(plt.Rectangle((MARGIN_PX, body_top + i * ROW_PX),
                                   WIDTH_PX - 2 * MARGIN_PX, ROW_PX,
                                   color=BAND, lw=0, zorder=0))

    for value in np.arange(np.ceil(vmin / tick), np.floor(vmax / tick) + 1) * tick:
        zero = abs(value) < 1e-9
        ax.plot([place(value)] * 2, [body_top, body_bottom],
                color="#8a918a" if zero else RULE,
                lw=points(1.3 if zero else 0.8), zorder=1)
        label = "0" if zero else signed(value, 1)
        for y in (top_ticks, bottom_ticks):
            ax.text(place(value), y, label, ha="center", va="center",
                    fontsize=size * 0.9, fontproperties=MONOSPACE, color=INK)

    for j, header in enumerate(headers):
        left, width = columns[j]
        ax.text(left + width if numeric[j] else left, header_y, header,
                ha="right" if numeric[j] else "left", va="center", fontsize=size,
                fontproperties=MONOSPACE_BOLD if numeric[j] else PROPORTIONAL_BOLD,
                color=INK)

    legend_x = x0
    for label, colour, *_ in series:
        ax.plot([legend_x, legend_x + 16], [header_y] * 2, color=colour,
                lw=points(BAR_PX), alpha=0.45, solid_capstyle="butt")
        ax.plot([legend_x + 8], [header_y], "o", color=colour, ms=points(DOT_PX), mew=0)
        ax.text(legend_x + 21, header_y, label, ha="left", va="center", fontsize=size,
                fontproperties=PROPORTIONAL_BOLD, color=INK)
        legend_x += 21 + measure(label, PROPORTIONAL_BOLD) + 18

    offsets = (np.arange(len(series)) - (len(series) - 1) / 2) * 2 * OFFSET_PX
    for i, text in enumerate(cells):
        y = body_top + (i + 0.5) * ROW_PX
        for j, value in enumerate(text):
            left, width = columns[j]
            ax.text(left + width if numeric[j] else left, y, value,
                    ha="right" if numeric[j] else "left", va="center", fontsize=size,
                    fontproperties=MONOSPACE if numeric[j] else PROPORTIONAL, color=INK)
        for (_, colour, estimate, lo, hi), dy in zip(series, offsets):
            ax.plot([place(lo[i]), place(hi[i])], [y + dy] * 2, color=colour,
                    lw=points(BAR_PX), alpha=0.45, solid_capstyle="butt", zorder=2)
            ax.plot([place(estimate[i])], [y + dy], "o", color=colour,
                    ms=points(DOT_PX), mew=0, zorder=3)

    out.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(out, dpi=DPI, facecolor="white")
    plt.close(figure)
    return height
