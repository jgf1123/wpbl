"""Play a whole season's schedule, so the CROSS-DAY half of the track is tested.

    pixi run season-fatigue

Spec 9 check 3 asks for two things: stint lengths and 7-DAY LOADS. Only the first
has ever been run. The only fatigue simulator before this one played a single game
at a time and reset the track to zero at every outing, so the entry cost and the
recovery rate -- the two settings that exist only to link one day to the next --
never engaged in any code path that ran. E = 30 and R = 20 were chosen by solving
two inequalities by hand (spec 7.9); nothing had ever simulated them.

What this adds is a CALENDAR. Each team plays its real dates, carries every
pitcher's track between them, recovers R a day, and charges E when she enters.
The track is the rulebook's count throughout: a rested arm sits at -30, so
entering puts her at 0 and her first twenty game pitches are fresh.

THE USAGE RULE IS DESCRIPTIVE, the same choice section 7.5 made and for the same
reason -- a fatigue setting only has consequences where a tired pitcher is left
in, so a rule sampled from real usage is enough to make E and R identifiable, and
a fitted one would make check 3 circular. Three draws, all from the real season:

    who starts    her team's real share of starts
    who relieves  her team's real share of relief outings
    how long      a stint target from the real distribution by role

The one thing the calendar adds is AVAILABILITY, and it is not fitted either: a
pitcher can be picked only if entering would not put her straight past her own
capacity, i.e. track + E <= capacity. That is the rulebook's own boundary used as
a manager's floor, not a new parameter. When a staff has nobody available the
freshest arm pitches anyway and the game is counted -- see `forced`, which is a
result rather than a nuisance: it says how often these settings ask a team to
field an arm no real manager would have had to.

WHAT THIS CANNOT SAY. The pitchers-per-game excess of section 7.5 is inherited,
because each stint is still drawn independently and the last arm of a game is cut
off by the seventh inning rather than by her target. A staff plan would fix it,
and that is the AI manager's job rather than this module's.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from wpbl import tables, workload
from wpbl.dice import (B_CELLS, CAPACITY_DEFAULT, PITCH_COST, capacity, cards,
                       line_weights, pitcher_columns, plate_appearances,
                       played_lines, to_cells)
from wpbl.engine import (ENTRY_COST, INNINGS, RECOVERY, RESTED, Table,
                         column_for, lineups, plate_appearance, recover, steal)

WINDOW = 7                 # days, the same window workload.py measures


def schedules():
    """Each team's real games, as a date per GAME, in order.

    Every game the feed has, TRAINING_EXCLUDED included: an arm carries what it
    threw whether or not the game is fit to train a card on, and the calendar is
    the thing being tested.

    FILTER TO is_final, because the feed gives ONE GAME SEVERAL game_ids. The 71
    rows are 40 played games plus 31 "Not Started" placeholders for the same
    fixtures -- BOS at NYH on 13 Aug appears three times, and it was one game.
    `is_final` separates them exactly: all 40 final rows have play-by-play and none
    of the 31 do. Taking the rows at face value triples some fixtures and inflates
    the season to 140 team-games against a real 80, which is enough to make the
    staff look as though it collapses.

    Counting DISTINCT DATES per team happens to give the same answer here, since
    no team ever plays twice in a day, but it would silently swallow a real
    doubleheader. The filter says what is meant.
    """
    games = tables.read("games", "all")
    games = games[games["is_final"]]
    days: dict[str, list] = {}
    for col in ("home_team_name", "away_team_name"):
        for team, grp in games.groupby(col):
            if not str(team).strip():
                continue                       # one feed row has no team name
            days.setdefault(team, []).extend(
                pd.to_datetime(grp["game_date"]).dt.normalize().tolist())
    return {t: sorted(v) for t, v in days.items()}


def staffs():
    """Per team: her pitchers, her share of starts, her share of relief outings.

    Weights are within the TEAM. The superseded one-game simulator could only
    approximate this with a league-wide draw -- a season needs each staff to be the
    set of arms that staff actually has, or availability means nothing.
    """
    pa = plate_appearances()
    first = pa.groupby(["game_id", "P_team"])["P"].first()
    rows = []
    for (gm, tm, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        if first.get((gm, tm)) == pid:
            role = "start"
        else:
            role = ("late" if int(grp.sort_values("sequence")["inning"].iloc[0]) >= LATE_FROM
                    else "middle")
        rows.append((tm, pid, role))
    out = pd.DataFrame(rows, columns=["team", "P", "role"])
    staff = {}
    for team, grp in out.groupby("team"):
        arms = sorted(grp["P"].unique())
        w = {}
        for role in ("start", "middle", "late"):
            c = (grp[grp["role"] == role]["P"].value_counts()
                 .reindex(arms).fillna(0).to_numpy(float))
            w[role] = c
        if any(v.sum() == 0 for v in w.values()):
            continue
        staff[team] = (arms, w["start"] / w["start"].sum(),
                       w["middle"] / w["middle"].sum(), w["late"] / w["late"].sum())
    return staff



# Relief splits in two, and the splitter is the INNING SHE ENTERS (spec 7.14).
# Measured over the real outings: arms entering from the sixth finish the game 81%
# of the time and throw a median 24 pitches; arms entering earlier finish 30% of
# the time and throw 35. The two groups separate on entry inning and length,
# neither of which was used to define them. The score is deliberately NOT used:
# only 10% of game-ending relief came with a 1-3 run lead, and the median stint is
# flat at 23-26 pitches whether she is protecting a lead or mopping up, so this is
# a "throw the last inning" role rather than a save-situation closer. Using the
# inning keeps the rule observable to the simulator instead of edging into the AI
# manager.
LATE_FROM = 6                # innings 1-5 are MIDDLE relief, 6-7 are LATE

# A change does not happen the moment a pitcher passes her target: real managers
# mostly wait for the inning to end. Measured over the real outings, the share of
# relievers who came in MID-inning rather than to start one:
#
#   late relief    17%   (83% start an inning, and span exactly 1)
#   middle relief  43%   (57% start an inning, and span 3)
#
# Hooking mid-inning every time fragments late relief especially: a closer brought
# in with one out left throws five pitches, and the simulated late stint came out
# at 14 against a real 22. Waiting for the boundary unless the roll says otherwise
# is descriptive in the same way the stint draw is -- it resamples when managers
# actually changed, rather than fitting a rule to them.
MID_INNING = {"middle": 0.43, "late": 0.17}


def role_stints():
    """Stint lengths by role: start, middle relief, late relief.

    The same real outings, split by the inning she entered. (This replaced
    `engine.stint_targets`, which pooled relief into one role and has been
    deleted along with the one-sided simulator that used it.)
    """
    pa = plate_appearances()
    pa = pa.assign(pitches=[PITCH_COST.get(l, 3.3) for l in pa["line"]])
    first = pa.groupby(["game_id", "P_team"])["P"].first()
    out = {"start": [], "middle": [], "late": []}
    for (gid, team, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        grp = grp.sort_values("sequence")
        if first.get((gid, team)) == pid:
            role = "start"
        else:
            role = "late" if int(grp["inning"].iloc[0]) >= LATE_FROM else "middle"
        out[role].append(float(grp["pitches"].sum()))
    return {k: np.array(v) for k, v in out.items()}



_START_W: dict = {}          # calibrated weights, cached per process


def calibrated_start_weights(iters=5, n_seasons=8, seed=4242, damp=0.6):
    """Starter-draw weights that reproduce the OBSERVED per-pitcher start counts.

    The draw is weighted by each pitcher's real share of her team's starts, but she
    is only in it when her track has cleared -- and the arms that start most often
    are the ones least likely to be clear, so **their realised share comes out
    below their nominal one.** Measured: the busiest simulated starter took 6.0 of a
    team's 20 starts against a real 6.8, and the rotation ran a median 8.0 days
    against 7.0.

    That is a selection problem with a known target, so it is corrected the standard
    way rather than by inventing a manager: iterate
    `w <- w * (observed / realised)`, renormalised, damped to stop it oscillating on
    simulation noise. Nothing is fitted to the weekly loads or to anything else --
    the target is the start counts themselves, which are observed.

    It converges in about five passes, halving the mean per-pitcher share error
    (0.026 to 0.011) and landing the busiest starter on 6.89 against 6.80 and the
    rotation on 7.0 against 7.0. **It does NOT fix the weekly split** (7.23): those
    move by three pitches, which is the evidence that the split is diffuse.
    """
    key = (iters, n_seasons, seed, damp)
    if key in _START_W:
        return _START_W[key]
    base = staffs()
    target = {t: dict(zip(v[0], v[1])) for t, v in base.items()}
    w = {t: dict(target[t]) for t in target}
    for it in range(iters):
        out, _, _ = sim_season(n_seasons=n_seasons, seed=seed + it, start_weights=w)
        st = out[out["role"] == "start"]
        for t in w:
            counts = st[st["team"] == t]["P"].value_counts()
            tot = counts.sum()
            if not tot:
                continue
            for arm in list(w[t]):
                want = target[t].get(arm, 0.0)
                got = counts.get(arm, 0) / tot
                if want <= 0:
                    w[t][arm] = 0.0
                elif got > 0:
                    w[t][arm] *= (want / got) ** damp
            total = sum(w[t].values())
            if total > 0:
                w[t] = {k: v / total for k, v in w[t].items()}
    _START_W[key] = w
    return w


def _pick_starter(idx, w_start, track, rested, rng):
    """Tomorrow's starter is not chosen in advance; today's is chosen from who has
    cleared (user, 29 Sep).

    Most of this league did not keep a rotation, so imposing one would invent a
    pattern the data does not show. Instead nothing is scheduled: an arm becomes
    start-eligible when her track has recovered all the way to RESTED, and how long
    that takes is exactly how much she threw last time. A 66-pitch start clears in
    4.8 days; a 30-pitch relief outing clears in three. The rule is therefore
    REACTIVE with no parameter of its own -- "see what she threw, then decide" is
    what the track already encodes.

    Among the cleared arms she is drawn by her real share of starts, so who starts
    is still resampled from the season rather than invented.
    """
    ready = track[idx] <= rested
    if ready.any():
        w = np.where(ready, w_start, 0.0)
        if w.sum() == 0:                       # cleared, but none of them ever started
            w = ready.astype(float)
        return int(idx[int(rng.choice(len(idx), p=w / w.sum()))]), False
    return int(idx[int(np.argmin(track[idx]))]), True      # nobody clear: the freshest


def _pick_reliever(idx, w_role, w_start, track, caps, rested, recovery,
                   used, entry, late, rng):
    """Weighted by her real share of THIS relief role and by how much arm she has.

    SMOOTH, not a cut-off (user, 29 Sep): the weight is her role share times her
    remaining headroom, so a loaded arm becomes progressively unlikely rather than
    abruptly impossible. A manager is allowed to do something unwise; he is just
    not likely to.

    HEADROOM COUNTS THE WARM-UP (user, 29 Sep): `capacity - (track + ENTRY_COST)`,
    not `capacity - track`. A pitcher who finished yesterday near her capacity is
    not available today, because the 30 she spends warming up would put her back
    past it before she faced anybody -- which is the story the entry cost exists to
    tell, and the arithmetic did not tell it. It also does the work of an explicit
    rule for starters: a 66-pitch start leaves her at 46 the next day, so
    `cap - (46 + 30)` is negative and she drops out of the draw on her own. She
    pays 30 for the start and 30 again for any relief between starts, so a starter
    used in relief is expensive twice over.

    PROTECTION IS GRADED BY ROLE (spec 7.14). A late arm is on call in a way a
    middle one is not: real late relievers went back-to-back 5% of the time and
    inside two days 17%, against 2% and 6% for middle relief and 0% and 1% for
    starters. So the "about to start" hold is dropped in the late innings and kept
    earlier. Two rules hold in both: an arm RECOVERING FROM A START is unavailable
    until her track clears, and one ALREADY USED today cannot return, which is a
    rule of baseball rather than a preference.
    """
    head = np.maximum(caps[idx] - (track[idx] + entry), 0.0)
    spent = np.array([i in used for i in idx])
    hold = spent.copy()
    # The explicit "recovering from a start" hold was REMOVED on 29 Sep, because
    # charging the warm-up against headroom had already made it redundant and it
    # had become harmful. A 64-pitch start leaves her at 64; the next day
    # `cap - (44 + 30)` is barely positive and the day after that it is modest, so
    # headroom alone keeps her out for about two days and then lets her back
    # gradually -- which is what the season shows. Holding her until her track
    # fully cleared pushed her relief outings to a median of 11 days after a start
    # against a real 7, and 3% within three days against a real 15%. Dropping it
    # gives 9 days and 16%, at a cost of 1.0% of starts having a relief outing
    # within a day where the season has none.
    if not late:
        hold = hold | ((track[idx] <= rested + recovery) & (w_start > w_role))
    w = w_role * head * ~hold
    if w.sum() == 0:                           # everyone held: drop the preferences
        w = w_role * head * ~spent
    if w.sum() == 0:                           # nobody has anything left
        w = (~spent).astype(float) * np.maximum(head, 1e-9)
    if w.sum() == 0:
        return int(idx[int(np.argmax(head))]), True
    return int(idx[int(rng.choice(len(idx), p=w / w.sum()))]), False



def fixtures():
    """Every real game as (date, home team, away team), in date order.

    `schedules()` gave each team its own list of dates, which was enough while a
    staff was simulated on its own. It is not enough to decide whether the bottom
    of the seventh is played: that needs a home side and a score, so the two
    staffs have to meet in one game.

    Same `is_final` filter as `schedules`, for the same reason (Data notes: one
    fixture carries several game_ids).
    """
    games = tables.read("games", "all")
    games = games[games["is_final"]]
    rows = []
    for r in games.itertuples():
        home, away = str(r.home_team_name).strip(), str(r.away_team_name).strip()
        if not home or not away:
            continue
        rows.append((pd.to_datetime(r.game_date).normalize(), home, away))
    return sorted(rows, key=lambda x: x[0])


class _Side:
    """One staff's state inside one game."""

    def __init__(self, team, prep, track):
        (self.arms, self.w_start, self.w_mid, self.w_late,
         self.caps, self.ci) = prep
        self.team = team
        self.track = track
        self.idx = np.arange(len(self.arms))
        self.used = set()
        self.forced = False
        self.mid_entries = 0
        self.entries = 0
        self.pi = None
        self.role = None
        self.start_at = 0.0
        self.entered_inning = 1
        self.target = 0.0



