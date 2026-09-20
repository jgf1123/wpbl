"""Same label, different base-out outcome: play label x the out line that reproduces it."""
from collections import Counter
import pandas as pd
SRC = open(__file__.replace("label_vs_line.py", "proposals.py"), encoding="utf-8").read()
SRC = SRC.replace('print(f"\n=== B.', 'if False: print(f"\n=== B.')
start = SRC.index("# ---------------- B: out types by base-out transition")
head = SRC[:SRC.index("# ---------------- A: quartiles")]
body = SRC[start:SRC.index('for rule in ("lead", "trail"):')]
exec(head + body)
rows = []
for r in f.itertuples():
    cand = candidates(tuple(c != "_" for c in r.bases), r.outs, "trail")
    if r.actual[0] is None:
        matched = [k for k, v in cand.items() if v[0] is None]
    else:
        matched = [k for k, v in cand.items() if v == r.actual]
    rows.append({"label": r.label, "line": min(matched, key=len) if matched else "none", "made": r.made})
t = pd.DataFrame(rows)
print(f"{len(t)} PAs: runners on, <2 outs, an out made (36 games)")
print(pd.crosstab(t["label"], t["line"]).to_string())
air = t["label"].isin(["lineout", "flyout", "popup", "foul_out"])
print("\nair outs with 2 outs made (doubled off):", int((air & (t["made"] >= 2)).sum()),
      " of which lineouts:", int(((t["label"] == "lineout") & (t["made"] >= 2)).sum()))
g = t["label"] == "groundout"
print("groundouts reproduced as B+ / F+ / FB+ (runners advanced):", int((g & t["line"].str.endswith("+")).sum()), "of", int(g.sum()))
print("groundouts reproduced as plain B (runners held):", int((g & (t["line"] == "B")).sum()))
