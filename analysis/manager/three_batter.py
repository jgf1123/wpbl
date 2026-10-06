"""Relief outings that faced fewer than three batters and left mid-inning (the three-batter minimum in WPBL).

    pixi run python analysis/manager/three_batter.py
"""
import pandas as pd
T='data/tables/'
st=pd.read_parquet(T+'pitching_stints.parquet'); pl=pd.read_parquet(T+'plays.parquet')
rel=st[~st.is_starter]
res=[]
for _,s in rel.iterrows():
    g=pl[pl.game_id==s.game_id].sort_values('sequence')
    last=g[g.sequence==s.last_sequence].iloc[0]
    nxt=g[(g.sequence>s.last_sequence)&g.is_plate_appearance]
    mid = len(nxt)>0 and nxt.iloc[0].inning==last.inning and nxt.iloc[0].half==last.half
    res.append((s.pitcher_name,s.game_id[-6:],s.batters_faced,mid))
r=pd.DataFrame(res,columns=['p','g','bf','mid'])
print('relief stints',len(r),' bf<3:',(r.bf<3).sum(),' bf<3 and removed mid-inning:',((r.bf<3)&r.mid).sum())
print(r[(r.bf<3)&r.mid].to_string())
