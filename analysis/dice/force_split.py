"""With 2+ forced runners and <2 outs: which runner is out on a fielder's choice / double play?"""
import re
from collections import Counter
import pandas as pd
from wpbl import tables
from wpbl.batters import contact
from wpbl.run_expectancy import HALF_KEY, damaged_halves

plays = tables.read("plays", "training").sort_values(["game_id", "sequence"])
line = tables.read("line_score", "training")
games = tables.read("games", "training").set_index("game_id")
damaged = damaged_halves(plays, line, games)
plays["half_key"] = list(map(tuple, plays[HALF_KEY].values))
plays = plays[~plays["half_key"].isin(damaged)]
last_half = {g: blk["half_key"].iloc[-1] for g, blk in plays.groupby("game_id")}
BASE_WORD = {"second": 1, "third": 2, "home": 3}      # force at that base = runner from 1st/2nd/3rd
OUT_AT = re.compile(r"out at (second|third|home)")

rows = []
for key, half in plays.groupby("half_key", sort=False):
    live = [p for p in half.itertuples() if p.outs_before < 3]
    for i, p in enumerate(live):
        before = [p.first_base, p.second_base, p.third_base]
        if (p.play_kind != "plate_appearance" or p.outs_before >= 2
                or not (isinstance(before[0], str) and isinstance(before[1], str))):
            continue
        if i + 1 < len(live):
            nxt = live[i + 1]
            after = [nxt.first_base, nxt.second_base, nxt.third_base]
            made = int(nxt.outs_before) - int(p.outs_before)
        elif last_half.get(p.game_id) == key:
            continue
        else:
            after, made = [None] * 3, 3 - int(p.outs_before)
        if made < 1:
            continue
        runs = int(p.runs_scored)
        on_after = {x for x in after if isinstance(x, str)}
        batter_safe = p.batter_name in on_after
        # runners who vanished: those nearest home take the runs, the rest were out
        gone = [b for b in (3, 2, 1) if isinstance(before[b - 1], str) and before[b - 1] not in on_after]
        scored = gone[:runs]
        out_from = sorted(b for b in gone[runs:])
        text = str(p.narrative or "").lower()
        narr = sorted(BASE_WORD[w] for w in OUT_AT.findall(text))
        rows.append({"bases": "123" if isinstance(before[2], str) else "12_", "outs": int(p.outs_before),
                     "made": made, "batter_safe": batter_safe, "out_from": tuple(out_from),
                     "narr_out_from": tuple(narr), "label": contact(p.event_type, p.narrative),
                     "narrative": p.narrative})
f = pd.DataFrame(rows)
print(f"{len(f)} PAs: runners on 1st and 2nd (or loaded), <2 outs, at least one out made")
NAME = {1: "runner from 1st (force at 2nd)", 2: "runner from 2nd (force at 3rd)", 3: "runner from 3rd (force at home)"}

fc = f[f["batter_safe"] & (f["made"] == 1)]
print(f"\n=== fielder's choice: batter safe, one out ({len(fc)}) ===")
for bases, g in fc.groupby("bases"):
    print(f"  {bases}: " + ", ".join(f"{NAME.get(k[0], k) if len(k) == 1 else k}: {n}"
                                     for k, n in Counter(g["out_from"]).most_common()))
dis = fc[fc["out_from"] != fc["narr_out_from"]]
print(f"  name tracking vs narrative disagree on {len(dis)}:")
for r in dis.itertuples():
    print(f"    {r.bases} names say {r.out_from}, narrative says {r.narr_out_from}: {str(r.narrative)[:120]}")

dp = f[f["made"] >= 2]
print(f"\n=== double plays ({len(dp)}) ===")
print(dp.groupby(["bases", "batter_safe", "out_from"]).size().rename("n").to_string())
print("\nlabels:", dp["label"].value_counts().to_dict())

dp0 = dp[dp["outs"] == 0]
print(f"\n=== double plays with nobody out, where the next play shows who is left ({len(dp0)}) ===")
for r in dp0.itertuples():
    print(f"  {r.bases} batter_safe={r.batter_safe} out_from={r.out_from} narr={r.narr_out_from}: {str(r.narrative)[:130]}")
