"""How WPBL used the DH: lineup sizes, starting pitchers who batted, and fielders brought in to pitch.

    pixi run python analysis/manager/dh_rules.py
"""
import pandas as pd
T='data/tables/'
bat=pd.read_parquet(T+'batting.parquet'); st=pd.read_parquet(T+'pitching_stints.parquet'); pl=pd.read_parquet(T+'plays.parquet')
pa=pl[pl.is_plate_appearance]
sl=bat[bat.in_starting_lineup==True]
dh=sl.groupby(['game_id','team_id']).agg(n=('player_name','size'), dhpos=('lineup_position',lambda s:(s.str.lower()=='dh').any())).reset_index()
print('starting lineup sizes:', dh.n.value_counts().to_dict(), ' DH listed:', dh.dhpos.sum(), 'of', len(dh))
rows=[]
for _,s in st.iterrows():
    b=pa[(pa.game_id==s.game_id)&(pa.batter_id==s.pitcher_id)]
    if b.empty: continue
    before=(b.sequence<s.first_sequence).sum(); during=((b.sequence>=s.first_sequence)&(b.sequence<=s.last_sequence)).sum(); after=(b.sequence>s.last_sequence).sum()
    br=bat[(bat.game_id==s.game_id)&(bat.player_id==s.pitcher_id)]
    lp=br.lineup_position.iloc[0] if len(br) else None; pos=br.position.iloc[0] if len(br) else None
    d=dh[(dh.game_id==s.game_id)&(dh.team_id==s.pitching_team_id)]
    rows.append(dict(game=s.game_id[-6:],team=s.pitching_team_id,pitcher=s.pitcher_name,starter=s.is_starter,start_pos=lp,pos=pos,team_dh=bool(d.dhpos.iloc[0]) if len(d) else None,pa_before=before,pa_during=during,pa_after=after))
r=pd.DataFrame(rows)
pd.set_option('display.width',250); pd.set_option('display.max_rows',300)
print('\nA. starting pitchers who batted and kept batting after leaving the mound')
print(r[r.starter&(r.pa_after>0)].to_string())
print('\nB. relievers who batted earlier in the game (in the lineup before pitching)')
print(r[~r.starter&(r.pa_before>0)].to_string())
print('\ncounts: starters who batted', (r.starter).sum(), '; of those kept batting after', (r.starter&(r.pa_after>0)).sum())