def avg_half_inning():
    """Pitches in an average half-inning, in the game's currency. 18.3.

    This is what a manager is estimating when he decides whether his starter has
    another inning in her, so it is the unit the hook rule below is written in.
    """
    pa = plate_appearances()
    cost = float(sum(PITCH_COST.get(l, 3.3) for l in pa["line"]))
    return cost / pa.groupby(["game_id", "half", "inning"]).ngroups


# How much margin a manager leaves. The literal reading of "she cannot pitch
# another full inning" is MARGIN = 1.0, and it leaves her in too long: she is
# pulled at the FIRST boundary below the threshold, so her realised headroom
# averages half an inning less than the threshold itself. The real starts show a
# median headroom of 15.5 pitches at a boundary hook, which needs a threshold
# nearer one and a half innings. Swept against the real starter distribution,
# 1.4 lands it (median 65 against 65.5, p25 55 against 55).
#
# This is the one CALIBRATED constant in the hook rule, and it is calibrated the
# way 7.17 asks: the threshold is a decision the manager makes, tuned so that the
# OUTCOME matches, rather than an outcome used as a decision.
MARGIN = 1.4



def column_values(centred=True):
    """Run value per plate appearance of each pitcher's block, by column.

    Higher is worse for the pitcher. This is what an optimising manager compares
    when he asks whether the arm on the mound is still the cheapest way to get the
    next batter out (7.7).
    """
    from wpbl.dice import column_cells
    P = cards("P")
    w = line_weights()
    cols = column_cells(P.to_numpy(), centred)
    return P.index, {k: (v * w).sum(axis=1) / 100.0 for k, v in cols.items()}



