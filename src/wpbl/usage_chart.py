"""Render each team's pitcher usage, game by game, inning by inning.

    pixi run chart          # writes data/usage.html

Geometry comes from the box score's innings-pitched figures: a pitcher's outs
accumulate in appearance order, so her segment spans exactly the outs she was
responsible for. That agrees with the entry inning derived independently from
the play-by-play in every appearance, so partial innings are exact rather
than approximate.

Colour identifies the pitcher. Each team's seven busiest arms by innings take
the first seven categorical slots; everyone below them shares the eighth. Slots
are assigned per team, so the same colour means a different person in a
different panel -- each panel carries its own key.
"""

from __future__ import annotations

import html

import pandas as pd

from wpbl.parse import OUT_DIR

OUTPUT = OUT_DIR.parent / "usage.html"

# Layout, in SVG user units.
GUTTER = 190          # left column: game, date, opponent, result
PLOT = 672
ROW = 32
BAR = 19
RULER = 30
MAX_INNINGS = 8       # longest game in the data; keeps every panel on one scale

# Three-letter codes keep the row label from crowding the score.
CODES = {"Boston Hunters": "BOS", "Los Angeles Queens": "LAQ",
         "New York Heights": "NYH", "San Francisco Firebells": "SFF"}

# The validated categorical order, light and dark steps. Both modes pass every
# adjacent-pair gate; light WARNs on contrast for aqua/yellow/magenta, for which
# the relief is the direct labels and table view this page already carries.
PALETTE_LIGHT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100",
                 "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
PALETTE_DARK = ["#3987e5", "#d95926", "#199e70", "#c98500",
                "#d55181", "#008300", "#9085e9", "#e66767"]
NAMED = 7             # pitchers with their own colour; the rest share slot 8


def _luminance(hex_colour: str) -> float:
    channels = []
    for i in (1, 3, 5):
        v = int(hex_colour[i:i + 2], 16) / 255
        channels.append(v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4)
    r, g, b = channels
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def label_ink(fill: str) -> str:
    """White or near-black, whichever reads better on this fill.

    White on the yellow slot is illegible, so the label colour has to follow the
    fill rather than being fixed.
    """
    lum = _luminance(fill)
    on_white = 1.05 / (lum + 0.05)
    on_black = (lum + 0.05) / (_luminance("#101310") + 0.05)
    return "#ffffff" if on_white >= on_black else "#101310"


def ip_text(outs: int) -> str:
    return f"{outs // 3}.{outs % 3}"


def collect() -> list[dict]:
    pitching = pd.read_parquet(OUT_DIR / "pitching.parquet")
    stints = pd.read_parquet(OUT_DIR / "pitching_stints.parquet")
    team_games = pd.read_parquet(OUT_DIR / "team_games.parquet").sort_values("game_date")
    team_games["gm"] = team_games.groupby("team_name").cumcount() + 1

    entry = stints.set_index(["game_id", "pitching_team_id", "pitcher_id"])
    pitching = pitching.sort_values(["game_date", "appear_order"])
    # Outs accumulate in the order pitchers took the mound.
    pitching["end_out"] = pitching.groupby(["game_id", "team_id"])["ip_outs"].cumsum()
    pitching["start_out"] = pitching["end_out"] - pitching["ip_outs"]

    teams = []
    for team_name, rows in team_games.groupby("team_name"):
        staff_all = pitching[pitching["team_id"] == rows["team_id"].iloc[0]]
        # Rank by innings, then appearances, then name, so the colour assignment
        # is deterministic across rebuilds.
        ranked = (staff_all.groupby("person_name")
                  .agg(outs=("ip_outs", "sum"), app=("game_id", "size"),
                       gs=("is_starter", "sum"), bf=("bf", "sum"))
                  .reset_index()
                  .sort_values(["outs", "app", "person_name"], ascending=[False, False, True]))
        slots, key = {}, []
        for rank, row in enumerate(ranked.itertuples(index=False)):
            slot = min(rank, NAMED)
            slots[row.person_name] = slot
            key.append({"name": row.person_name, "slot": slot, "outs": int(row.outs),
                        "ip": ip_text(int(row.outs)), "app": int(row.app),
                        "gs": int(row.gs), "bf": int(row.bf), "named": rank < NAMED})

        games = []
        for _, game in rows.sort_values("gm").iterrows():
            staff = pitching[(pitching["game_id"] == game["game_id"])
                             & (pitching["team_id"] == game["team_id"])]
            arms = []
            for _, arm in staff.iterrows():
                lookup = (arm["game_id"], arm["team_id"], arm["player_id"])
                entered = entry.loc[lookup] if lookup in entry.index else None
                arms.append({
                    "name": arm["person_name"],
                    "slot": slots[arm["person_name"]],
                    "start": int(arm["start_out"]),
                    "outs": int(arm["ip_outs"]),
                    "ip": arm["ip"],
                    "starter": bool(arm["is_starter"]),
                    "bf": int(arm["bf"]),
                    "pitches": int(arm["pitches"]),
                    "enteredInning": int(entered["entered_inning"]) if entered is not None else None,
                    "enteredOuts": int(entered["entered_outs"]) if entered is not None else None,
                    "runners": int(entered["entered_runners_on"]) if entered is not None else None,
                })
            games.append({
                "gm": int(game["gm"]),
                "date": pd.Timestamp(game["game_date"]).strftime("%b %d").replace(" 0", " "),
                "opponent": game["opponent_team_name"],
                "home": bool(game["is_home"]),
                "won": bool(game["won"]),
                "runs": int(game["runs"]),
                "against": int(game["opponent_runs"]),
                "outs": int(staff["ip_outs"].sum()),
                "arms": arms,
            })
        teams.append({
            "team": team_name, "games": games, "key": key,
            "record": f"{int(rows['won'].sum())}-{int((~rows['won']).sum())}",
        })
    return teams


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        return f"{n}th"
    return f"{n}{ {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th') }"


