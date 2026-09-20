"""Season shape for the blog's opening paragraph: what the 37 training games are."""
import pandas as pd

from wpbl import tables
from wpbl.dice import plate_appearances

pd.set_option("display.width", 220)
allg = tables.read("games", "all")
pa = plate_appearances()
tid = set(pa["game_id"].unique())
g = allg[allg["game_id"].isin(tid)]
print(f"{len(g)} games carry the training plate appearances")
print("  regular season:", int(g["is_regular_season"].sum()),
      "| postseason:", int(g["is_postseason"].sum()))
played = allg[allg["is_final"] & allg["has_boxscore"]]
print(f"\nall finished games with a boxscore: {len(played)} "
      f"({int(played['is_regular_season'].sum())} regular, {int(played['is_postseason'].sum())} postseason)")
out = played[~played["game_id"].isin(tid)]
cols = ["game_date", "home_team_name", "away_team_name", "home_score", "away_score", "is_postseason"]
print("\nfinished games NOT in the training set:")
print(out[cols].to_string(index=False) if len(out) else "  (none)")
if len(out):
    print("  runs in those games:", int((out["home_score"] + out["away_score"]).sum()))