def hmb_column(col, role, inning, entered_inning):
    """History Maker Baseball's rule, adapted: FRESH ends at the half-inning
    boundary (user, 29 Sep).

    HMB makes a reliever Fresh until the end of the half-inning she enters, so
    bringing her in with two outs spends most of a free fresh window on two
    batters. That is the boundary incentive the printed game lacks (7.19), and it
    comes from inside the fatigue system rather than from a surcharge, with the
    cost scaling by HOW FAR into the inning she arrives.

    HMB's clock is innings and ours is pitches, so the two cannot simply be
    stacked: a reliever eighteen pitches into her outing is Fresh on the track and
    past the boundary on HMB's clock. The adaptation is that **the boundary can
    only DEMOTE her, never promote her.** Once the half-inning she entered is over
    she is at best FADING, whatever her count says; and a reliever who came in
    already carrying stays exactly as tired as her track makes her. Carry is
    untouched, which is the whole point of 7.9.

    A starter is not affected: she enters at the top of the first, so the rule
    would never bind.
    """
    if role == "start" or inning <= entered_inning or col != "fresh":
        return col
    return "fading"



HORIZON = 7          # plate appearances: about one relief outing at 3.48 a batter


def _cost_run(cv, ci, track, cap, n, fresh_for, hmb, ppa):
    """Run cost of one pitcher over the next `n` plate appearances.

    `fresh_for` is how many of them fall inside the half-inning she entered; past
    that, HMB's rule demotes her out of fresh (7.27). With hmb off it does nothing.
    """
    total = 0.0
    for j in range(n):
        col = column_for(track + j * ppa, cap)
        if hmb and j >= fresh_for and col == "fresh":
            col = "fading"
        total += cv[col][ci]
    return total


