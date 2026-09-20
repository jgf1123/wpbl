"""Figure 2 of the blog: the batter card as a tree, with one player's numbers on it.

    pixi run python analysis/dice/fig_card_tree.py [out.png] [--who="Denae Benites"]

Each branch carries the player's own share, raw and on her card, as a share of the
group it sits in. The point the figure makes: smoothing moves what is inside a
branch (her singles) and leaves the branch above it almost untouched.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from wpbl import tables
from wpbl.batters import contact
from wpbl.parse import DATA_DIR

INK, MUTED, GRID = "#222222", "#666666", "#c9c9c9"
MOVED, STEADY = "#c2410c", "#1b6ca8"
TO = {"strikeout": "K", "walk": "BB", "hit_by_pitch": "HBP", "home_run": "HR",
      "single": "1B", "double": "2B", "triple": "2B", "reached_on_error": "ROE"}
ALL = ["K", "BB", "HBP", "HR", "1B", "2B", "ROE", "OUT"]

args = [a for a in sys.argv[1:] if not a.startswith("--")]
who = next((a.split("=", 1)[1] for a in sys.argv[1:] if a.startswith("--who=")), "Denae Benites")
out = Path(args[0]) if args else DATA_DIR / "img" / "dice_card_tree.png"
out.parent.mkdir(parents=True, exist_ok=True)

plays = tables.read("plays", "training")
players = tables.read("players", "training")
person = players.set_index("player_id")["person_id"].to_dict()
name = players.drop_duplicates("person_id").set_index("person_id")["person_name"].to_dict()
pa = plays[(plays["play_kind"] == "plate_appearance") & (plays["outs_before"] < 3)].copy()
pa["line"] = [TO.get(contact(e, n), "OUT") for e, n in zip(pa["event_type"], pa["narrative"])]
pa["B"] = pa["batter_id"].map(person).fillna(pa["batter_id"])
pid = next(k for k, v in name.items() if v == who)
mine = pa[pa["B"] == pid]
raw = (100 * mine["line"].value_counts().reindex(ALL).fillna(0) / len(mine)).to_dict()
row = pd.read_csv(DATA_DIR / "dice" / "cards_batters.csv").set_index("player").loc[who]
hs = row["HBP share of FP"] / 100
card = {"K": row["K"], "BB": row["FP"] * (1 - hs), "HBP": row["FP"] * hs, "HR": row["HR"],
        "1B": row["1B"], "2B": row["2B"], "ROE": row["ROE"], "OUT": row["OUT"]}

TTO, PARK = ["K", "BB", "HBP", "HR"], ["1B", "2B", "ROE", "OUT"]
FP, KFP, REST = ["BB", "HBP"], ["K", "BB", "HBP"], ["2B", "ROE", "OUT"]
T = {"label": "Every plate appearance", "of": ALL, "kids": [
    {"label": "No ball in play", "of": TTO, "kids": [
        {"label": "Home run", "of": ["HR"]},
        {"label": "Strikeout or free pass", "of": KFP, "kids": [
            {"label": "Strikeout", "of": ["K"]},
            {"label": "Free pass", "of": FP, "kids": [
                {"label": "Walk", "of": ["BB"]},
                {"label": "Hit by pitch", "of": ["HBP"]}]}]}]},
    {"label": "Ball in play", "of": PARK, "kids": [
        {"label": "Single", "of": ["1B"]},
        {"label": "Not a single", "of": REST, "kids": [
            {"label": "Out", "of": ["OUT"]},
            {"label": "Double or error", "of": ["2B", "ROE"], "kids": [
                {"label": "Double", "of": ["2B"]},
                {"label": "Error", "of": ["ROE"]}]}]}]}]}

LEAF_GAP = 1.55            # vertical room for a label plus its two numbers
counter = [0]


def place(node, depth, parent_of):
    node["x"] = depth
    node["raw"] = 100 * sum(raw[c] for c in node["of"]) / sum(raw[c] for c in parent_of)
    node["card"] = 100 * sum(card[c] for c in node["of"]) / sum(card[c] for c in parent_of)
    kids = node.get("kids")
    if not kids:
        node["y"] = counter[0] * LEAF_GAP
        counter[0] += 1
    else:
        for kid in kids:
            place(kid, depth + 1, node["of"])
        node["y"] = sum(k["y"] for k in kids) / len(kids)
    return node


place(T, 0, ALL)
fig, ax = plt.subplots(figsize=(7.28, 5.9), dpi=200)


def draw(node, root=False):
    kids = node.get("kids", [])
    if kids:
        mid = node["x"] + 0.80          # elbow: out, down, then in to each child
        ax.plot([node["x"] + 0.62, mid], [-node["y"], -node["y"]],
                color=GRID, linewidth=1.1, zorder=1, solid_capstyle="round")
        ax.plot([mid, mid], [-kids[0]["y"], -kids[-1]["y"]],
                color=GRID, linewidth=1.1, zorder=1, solid_capstyle="round")
    for kid in kids:
        ax.plot([mid, kid["x"] - 0.03], [-kid["y"], -kid["y"]],
                color=GRID, linewidth=1.1, zorder=1, solid_capstyle="round")
        draw(kid)
    move = abs(node["card"] - node["raw"])
    color = MOVED if move >= 5 else (STEADY if move < 1.5 else INK)
    ax.text(node["x"], -node["y"] + 0.10, node["label"], fontsize=8.5,
            color=INK if not root else MUTED, va="bottom", ha="left", zorder=3,
            bbox=dict(facecolor="white", edgecolor="none", pad=1.0))
    if not root:
        ax.text(node["x"], -node["y"] - 0.16, f"{node['raw']:.0f}%  →  {node['card']:.0f}%",
                fontsize=8.5, color=color, va="top", ha="left", zorder=3,
                fontweight="bold" if move >= 5 else "normal")


draw(T, root=True)
ax.set_xlim(-0.30, 5.05)
ax.set_ylim(-7 * LEAF_GAP - 0.95, 1.05)
ax.axis("off")
fig.suptitle(f"A card is built in steps: {who}'s", x=0.02, ha="left",
             fontsize=12, color=INK, y=0.985)
fig.text(0.02, 0.935, "Each percentage is a share of the group just to its left, her own record "
         "then her card. Smoothing takes\nnearly a fifth off her singles (orange) and leaves the "
         "split above almost where it was (blue).",
         ha="left", va="top", fontsize=8.5, color=MUTED)
fig.tight_layout(rect=(0, 0, 1, 0.90))
fig.savefig(out)
plt.close(fig)
print(f"-> {out}")
