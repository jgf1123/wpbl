from wpbl.game_timeline import build
from wpbl.parse import ALL_DIR
from wpbl.usage_chart import CODES
from wpbl.win_probability import Model
import pandas as pd
# ALL_DIR = every game including postseason (OUT_DIR is regular-only by default)
games = pd.read_parquet(ALL_DIR / "games.parquet").set_index("game_id")
ids = sorted(pd.read_parquet(ALL_DIR / "plays.parquet")["game_id"].unique())
print("Loading WP model once...")
model = Model()
rows = []
for i, gid in enumerate(ids, 1):
    frame, game = build(model, gid)
    roller = float(frame["swing"].abs().sum(skipna=True))
    home = CODES.get(game["home_team_name"], "?")
    away = CODES.get(game["away_team_name"], "?")
    rows.append({
        "game_id": gid,
        "date": str(game.get("game_date", ""))[:10],
        "matchup": f"{away}@{home}",
        "score": f"{int(game['away_score'])}-{int(game['home_score'])}",
        "steps": len(frame) - 1,
        "rollercoaster": roller,
    })
    print(f"[{i}/{len(ids)}] {gid}  {roller:.3f}")
out = pd.DataFrame(rows).sort_values("rollercoaster", ascending=False)
print()
print(out.to_string(index=False, float_format=lambda x: f"{x:.3f}"))
print()
print(f"mean {out['rollercoaster'].mean():.3f}  "
      f"median {out['rollercoaster'].median():.3f}  "
      f"min {out['rollercoaster'].min():.3f}  "
      f"max {out['rollercoaster'].max():.3f}")