def lookahead_pull(cv, sd, entry, outs, pa_left, hmb, ppa):
    """Change now, or finish the inning and change at the boundary?

    The optimiser of 7.7 and 7.25 compares only the NEXT batter, where an incoming
    reliever is fresh whatever the situation -- so it cannot see any cost that
    arrives later in her outing, which is why neither the entry cost nor HMB's rule
    moved it. This manager values a whole outing and compares the two options a
    real manager actually weighs:

      A  change NOW      -- the reliever pitches the rest of this inning and on,
                            and under HMB her fresh window is cut short by however
                            far into the inning she arrived
      B  change at the BOUNDARY -- the current pitcher finishes the inning, then
                            the reliever comes in clean and gets a full fresh one

    It is still parameter-free apart from the horizon, and still myopic about the
    SEASON -- it buys nothing for tomorrow, so it is not the manager check 3 wants.
    It exists to test whether a boundary incentive is visible to anyone at all.
    """
    free = [j for j in sd.idx
            if j not in sd.used and sd.caps[j] - (sd.track[j] + entry) > 0]
    if not free:
        return False, None
    best = min(free, key=lambda j: cv["fresh"][sd.ci[j]])
    n = HORIZON
    keep_for = min(pa_left, n)

    # A: she comes in now, mid-inning, and is only fresh for the rest of it
    a = _cost_run(cv, sd.ci[best], sd.track[best] + entry, sd.caps[best],
                  n, pa_left, hmb, ppa)
    # B: the current pitcher finishes the inning, then the reliever starts one clean
    b = _cost_run(cv, sd.ci[sd.pi], sd.track[sd.pi], sd.caps[sd.pi],
                  keep_for, 0 if hmb else n, hmb, ppa)
    b += _cost_run(cv, sd.ci[best], sd.track[best] + entry, sd.caps[best],
                   n - keep_for, n, hmb, ppa)
    return a < b, best


def comes_out(track, cap, bases, outs, half_pitches):
    """Should the pitcher be replaced? (user's two mechanisms, 29 Sep.)

    Measured over the 78 real starts, a starter comes out three ways:

      at an INNING BOUNDARY            52 (67%), median 62.5 pitches
      MID-INNING with runners on       21 (27%), median 72.0
      mid-inning with the bases empty   4 (5%)

    and the headroom she has left before her capacity says what the manager was
    thinking. At a boundary it is a median 15.5 pitches, near enough one
    half-inning (18.3) that the decision reads as "it does not look like she can
    go again"; in a jam it is 10.0, and she has been left in and got into trouble.
    So:

      BOUNDARY: pull when another inning would take her past her capacity, with
      the margin above. The reliever starts the inning clean rather than waiting
      for the starter to reach her limit.

      JAM: pull mid-inning when runners are on and she is within half an inning of
      her capacity -- in trouble, and close enough to gassed that it is unlikely
      to pass.

    **Neither rule draws a target.** Her stint is an OUTCOME of her capacity and
    how the game has gone, which is what 7.17 said was needed: the length was
    being measured as an outcome and then used as a decision.
    """
    headroom = cap - track
    if outs == 0 and bases == (False, False, False):
        return headroom < MARGIN * half_pitches       # start of a half-inning
    if any(bases):
        return headroom < half_pitches / 2            # a jam, and little left
    return False