def span_text(arm: dict) -> str:
    if arm["bf"] == 0:
        # Posted as the starting pitcher, then moved to a fielding position
        # before anyone came to the plate. Not the same thing as failing to
        # record an out, and it should not read as though it were.
        return "announced, never faced a batter"
    if arm["outs"] == 0:
        return f"{ordinal(arm['enteredInning'])}, no outs recorded"
    first = arm["start"] // 3 + 1
    last = (arm["start"] + arm["outs"] - 1) // 3 + 1
    return ordinal(first) if first == last else f"{ordinal(first)}-{ordinal(last)}"


def svg_panel(team: dict) -> str:
    games = team["games"]
    height = RULER + len(games) * ROW + 6
    width = GUTTER + PLOT + 12
    scale = PLOT / MAX_INNINGS / 3  # px per out
    parts = [f'<svg viewBox="0 0 {width} {height}" width="100%" height="{height}" '
             f'role="img" aria-label="Pitcher usage by inning for {html.escape(team["team"])}">']

    for inning in range(MAX_INNINGS + 1):
        x = GUTTER + inning * 3 * scale
        parts.append(f'<line class="rule" x1="{x:.1f}" y1="{RULER - 8}" '
                     f'x2="{x:.1f}" y2="{height - 6}"/>')
        if inning < MAX_INNINGS:
            parts.append(f'<text class="tick" x="{x + 1.5 * scale:.1f}" y="{RULER - 14}" '
                         f'text-anchor="middle">{inning + 1}</text>')

    for index, game in enumerate(games):
        mid = RULER + index * ROW + ROW / 2
        opponent = f'{"vs" if game["home"] else "@"} {CODES.get(game["opponent"], "???")}'
        parts.append(f'<text class="glabel dim" x="0" y="{mid + 4:.1f}">g{game["gm"]}</text>')
        parts.append(f'<text class="glabel" x="26" y="{mid + 4:.1f}">'
                     f'{html.escape(game["date"])}</text>')
        parts.append(f'<text class="glabel" x="84" y="{mid + 4:.1f}">'
                     f'{html.escape(opponent)}</text>')
        parts.append(f'<text class="score {"win" if game["won"] else "loss"}" x="{GUTTER - 14}" '
                     f'y="{mid + 4:.1f}" text-anchor="end">{"W" if game["won"] else "L"} '
                     f'{game["runs"]}-{game["against"]}</text>')
        parts.append(f'<rect class="track" x="{GUTTER}" y="{mid - BAR / 2:.1f}" '
                     f'width="{game["outs"] * scale:.1f}" height="{BAR}" rx="4"/>')

        for arm in game["arms"]:
            x = GUTTER + arm["start"] * scale
            if arm["bf"] == 0:
                # She never took the mound in any real sense; drawing a marker
                # would put her on the timeline alongside pitchers who did.
                continue
            if arm["outs"] == 0:
                # No outs recorded: she occupies no innings, so a block would lie.
                parts.append(f'<path class="noout s{arm["slot"]}" '
                             f'd="M{x:.1f} {mid - BAR / 2 - 5:.1f} l4.5 0 l-4.5 6.5 l-4.5 -6.5 Z">'
                             f'<title>{html.escape(arm["name"])} - {html.escape(span_text(arm))}; '
                             f'{arm["bf"]} batters faced, {arm["pitches"]} pitches</title></path>')
                continue
            w = arm["outs"] * scale - 2  # 2px surface gap between segments
            tip = (f'{arm["name"]} - {span_text(arm)}, {arm["ip"]} IP\n'
                   f'{arm["bf"]} batters faced, {arm["pitches"]} pitches')
            if arm["starter"]:
                tip += "\nstarted"
            elif arm["enteredInning"]:
                tip += (f'\nentered {ordinal(arm["enteredInning"])}, {arm["enteredOuts"]} out'
                        f'{"s" if arm["enteredOuts"] != 1 else ""}, {arm["runners"]} on')
            parts.append(f'<g class="seg s{arm["slot"]}">'
                         f'<rect x="{x:.1f}" y="{mid - BAR / 2:.1f}" '
                         f'width="{max(w, 3):.1f}" height="{BAR}" rx="4"/>'
                         f'<title>{html.escape(tip)}</title>')
            # Full name, else surname, else nothing -- a truncated stub would be
            # ambiguous (Schiano and Schroder share three letters).
            surname = arm["name"].split()[-1]
            fits = next((t for t in (arm["name"], surname) if w > len(t) * 6.4 + 14), None)
            if fits:
                parts.append(f'<text class="seglabel" x="{x + 7:.1f}" y="{mid + 4:.1f}">'
                             f'{html.escape(fits)}</text>')
            parts.append("</g>")
    parts.append("</svg>")
    return "".join(parts)


