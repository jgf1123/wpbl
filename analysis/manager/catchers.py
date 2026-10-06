"""Everyone who caught in 2026, by team and games, to check against the cards' C eligibility.

    pixi run python analysis/manager/catchers.py
"""
import pandas as pd
from wpbl import tables
f=tables.read('fielding','all')
c=f[f.position.fillna('').str.split('/').apply(lambda s:'c' in s)]
g=c.groupby('person_name').agg(team=('team_name','last'),games=('game_id','nunique'),only_c=('position',lambda s:(s=='c').sum()),pb=('pb','sum'),sba=('sba','sum'))
print(g.sort_values(['team','games']).to_string())