def sim_season(n_seasons=200, seed=20260928, centred=True, recovery=RECOVERY,
               entry=ENTRY_COST, fixture_list=None, seventh_rule=True,
               manager="descriptive", hmb=False, start_weights=None,
               correct_starts=True):
    """Play every real GAME, both staffs at once, carrying each track across days.

    Restructured 29 Sep (user). It used to play each team's schedule on its own,
    seven half-innings every time, because a lone staff has no opponent and no
    score. That charged the dice for a half-inning nobody played -- worth about
    +0.17 runs (7.15) -- and, more to the point here, it gave the AWAY staff a
    seventh inning it often never pitches.

    Who pitches when: the HOME staff works the top of every inning, the AWAY staff
    the bottom. **The bottom of the seventh is not played when the home team is
    already ahead**, so it is the AWAY staff that loses the half-inning, and its
    late reliever with it. `seventh_rule=False` restores the old behaviour for
    comparison.

    `fixture_list` overrides the calendar with [(date, home, away), ...], which is
    how the final's cadence is tested.
    """
    rng = np.random.default_rng(seed)
    ids, cols = pitcher_columns(centred=centred)
    pos = set(ids)
    B = cards("B")
    w = line_weights()
    b_line = dict(zip(B.index, played_lines(to_cells(B.to_numpy(), B_CELLS, w, False), "B")))
    col_index = {pid: i for i, pid in enumerate(ids)}
    st_targets = role_stints()
    half_pitches = avg_half_inning()
    _, colval = column_values(centred=centred)
    ppa = avg_half_inning() / (len(plate_appearances()) /
                               plate_appearances().groupby(
                                   ['game_id','half','inning']).ngroups)
    pa_per_out = (len(plate_appearances()) /
                  plate_appearances().groupby(['game_id','half','inning']).ngroups) / 3
    cv = {k: v for k, v in colval.items()}
    caps_all = capacity()
    lus = lineups()
    fx = fixtures() if fixture_list is None else fixture_list
    staff = staffs()
    # The draw's weights are corrected for the eligibility filter unless they were
    # handed in (which is what the calibration itself does, to avoid recursion).
    if start_weights is None and correct_starts:
        start_weights = calibrated_start_weights()
    if start_weights is not None:
        staff = {t: (v[0], np.array([start_weights[t].get(a, 0.0) for a in v[0]]),
                     v[2], v[3])
                 for t, v in staff.items() if t in start_weights}
    rested = -entry

    prepared = {}
    for team, (arms, w_start, w_mid, w_late) in staff.items():
        keep = [i for i, a in enumerate(arms) if a in pos]
        if len(keep) < 3:
            continue
        a = [arms[i] for i in keep]
        ws, wm, wl = w_start[keep], w_mid[keep], w_late[keep]
        if ws.sum() == 0 or wm.sum() == 0 or wl.sum() == 0:
            continue
        prepared[team] = (a, ws / ws.sum(), wm / wm.sum(), wl / wl.sum(),
                          np.array([caps_all.get(x, CAPACITY_DEFAULT) for x in a], float),
                          np.array([col_index[x] for x in a]))
    fx = [f for f in fx if f[1] in prepared and f[2] in prepared]

    outings, games_out = [], []
    seen = {"fresh": 0, "fading": 0, "gassed": 0}

    def open_side(team, track, day):
        sd = _Side(team, prepared[team], track)
        pi, forced = _pick_starter(sd.idx, sd.w_start, sd.track, rested, rng)
        sd.forced |= forced
        sd.track[pi] += entry
        sd.pi, sd.role, sd.start_at = pi, "start", sd.track[pi]
        sd.entered_inning = 1
        sd.target = float("inf")     # she comes out by rule, not by target
        sd.used.add(pi)
        return sd

    def half(sd, lu, spot, inning, day, season):
        """One half-inning pitched by `sd`. Returns (runs, next spot)."""
        bases, outs, total = (False, False, False), 0, 0
        while outs < 3:
            if manager == "lookahead":
                due, pick = lookahead_pull(cv, sd, entry, outs,
                                           max(1, int(round((3 - outs) * pa_per_out))),
                                           hmb, ppa)
                sd._pick = pick
            elif manager == "optimiser":
                # 7.7's rule, with no free parameter: every batter is worth the
                # same in runs, so give him to the cheapest arm still able to take
                # him. Keep her while her CURRENT column beats the best available
                # arm's FRESH column.
                col_now = column_for(sd.track[sd.pi], sd.caps[sd.pi])
                cur = cv[col_now][sd.ci[sd.pi]]
                free = [j for j in sd.idx
                        if j not in sd.used and sd.caps[j] - (sd.track[j] + entry) > 0]
                due = bool(free) and cur > min(cv["fresh"][sd.ci[j]] for j in free)
            elif sd.role in ("start", "late"):
                # Neither is on a drawn number. A starter comes out by the rule
                # above. A LATE reliever is there to finish: 81% of real ones do,
                # so she pitches to the end of the game unless the same rule takes
                # her out first. Drawing her a target instead cut her to 17
                # pitches against a real 22, because the pool she was drawn from
                # had already been truncated by the end of the game (7.13).
                due = comes_out(sd.track[sd.pi], sd.caps[sd.pi],
                                bases, outs, half_pitches)
            else:
                due = sd.track[sd.pi] - sd.start_at >= sd.target
                if due and outs > 0 and rng.random() >= MID_INNING[
                        "late" if inning >= LATE_FROM else "middle"]:
                    due = False
            if due:
                outings.append((season, sd.team, sd.arms[sd.pi], day, sd.role,
                                sd.track[sd.pi] - sd.start_at, sd.start_at))
                late = inning >= LATE_FROM
                if manager == "lookahead" and getattr(sd, "_pick", None) is not None:
                    pi, forced = sd._pick, False
                elif manager == "optimiser":
                    free = [j for j in sd.idx
                            if j not in sd.used and sd.caps[j] - (sd.track[j] + entry) > 0]
                    if free:
                        pi = min(free, key=lambda j: cv["fresh"][sd.ci[j]])
                        forced = False
                    else:
                        pi = int(sd.idx[int(np.argmax(sd.caps[sd.idx] - sd.track[sd.idx]))])
                        forced = True
                else:
                    pi, forced = _pick_reliever(
                        sd.idx, sd.w_late if late else sd.w_mid, sd.w_start, sd.track,
                        sd.caps, rested, recovery, sd.used, entry,
                        late, rng)
                sd.forced |= forced
                sd.track[pi] += entry
                sd.pi = pi
                sd.role = "late" if late else "middle"
                sd.start_at = sd.track[pi]
                sd.entered_inning = inning
                sd.entries += 1
                sd.mid_entries += int(outs > 0)
                sd.target = (float("inf") if sd.role == "late"
                             else float(rng.choice(st_targets[sd.role])))
                sd.used.add(pi)
            col = column_for(sd.track[sd.pi], sd.caps[sd.pi])
            if hmb:
                col = hmb_column(col, sd.role, inning, sd.entered_inning)
            seen[col] += 1
            ids_b, pr = lu[spot % 9]
            spot += 1
            tb = Table.from_lines(cols[col][sd.ci[sd.pi]],
                                  b_line[ids_b[int(rng.choice(len(ids_b), p=pr))]])
            bases, made, early, r, line = plate_appearance(tb, bases, outs, rng)
            sd.track[sd.pi] += PITCH_COST.get(line, 3.3)
            total += early
            outs += made
            if outs >= 3:
                break
            total += r
            bases, made = steal(bases, rng)
            outs += made
        return total, spot

    def close_side(sd, day, season, halves):
        outings.append((season, sd.team, sd.arms[sd.pi], day, sd.role,
                        sd.track[sd.pi] - sd.start_at, sd.start_at))
        games_out.append((season, sd.team, day, sd.runs, len(sd.used),
                          sd.forced, halves, sd.entries, sd.mid_entries))

    for season in range(n_seasons):
        track = {t: np.full(len(prepared[t][0]), float(rested)) for t in prepared}
        prev = {t: None for t in prepared}
        for day, home, away in fx:
            for t in (home, away):
                if prev[t] is not None:
                    track[t] = np.maximum(rested, track[t] - recovery * (day - prev[t]).days)
                prev[t] = day
            H = open_side(home, track[home], day)
            A = open_side(away, track[away], day)
            H.runs = A.runs = 0                       # runs ALLOWED by that staff
            lu_a, spot_a = lus[rng.integers(len(lus))], 0   # away bats the top
            lu_h, spot_h = lus[rng.integers(len(lus))], 0   # home bats the bottom
            score_away = score_home = 0
            h_halves = a_halves = 0
            for inning in range(1, INNINGS + 1):
                r, spot_a = half(H, lu_a, spot_a, inning, day, season)   # home pitches
                score_away += r
                h_halves += 1
                if (seventh_rule and inning == INNINGS and score_home > score_away):
                    break            # the home team is ahead; the bottom is not played
                r, spot_h = half(A, lu_h, spot_h, inning, day, season)   # away pitches
                score_home += r
                a_halves += 1
            H.runs, A.runs = score_away, score_home
            close_side(H, day, season, h_halves)
            close_side(A, day, season, a_halves)
    out = pd.DataFrame(outings, columns=["season", "team", "P", "date", "role",
                                         "pitches", "entered_at"])
    gm = pd.DataFrame(games_out, columns=["season", "team", "date", "runs",
                                          "pitchers", "forced", "halves",
                                          "entries", "mid_entries"])
    n = sum(seen.values())
    return out, gm, {k: v / n for k, v in seen.items()}