def key_block(team: dict) -> str:
    named = [k for k in team["key"] if k["named"]]
    rest = [k for k in team["key"] if not k["named"]]
    items = []
    for entry in named:
        relief = entry["app"] - entry["gs"]
        if entry["gs"] and relief:
            role = f'{entry["gs"]} GS, {relief} RP'
        elif entry["gs"]:
            role = f'{entry["gs"]} GS'
        else:
            role = f'{relief} RP'
        if entry["bf"] == 0:
            role = "never faced a batter"
        items.append(f'<li><span class="sw s{entry["slot"]}"></span>'
                     f'<span class="nm">{html.escape(entry["name"])}</span>'
                     f'<span class="ip">{entry["ip"]}</span>'
                     f'<span class="rl">{role}</span></li>')
    if len(rest) == 1:
        # A single pitcher in the last slot is just another pitcher -- calling
        # her "1 more" and giving her a full-width row would be noise.
        only = rest[0]
        relief = only["app"] - only["gs"]
        role = (f'{only["gs"]} GS, {relief} RP' if only["gs"] and relief
                else (f'{only["gs"]} GS' if only["gs"] else f'{relief} RP'))
        if only["bf"] == 0:
            role = "never faced a batter"
        items.append(f'<li><span class="sw s{NAMED}"></span>'
                     f'<span class="nm">{html.escape(only["name"])}</span>'
                     f'<span class="ip">{only["ip"]}</span>'
                     f'<span class="rl">{role}</span></li>')
    elif rest:
        outs = sum(k["outs"] for k in rest)
        names = ", ".join(html.escape(k["name"]) for k in rest)
        items.append(f'<li class="wide"><span class="sw s{NAMED}"></span>'
                     f'<span class="nm">{names}</span>'
                     f'<span class="tail">{ip_text(outs)} across {len(rest)} pitchers</span></li>')
    return f'<ul class="key">{"".join(items)}</ul>'


def table_rows(team: dict) -> str:
    rows = []
    for game in team["games"]:
        for arm in game["arms"]:
            rows.append(
                "<tr>"
                f'<td>{game["gm"]}</td>'
                f'<td>{"vs" if game["home"] else "@"} {html.escape(game["opponent"])}</td>'
                f'<td><span class="sw s{arm["slot"]}"></span>{html.escape(arm["name"])}</td>'
                f'<td>{"Started" if arm["starter"] else "Relieved"}</td>'
                f'<td>{html.escape(span_text(arm))}</td>'
                f'<td class="num">{arm["ip"]}</td>'
                f'<td class="num">{arm["bf"]}</td>'
                f'<td class="num">{arm["pitches"]}</td>'
                "</tr>")
    return "".join(rows)


