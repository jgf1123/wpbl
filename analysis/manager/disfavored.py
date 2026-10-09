"""Every pitcher's regular-season and postseason usage, to list pitchers the teams stopped calling on.

    pixi run python analysis/manager/disfavored.py
"""
import pandas as pd
from wpbl import tables
p=tables.read('pitching','all'); g=tables.read('games','all')
p=p.merge(g[['game_id','is_postseason']],on='game_id')
# team per person: most recent team name
p=p.sort_values('game_date')
reg=p[~p.is_postseason]; post=p[p.is_postseason]
last_reg=reg.game_date.max()
agg=reg.groupby('person_id').agg(name=('person_name','last'),team=('team_name','last'),app=('game_id','nunique'),gs=('is_starter','sum'),ip_outs=('ip_outs','sum'),pitches=('pitches','sum'),first=('game_date','min'),last=('game_date','max'))
pa=post.groupby('person_id').agg(post_app=('game_id','nunique'),post_outs=('ip_outs','sum'))
a=agg.join(pa).fillna({'post_app':0,'post_outs':0})
a['ip']=(a.ip_outs//3).astype(int).astype(str)+'.'+(a.ip_outs%3).astype(int).astype(str)
a['post_ip']=(a.post_outs//3).astype(int).astype(str)+'.'+(a.post_outs%3).astype(int).astype(str)
a['days_since_last']=(pd.to_datetime(last_reg)-pd.to_datetime(a['last'])).dt.days
# team appearances per team for context
a=a.sort_values(['team','ip_outs'],ascending=[True,False])
pd.set_option('display.width',250)
print('last regular-season date', last_reg, '; postseason dates', sorted(post.game_date.unique()))
print(a[['name','team','app','gs','ip','pitches','first','last','days_since_last','post_app','post_ip']].to_string())