def loads(out: pd.DataFrame) -> pd.DataFrame:
    """The 7-day load carried at each simulated outing.

    Measured exactly as `workload.appearances` measures the real one -- inclusive
    of today, the seven days ending today. The same definition on both sides or
    the comparison is not one.
    """
    rows = []
    for _, grp in out.groupby(["season", "team", "P"], sort=False):
        grp = grp.sort_values("date")
        d = grp["date"].to_numpy()
        p = grp["pitches"].to_numpy()
        starts = (grp["role"] == "start").to_numpy()
        for i in range(len(grp)):
            m = (d > d[i] - np.timedelta64(WINDOW, "D")) & (d <= d[i])
            rows.append((float(p[m].sum()), bool(starts[m].any())))
    return pd.DataFrame(rows, columns=["load", "week_with_start"])


def season_runs(per_seven=False):
    """Real runs per team-game, computed.

    It used to be the literal "7.77". Section 9.1 records the identical bug in
    `engine.py`, where a hardcoded season row left the dice compared against the
    wrong number once two games were added. Computed from the plays it is 7.64.

    `per_seven` scales it to seven half-innings instead. That was needed while the
    simulation played seven every time; now that it plays the real game, with the
    bottom of the seventh dropped when the home team leads, a team-game on each
    side means the same thing and the raw figure is the right comparison. Kept
    because the scaled version is what the one-sided simulator has to be judged
    against, and `seventh_rule=False` still produces one.
    """
    plays = tables.read("plays", "training")
    games = plays["game_id"].nunique()
    per_game = float(plays["runs_scored"].sum()) / (2 * games)
    if not per_seven:
        return per_game
    halves = plays.groupby(["game_id", "half"])["inning"].nunique()
    batted = float(halves.groupby(level=0).sum().mean()) / 2
    return per_game / batted * INNINGS


