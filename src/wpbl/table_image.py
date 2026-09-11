"""Render a table as a PNG sized for Substack, which has no table support.

    pixi run table out.png < table.md      # paste a markdown table in
    pixi run table out.png table.md        # or point at a file
    ... | pixi run table out.png           # or pipe anything tab-separated

Reads a markdown or tab-separated table on stdin (or from a file argument) and
writes a PNG. Nothing is transcribed: copy the table, pipe it in, get an image.
Markdown emphasis is stripped rather than rendered, and the |---| separator row
is discarded, so a table copied straight out of a chat window works.

Every image comes out exactly WIDTH_PX wide, because Substack resizes uploads
to 728px and an image that arrives at some other width gets resampled -- which
is what makes screenshotted tables look soft. The table is measured, scaled to
fit that width, and centred in it. A wide table shrinks its type to fit; a
narrow one keeps full-size type and sits centred in the frame rather than being
stretched, since stretching a four-column table across 728px puts oceans
between the columns and makes it harder to read, not easier.

Text is measured properly, glyph by glyph, rather than by counting characters:
a column of "1.12 [0.97, 1.28] n=418" is much wider than its character count
suggests in a proportional face, and guessing produces either clipping or slack.

Numeric columns are right-aligned in a monospaced face so digits line up, which
is most of what makes a table of figures readable. Alignment is inferred: a
column is numeric when every non-empty cell in it parses as a number.

No title and no caption are drawn -- those belong to whatever the image is
being placed into.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.font_manager import FontProperties
from matplotlib.textpath import TextPath

WIDTH_PX = 728          # Substack's column width
DPI = 200               # rendering resolution; the pixel width is what matters
MARGIN_PX = 8           # breathing room at the frame edge
# Space between one column's text and the next, as a multiple of the type
# size rather than a fixed pixel count -- a gap that stays 14px while the type
# shrinks to fit a wide table drifts from too tight to too loose. At 1.8 the
# columns read as separate without a rule between them; below about 1.2 a
# left-aligned column runs into the right-aligned one beside it and the header
# row reads as one run-on phrase.
CELL_GAP_EMS = 1.8
ROW_PAD_PX = 9          # vertical padding within a row
FONT_PX = 13.0          # target type size before any shrink-to-fit
MIN_FONT_PX = 7.5       # below this a table is unreadable; let it clip instead

INK = "#101310"
RULE = "#c9cec9"
BAND = "#f4f6f4"
PROPORTIONAL = FontProperties(family="DejaVu Sans")
MONOSPACE = FontProperties(family="DejaVu Sans Mono")
# Headers are drawn bold, and in a numeric column they are drawn monospaced
# like the figures beneath them. Measuring them in the plain proportional face
# under-reports their width, which is how a long header such as
# "Opportunities" ends up in a column sized for "331" and overruns its
# neighbour. Measure every string in the face and weight it is drawn in.
PROPORTIONAL_BOLD = FontProperties(family="DejaVu Sans", weight="bold")
MONOSPACE_BOLD = FontProperties(family="DejaVu Sans Mono", weight="bold")

EMPHASIS = re.compile(r"\*\*|__|`")
SEPARATOR = re.compile(r"^:?-{2,}:?$")
NUMBER = re.compile(r"^[+\-−]?[\d,]*\.?\d+%?$")


def _numeric(value: str) -> bool:
    return bool(NUMBER.match(str(value).strip().replace("·", "").strip()))


def _text_width(text: str, font: FontProperties) -> float:
    """Width of a string at font size 1, in the same units as the size.

    Measured from the glyph outlines, so it is right for proportional faces
    where character counting is not.
    """
    if not text:
        return 0.0
    return TextPath((0, 0), text, size=1.0, prop=font).get_extents().width


def parse(text: str) -> tuple[list[str], list[list[str]]]:
    """Rows out of a markdown or tab-separated table."""
    table = []
    for line in text.splitlines():
        line = EMPHASIS.sub("", line).strip()
        if not line:
            continue
        if "|" in line:
            cells = [c.strip() for c in line.strip("|").split("|")]
        elif "\t" in line:
            cells = [c.strip() for c in line.split("\t")]
        else:
            continue
        if all(SEPARATOR.match(c) for c in cells if c):
            continue
        table.append(cells)
    if not table:
        raise SystemExit("no table found -- expected markdown pipes or tabs")
    width = max(len(row) for row in table)
    table = [row + [""] * (width - len(row)) for row in table]
    return table[0], table[1:]


def render(path: str | Path, header: list[str], rows: list[list]) -> Path:
    """Draw the table at exactly WIDTH_PX and save it."""
    body = [[str(cell) for cell in row] for row in rows]
    columns = len(header)
    right = [all(_numeric(row[i]) for row in body if row[i].strip())
             for i in range(columns)]
    fonts = [MONOSPACE if r else PROPORTIONAL for r in right]
    head_fonts = [MONOSPACE_BOLD if r else PROPORTIONAL_BOLD for r in right]

    # Widest cell in each column, per unit of font size. The header counts, in
    # the face and weight it will actually be drawn in.
    unit = [max([_text_width(header[i], head_fonts[i])]
                + [_text_width(row[i], fonts[i]) for row in body])
            for i in range(columns)]

    # Solve for the type size with the gap included, since the gap scales with
    # it: total = sum(text) * font + columns * gap_ems * font.
    usable = WIDTH_PX - 2 * MARGIN_PX
    font_px = min(FONT_PX, usable / (sum(unit) + columns * CELL_GAP_EMS))
    font_px = max(MIN_FONT_PX, font_px)
    gap = CELL_GAP_EMS * font_px

    widths = [u * font_px + gap for u in unit]
    table_px = sum(widths)
    left = max(MARGIN_PX, (WIDTH_PX - table_px) / 2)      # centre it

    row_px = font_px + 2 * ROW_PAD_PX
    height_px = row_px * (len(body) + 1) + 2 * MARGIN_PX

    fig = plt.figure(figsize=(WIDTH_PX / DPI, height_px / DPI), dpi=DPI)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, WIDTH_PX)
    ax.set_ylim(0, height_px)
    ax.axis("off")

    edges = [left]
    for w in widths:
        edges.append(edges[-1] + w)
    points = font_px * 72 / DPI          # matplotlib wants points, not pixels

    def draw(cells, centre, bold=False):
        for i, cell in enumerate(cells):
            if right[i]:
                x, align = edges[i + 1] - gap / 2, "right"
            else:
                x, align = edges[i] + gap / 2, "left"
            ax.text(x, centre, cell, fontsize=points, va="center", ha=align,
                    color=INK, weight="bold" if bold else "normal",
                    fontproperties=(MONOSPACE if right[i] else PROPORTIONAL))

    y = height_px - MARGIN_PX
    draw(header, y - row_px / 2, bold=True)
    y -= row_px
    ax.plot([left, left + table_px], [y, y], color=INK, lw=1.0)

    for n, row in enumerate(body):
        if n % 2 == 1:
            ax.add_patch(plt.Rectangle((left, y - row_px), table_px, row_px,
                                       color=BAND, zorder=0))
        draw(row, y - row_px / 2)
        y -= row_px
    ax.plot([left, left + table_px], [y, y], color=RULE, lw=0.8)

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=DPI, facecolor="white")
    plt.close(fig)
    return path


def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    if not args:
        raise SystemExit("usage: pixi run table OUT.png [INPUT]   "
                         "(input defaults to stdin)")
    out = args[0]
    if len(args) > 1:
        text = Path(args[1]).read_text(encoding="utf-8")
    else:
        text = sys.stdin.buffer.read().decode("utf-8", "replace")
    header, rows = parse(text)
    written = render(out, header, rows)
    print(f"{len(rows)} rows x {len(header)} columns -> {written}")


if __name__ == "__main__":
    main()
