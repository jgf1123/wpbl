"""How the real managers used their players: the manager AI's conventions
(manager_spec.md, "Option 4, revealed preference" and "Lineup conventions").

The dice game has no fielding, so nothing in it justifies a weak bat at
shortstop. The conventions put players where their teams put them anyway:

  window       each team's late season -- the second half of its regular
               season, each game weight 1 -- and its postseason, weight 2
  the nine     most weighted starts in the window, not counting starts at P
  positions    a player is eligible where she started 2+ times (any game, any
               team: a traded player keeps her positions)
  roles        a starter has 2+ starts in her team's last 10 games, postseason
               included; everyone else is a reliever
  conflicts    a player kept out of the window by a conflict, not a benching, is
               credited at her start rate up to her last appearance
"""
from __future__ import annotations

import re
import unicodedata
from collections import defaultdict

from wpbl import tables

POST_WEIGHT = 2
ELIGIBLE_STARTS = 2
STARTER_STARTS, ROLE_GAMES = 2, 10
CONFLICT = {"Thaima Maximiliana"}          # user, 2026-10-04: a conflict from 29 Aug
TEAMS = {"Boston": "BOS", "Los Angeles": "LAQ", "New York": "NYH", "San Francisco": "SFF"}


def _norm(s):
    return re.sub(r"[^a-z]", "", unicodedata.normalize("NFKD", s)
                  .encode("ascii", "ignore").decode().lower())


def _team(name):
    return next(v for k, v in TEAMS.items() if name.startswith(k))


class Usage:
    def __init__(self, cards):
        names = {_norm(n): n for n in list(cards.batter) + list(cards.pitcher)}
        games = tables.read("games", "all")[["game_id", "is_postseason"]]
        bat = tables.read("batting", "all").merge(games, on="game_id")
        bat = bat.assign(card=bat["person_name"].map(lambda n: names.get(_norm(n))),
                         team=bat["team_name"].map(_team))
        st = bat[bat["in_starting_lineup"] == True]
        st = st.assign(pos=st["lineup_position"].str.upper())

        self.starts_at = defaultdict(int)              # (name, pos) -> starts, all games
        for r in st.itertuples():
            self.starts_at[(r.card, r.pos)] += 1

        self.weight = defaultdict(float)               # (team, name) -> weighted window starts
        self.weight_at = defaultdict(float)            # (team, name, pos) -> the same at pos
        for team in TEAMS.values():
            ts = st[st["team"] == team]
            reg = ts[~ts["is_postseason"]]
            dates = sorted(reg["game_date"].unique())
            cut = dates[len(dates) // 2]
            window = [(reg[reg["game_date"] >= cut], 1.0), (ts[ts["is_postseason"]], POST_WEIGHT)]
            total = sum(w * part["game_id"].nunique() for part, w in window)
            for part, w in window:
                for r in part[part["pos"] != "P"].itertuples():
                    self.weight[(team, r.card)] += w
                    self.weight_at[(team, r.card, r.pos)] += w
            for name in CONFLICT:
                mine = bat[(bat["card"] == name) & (bat["team"] == team)]
                if mine.empty:
                    continue
                last = mine["game_date"].max()
                played = bat[(bat["team"] == team) & (bat["game_date"] <= last)]["game_id"].nunique()
                before = st[(st["card"] == name) & (st["team"] == team) & (st["pos"] != "P")
                            & (st["game_date"] <= last)]
                rate = before["game_id"].nunique() / played
                self.weight[(team, name)] = rate * total
                for pos, n in before["pos"].value_counts().items():
                    self.weight_at[(team, name, pos)] = rate * total * n / len(before)

        pit = tables.read("pitching", "all")
        pit = pit.assign(card=pit["person_name"].map(lambda n: names.get(_norm(n))),
                         team=pit["team_name"].map(_team))
        self.starters = {}
        for team in TEAMS.values():
            tp = pit[pit["team"] == team]
            order = tp.drop_duplicates("game_id").sort_values("game_date")["game_id"]
            last = tp[tp["game_id"].isin(set(order.iloc[-ROLE_GAMES:]))]
            gs = last[last["is_starter"] == True].groupby("card")["game_id"].nunique()
            self.starters[team] = set(gs[gs >= STARTER_STARTS].index)

    def eligible(self, name, pos):
        return pos == "DH" or self.starts_at[(name, pos)] >= ELIGIBLE_STARTS