def season_halves_batted():
    """Real half-innings a team bats, which is also what its opponent pitches.

    6.85, not 7: the home team does not bat the bottom of the seventh when it is
    already ahead, so the AWAY staff is the one that loses a half-inning -- and its
    late reliever with it.
    """
    plays = tables.read("plays", "training")
    halves = plays.groupby(["game_id", "half"])["inning"].nunique()
    return float(halves.groupby(level=0).sum().mean()) / 2


def _q(s, q):
    return float(np.quantile(s, q)) if len(s) else float("nan")


def real_usage():
    """The real outings and their 7-day loads, charged in the GAME's currency.

    `workload.appearances` measures the feed's pitches, which is the right answer
    to "how hard was that arm worked". It is the WRONG baseline for this module,
    because the simulated track spends PITCH_COST -- since 29 Sep the rulebook's
    5/5/3, which is 5.3% cheaper than the feed's count. Comparing a rulebook-unit
    stint against a feed-unit one makes the dice look about 5% lighter than they
    are, and that is a units error, not a result.

    So the same real outings are re-charged at whatever the game charges, and both
    sides of every comparison are then in one unit. The feed's own figures stay
    available through `workload.appearances` for the questions they answer.
    """
    pa = plate_appearances()
    pa = pa.assign(pitches=[PITCH_COST.get(l, 3.3) for l in pa["line"]])
    first = pa.groupby(["game_id", "P_team"])["P"].first()
    rows = []
    for (gid, team, pid), grp in pa.groupby(["game_id", "P_team", "P"], sort=False):
        grp = grp.sort_values("sequence")
        if first.get((gid, team)) == pid:
            role = "start"
        else:
            role = "late" if int(grp["inning"].iloc[0]) >= LATE_FROM else "middle"
        rows.append((pid, pd.to_datetime(grp["date"].iloc[0]),
                     float(grp["pitches"].sum()), role))
    out = pd.DataFrame(rows, columns=["P", "date", "pitches", "role"])
    out["is_starter"] = out["role"] == "start"
    loads, with_start = [], []
    for pid, grp in out.groupby("P"):
        d = grp["date"].to_numpy()
        pi = grp["pitches"].to_numpy()
        st = grp["is_starter"].to_numpy()
        for i in range(len(grp)):
            m = (d > d[i] - np.timedelta64(WINDOW, "D")) & (d <= d[i])
            loads.append(float(pi[m].sum()))
            with_start.append(bool(st[m].any()))
    return out, pd.DataFrame({"load": loads, "week_with_start": with_start})