def series_css():
    light = "\n".join(f"  --s{i}: {c};\n  --s{i}-ink: {label_ink(c)};"
                      for i, c in enumerate(PALETTE_LIGHT))
    dark = "\n".join(f"    --s{i}: {c};\n    --s{i}-ink: {label_ink(c)};"
                     for i, c in enumerate(PALETTE_DARK))
    rules = "\n".join(
        f".s{i} rect, path.noout.s{i} {{ fill: var(--s{i}); }}\n"
        f"span.sw.s{i} {{ background: var(--s{i}); }}\n"
        f".s{i} .seglabel {{ fill: var(--s{i}-ink); }}"
        for i in range(len(PALETTE_LIGHT)))
    return light, dark, rules


def render(teams: list[dict]) -> str:
    panels = []
    for team in teams:
        arms = [a for g in team["games"] for a in g["arms"]]
        panels.append(f"""
<section class="panel">
  <header class="panel-head">
    <h2>{html.escape(team["team"])}</h2>
    <p class="meta">{len(team["games"])} games &middot; {team["record"]} &middot;
      {len(team["key"])} pitchers used</p>
  </header>
  {key_block(team)}
  <div class="scroll">{svg_panel(team)}</div>
  <details>
    <summary>Table view &mdash; {len(arms)} appearances</summary>
    <div class="scroll">
      <table>
        <thead><tr><th>Gm</th><th>Opponent</th><th>Pitcher</th><th>Role</th>
          <th>Innings</th><th class="num">IP</th><th class="num">BF</th>
          <th class="num">Pit</th></tr></thead>
        <tbody>{table_rows(team)}</tbody>
      </table>
    </div>
  </details>
</section>""")
    light, dark, rules = series_css()
    return (TEMPLATE.replace("{{SERIES_LIGHT}}", light)
            .replace("{{SERIES_DARK}}", dark)
            .replace("{{SERIES_RULES}}", rules)
            .replace("{{GAMES}}", str(sum(len(t["games"]) for t in teams) // 2))
            .replace("{{APPEARANCES}}", str(sum(len(g["arms"]) for t in teams for g in t["games"])))
            .replace("{{PANELS}}", "".join(panels)))


TEMPLATE = """<title>WPBL Pitcher Innings</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap">
<style>
:root {
  --ground: #f7f8f6;
  --surface: #ffffff;
  --ink: #14181a;
  --ink-2: #55605c;
  --ink-3: #7d8783;
  --hair: #dde2de;
  --track: #e7ebe6;
  --win: #1f6f4a;
  --loss: #96524a;
{{SERIES_LIGHT}}
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --ground: #16191a;
    --surface: #1c2021;
    --ink: #eef1ee;
    --ink-2: #a4aeaa;
    --ink-3: #7d8783;
    --hair: #2c3231;
    --track: #262b2b;
    --win: #63b98d;
    --loss: #d78a82;
{{SERIES_DARK}}
  }
}
:root[data-theme="dark"] {
  --ground: #16191a;
  --surface: #1c2021;
  --ink: #eef1ee;
  --ink-2: #a4aeaa;
  --ink-3: #7d8783;
  --hair: #2c3231;
  --track: #262b2b;
  --win: #63b98d;
  --loss: #d78a82;
{{SERIES_DARK}}
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--ground);
  color: var(--ink);
  font-family: Archivo, "Helvetica Neue", Arial, sans-serif;
  font-size: 15px;
  line-height: 1.5;
  -webkit-font-smoothing: antialiased;
}
.wrap { max-width: 1000px; margin: 0 auto; padding: 40px 24px 72px; }
header.top { border-bottom: 1px solid var(--hair); padding-bottom: 20px; margin-bottom: 28px; }
h1 { font-size: 27px; font-weight: 700; letter-spacing: -0.015em; margin: 0 0 6px; text-wrap: balance; }
.sub { color: var(--ink-2); margin: 0 0 10px; max-width: 65ch; }
.sub:last-child { margin-bottom: 0; }
.panel { background: var(--surface); border: 1px solid var(--hair); border-radius: 10px;
  padding: 20px 20px 14px; margin-bottom: 22px; }
.panel-head { margin-bottom: 12px; }
h2 { font-size: 18px; font-weight: 600; margin: 0; letter-spacing: -0.01em; }
.meta { margin: 3px 0 0; font-size: 13px; color: var(--ink-2); font-variant-numeric: tabular-nums; }
ul.key { list-style: none; margin: 0 0 16px; padding: 0;
  display: grid; grid-template-columns: repeat(auto-fill, minmax(min(250px, 100%), 1fr)); gap: 4px 20px; }
ul.key li { display: flex; align-items: center; gap: 7px; font-size: 12.5px; min-width: 0; }
ul.key li.wide { grid-column: 1 / -1; align-items: baseline; flex-wrap: wrap; }
ul.key .tail { color: var(--ink-3); font-size: 11.5px; flex: none;
  font-family: "IBM Plex Mono", ui-monospace, monospace; }
span.sw { width: 11px; height: 11px; border-radius: 3px; flex: none; }
ul.key li.wide span.sw { align-self: center; }
ul.key .nm { color: var(--ink); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
ul.key li.wide .nm { white-space: normal; }
ul.key .ip { color: var(--ink-2); font-family: "IBM Plex Mono", ui-monospace, monospace;
  font-size: 11.5px; margin-left: auto; flex: none; padding-left: 10px; }
ul.key .rl { color: var(--ink-3); font-size: 11.5px; flex: none; width: 72px; text-align: right; }
.scroll { overflow-x: auto; }
svg { display: block; min-width: 874px; }
.rule { stroke: var(--hair); stroke-width: 1; }
.tick { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11px; fill: var(--ink-3); }
.glabel { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11.5px; fill: var(--ink-2); }
.glabel.dim { fill: var(--ink-3); }
.score { font-family: "IBM Plex Mono", ui-monospace, monospace; font-size: 11.5px; font-weight: 500; }
.score.win { fill: var(--win); }
.score.loss { fill: var(--loss); }
.track { fill: var(--track); }
.seg { cursor: default; }
.seg:hover rect { filter: brightness(1.08); }
.seglabel { font-size: 12px; font-weight: 500; pointer-events: none; }
{{SERIES_RULES}}
details { margin-top: 10px; border-top: 1px solid var(--hair); padding-top: 8px; }
summary { cursor: pointer; font-size: 13px; color: var(--ink-2); }
summary:focus-visible { outline: 2px solid var(--s0); outline-offset: 3px; border-radius: 3px; }
table { border-collapse: collapse; width: 100%; margin-top: 10px; font-size: 13px; }
th, td { text-align: left; padding: 5px 10px 5px 0; border-bottom: 1px solid var(--hair); white-space: nowrap; }
td .sw { display: inline-block; margin-right: 6px; vertical-align: middle; }
th { color: var(--ink-3); font-weight: 500; font-size: 11.5px; text-transform: uppercase; letter-spacing: 0.05em; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums;
  font-family: "IBM Plex Mono", ui-monospace, monospace; }
footer { color: var(--ink-3); font-size: 13px; margin-top: 30px; max-width: 65ch; }
footer p { margin: 0 0 8px; }
</style>
<div class="wrap">
  <header class="top">
    <h1>Which innings each pitcher covered</h1>
    <p class="sub">WPBL 2026, all {{GAMES}} completed games. Every bar is one game, split at the exact out
      each pitcher handed off &mdash; a segment ending two-thirds through the 5th means she was
      pulled with two out. Regulation is seven innings, and the leftmost segment is always the
      starter.</p>
    <p class="sub">Colour identifies the pitcher. Each team's seven busiest arms by innings get
      their own colour and everyone below them shares the last one, so read colour against the key
      in that panel &mdash; the same colour is a different person on a different team.</p>
  </header>
  {{PANELS}}
  <footer>
    <p><strong>Reading a row.</strong> The scale is fixed across every panel, so bar length is
      directly comparable: a short track means a short game, not a short outing.</p>
    <p>Boundaries come from the box score's innings-pitched figures, accumulated in the order
      pitchers appeared. They agree with the entry inning derived independently from the
      play-by-play in all {{APPEARANCES}} appearances.</p>
  </footer>
</div>
"""


def main() -> None:
    teams = collect()
    # Emit pure ASCII with numeric character references, so accented names
    # survive regardless of what charset the host declares when serving.
    page = render(teams).encode("ascii", "xmlcharrefreplace").decode("ascii")
    OUTPUT.write_text(page, encoding="utf-8")
    print(f"{OUTPUT}")
    for team in teams:
        shared = [k["name"] for k in team["key"] if not k["named"]]
        print(f"  {team['team']:24s} {len(team['key']):2d} pitchers; "
              f"slot 8 shared by {len(shared)}: {', '.join(shared) or '-'}")


if __name__ == "__main__":
    main()
