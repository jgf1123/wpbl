import pandas as pd
from wpbl import tables
from wpbl.batters import classify, contact
from wpbl.dice import TO_LINE
p = tables.read("plays", "training")
pa = p[(p["play_kind"] == "plate_appearance") & (p["outs_before"] < 3)].copy()
pa["feed"] = [classify(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
pa["contact"] = [contact(e, n) for e, n in zip(pa["event_type"], pa["narrative"])]
pa["card"] = pa["contact"].map(TO_LINE).fillna("OUT")
print(len(pa))
print(pd.crosstab(pa["feed"], pa["card"], margins=True).to_string())