def report(out, gm, shares, real, real_loads) -> None:
    ld = loads(out)
    print(f"=== season fatigue, spec 9 check 3 "
          f"(E={ENTRY_COST}, R={RECOVERY}, rested={RESTED}) ===")
    print(f"  {len(gm):,} simulated team-games: {gm['season'].nunique()} seasons "
          f"x {gm['team'].nunique()} teams\n")

    print(f"  {'stint length, pitches':38s}{'dice':>8s}{'season':>10s}"
          "   (both in the game's currency)")
    for role, m_s, m_r in (("starter", out["role"] == "start", real["role"] == "start"),
                           ("middle relief", out["role"] == "middle", real["role"] == "middle"),
                           ("late relief", out["role"] == "late", real["role"] == "late")):
        s, r = out.loc[m_s, "pitches"], real.loc[m_r, "pitches"]
        print(f"    {role:34s}{_q(s, .5):8.0f}{_q(r, .5):10.0f}")
        print(f"    {'  p25 / p75':34s}"
              f"{f'{_q(s, .25):.0f} / {_q(s, .75):.0f}':>8s}"
              f"{f'{_q(r, .25):.0f} / {_q(r, .75):.0f}':>10s}")

    print(f"\n  {'7-day load, pitches':38s}{'dice':>8s}{'season':>10s}")
    for label, m_s, m_r in (("relief-only week", ~ld["week_with_start"],
                             ~real_loads["week_with_start"]),
                            ("week with a start", ld["week_with_start"],
                             real_loads["week_with_start"])):
        s, r = ld.loc[m_s, "load"], real_loads.loc[m_r, "load"]
        print(f"    {label:34s}{_q(s, .5):8.0f}{_q(r, .5):10.0f}")
        print(f"    {'  p90':34s}{_q(s, .9):8.0f}{_q(r, .9):10.0f}")

    # Team-games from the SAME source the outings came from. `real_usage` reads
    # training plays (39 games, 78 team-games); the guard's 80 counts all plays,
    # which includes the excluded semifinal G3. Mixing the two understated this by
    # 3%, which is the denominator version of the hardcoded-season-row bug.
    real_pg = len(real) / (2 * tables.read("plays", "training")["game_id"].nunique())
    print(f"\n  {'the staff as a whole':38s}{'dice':>8s}{'season':>10s}")
    print(f"    {'runs allowed per team-game':34s}{gm['runs'].mean():8.2f}"
          f"{season_runs():10.2f}")
    print(f"    {'half-innings pitched':34s}{gm['halves'].mean():8.2f}"
          f"{season_halves_batted():10.2f}")
    print(f"    {'pitchers per team-game':34s}{gm['pitchers'].mean():8.2f}"
          f"{real_pg:10.2f}")
    print(f"    {'games with nobody available':34s}"
          f"{100 * gm['forced'].mean():7.1f}%{'--':>10s}")
    print("\n  column shares of simulated plate appearances")
    print("    " + "   ".join(f"{k} {100 * v:.1f}%" for k, v in shares.items()))


# The championship series (bullpen_spec calendar): five games in seven days. The
# real season never asks this of a staff -- its median gap between a team's games
# is two days and nobody plays five in a week -- so this is the cadence the spec
# says pushes arms past anything the data shows, and the only place the settings
# are genuinely stressed.
FINAL = [pd.Timestamp(f"2026-09-{d}") for d in (16, 17, 19, 20, 22)]


def series_stress(n_seasons=1500, seed=20260928):
    """The same settings on the final's cadence, reported game by game.

    Nothing about the pitchers changes; only the calendar does. Every team plays
    the five dates with a track that carries between them, which is the one thing
    a single-game check cannot see.
    """
    teams = sorted(staffs())
    if len(teams) < 2:
        raise RuntimeError("need two staffs for a series")
    home, away = teams[0], teams[1]
    # One pairing plays the five dates: a championship series is two teams, and
    # alternating the home side is what decides who loses the bottom of the
    # seventh, which is now part of what is being stressed.
    fx = [(d, home if i % 2 == 0 else away, away if i % 2 == 0 else home)
          for i, d in enumerate(FINAL)]
    return sim_season(n_seasons=n_seasons, seed=seed, fixture_list=fx)


def report_stress(out, gm) -> None:
    print("\n=== the same settings on the final's cadence "
          "(5 games in 7 days, 16-22 Sep) ===")
    print(f"  {len(gm):,} simulated team-games\n")
    print(f"    {'':14s}{'nobody available':>18s}{'runs':>8s}{'arms':>7s}"
          f"{'gassed outings':>17s}")
    by_day = gm.groupby("date")
    gassed = _gassed_share_by_day(out, gm)
    for i, (day, grp) in enumerate(by_day, 1):
        print(f"    G{i} {day.strftime('%d %b'):10s}"
              f"{100 * grp['forced'].mean():17.1f}%"
              f"{grp['runs'].mean():8.2f}{grp['pitchers'].mean():7.2f}"
              f"{100 * gassed.get(day, float('nan')):16.1f}%")
    first = by_day["runs"].mean().iloc[0]
    last = by_day["runs"].mean().iloc[-1]
    print(f"\n  G1 to G5, runs per team-game: {first:.2f} -> {last:.2f} "
          f"({last - first:+.2f})")


def _gassed_share_by_day(out, gm):
    """Share of each day's outings that were pitched from past capacity.

    Read off the outings rather than the PA counter, which is pooled over the
    whole run: an outing counts as gassed if she entered past her own capacity or
    passed it during the stint.
    """
    caps = capacity()
    cap = out["P"].map(lambda p: caps.get(p, CAPACITY_DEFAULT))
    out = out.assign(gassed=(out["entered_at"] + out["pitches"]) > cap)
    return out.groupby("date")["gassed"].mean()


def main() -> None:
    out, gm, shares = sim_season()
    real, real_loads = real_usage()
    report(out, gm, shares, real, real_loads)
    s_out, s_gm, _ = series_stress()
    report_stress(s_out, s_gm)


if __name__ == "__main__":
    main()
