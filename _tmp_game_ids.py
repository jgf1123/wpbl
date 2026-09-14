from wpbl.parse import OUT_DIR
import pandas as pd

games = pd.read_parquet(OUT_DIR / "games.parquet")
plays = pd.read_parquet(OUT_DIR / "plays.parquet")
print("games columns:", games.columns.tolist())
print("n games:", len(games))
# completed games with plays
with_plays = set(plays["game_id"].unique())
print("with plays:", len(with_plays))
ids = sorted(with_plays)
for gid in ids:
    row = games.loc[games["game_id"] == gid].iloc[0]
    print(gid, row.get("status", ""), f"{row.get('away_score','?')}-{row.get('home_score','?')}")
