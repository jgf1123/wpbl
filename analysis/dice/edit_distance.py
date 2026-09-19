"""Pairwise edit distance between every spelling of a name anywhere in the tables."""
import itertools
import unicodedata
import pandas as pd
from wpbl import tables

players = tables.read("players", "all")
plays = tables.read("plays", "all")
pid_of = players.groupby("player_name")["person_id"].agg(lambda s: set(s)).to_dict()


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c)).lower().strip()


def lev(a, b):
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


names = set(players["player_name"].dropna()) | set(players["person_name"].dropna())
from_plays = set()
for col in ("batter_name", "pitcher_name", "pitcher_name_feed", "first_base", "second_base", "third_base"):
    from_plays |= set(plays[col].dropna())
print(f"{len(names)} spellings in player rows; {len(from_plays)} in the play-by-play")
orphans = sorted(from_plays - names)
print("play-by-play names matching no player row:", orphans)

rows = []
for a, b in itertools.combinations(sorted(names | from_plays), 2):
    d = lev(fold(a), fold(b))
    if d <= 3:
        pa_, pb = pid_of.get(a, set()), pid_of.get(b, set())
        rows.append({"a": a, "b": b, "edits": d,
                     "same person?": "yes" if pa_ and pa_ == pb else ("n/a (not a player row)" if not (pa_ and pb) else "NO")})
print(pd.DataFrame(rows).sort_values("edits").to_string(index=False) if rows else "no pairs within 3 edits")
# near-misses on surname alone catch shortened first names ("Alexi" vs "Alexia")
last = {}
for n in names | from_plays:
    last.setdefault(fold(n).split()[-1], set()).add(n)
shared = {k: v for k, v in last.items() if len(v) > 1}
print("\nspellings sharing a surname:", {k: sorted(v) for k, v in shared.items()})
