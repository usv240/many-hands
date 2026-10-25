"""Simulate a full match and compute counterfactual ground truth for its decisive shots.

Ground truth, in plain words: for every dangerous shot, we go back to each mistake the
conceding team made in the build-up (a lost ball, or a defender out of position) and replay the
attack many times with and without that one mistake. The drop in danger when the mistake is
removed is that player's true contribution. The same random numbers are used for both versions
of each replay, so the comparison is fair and low-noise.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
import socceraction.spadl.config as spadlcfg

from simulator.engine import HALF_SECONDS, Engine, Params, State, Team

TYPE_IDS = {name: i for i, name in enumerate(spadlcfg.actiontypes)}
RESULT_IDS = {name: i for i, name in enumerate(spadlcfg.results)}
BODY_FOOT, BODY_HEAD = spadlcfg.bodyparts.index("foot"), spadlcfg.bodyparts.index("head")
ONBALL_LOSS = {"pass", "cross", "clearance", "dribble", "take_on"}

DECISIVE_XG = 0.07   # shots at least this good, plus every goal, get ground truth
WINDOW = 10          # steps before the shot that can contain causes
HORIZON_EXTRA = 4    # replays run until the original shot step, plus this many steps
ROLLOUTS = 100       # replays per arm
EFFECT_FLOOR = 0.004 # smaller effects are treated as noise


@dataclass
class Step:
    state: State
    spec: object
    pos: np.ndarray
    first_action: int
    events: list[dict]
    shot: tuple[int, float] | None
    goal: bool


@dataclass
class MatchResult:
    game: dict
    actions: pd.DataFrame
    positions: pd.DataFrame
    moments: list[dict] = field(default_factory=list)


def simulate(home: Team, away: Team, game_id: int, seed: int, params: Params | None = None,
             ground_truth: bool = True) -> MatchResult:
    eng = Engine(home, away, params)
    rng = np.random.default_rng(seed)
    steps: list[Step] = []
    rows: list[dict] = []
    action_id = 0
    st = eng._restart(State(1, 0, 0, 0, 0.0, 1, False), 0, rng, "kickoff", 0)
    st = replace(st, clock=0.0)
    end_of_half = {1: HALF_SECONDS + rng.uniform(60, 240), 2: HALF_SECONDS + rng.uniform(120, 420)}

    while True:
        if st.clock > end_of_half[st.period]:
            if st.period == 2:
                break
            st = eng._restart(replace(st, period=2, clock=0.0), 1, rng, "kickoff", 0)
            st = replace(st, clock=0.0)
        pos, spec, evs, nxt, shot, goal = eng.step(st, rng)
        steps.append(Step(st, spec, pos, action_id, evs, shot, goal))
        step_action_id = action_id
        prev_kind = rows[-1]["type_name"] if rows else None
        for e in evs:
            team = eng.teams[e["team"]]
            body = BODY_HEAD if (e["kind"] == "shot" and prev_kind == "cross" and rng.random() < 0.6) else BODY_FOOT
            rows.append(dict(
                game_id=game_id, original_event_id=f"{game_id}-{action_id}", action_id=action_id,
                step_action_id=step_action_id,
                period_id=st.period, time_seconds=round(e["clock"], 2), team_id=team.tid,
                player_id=team.players[e["player"]].pid,
                start_x=e["start_x"], start_y=e["start_y"], end_x=e["end_x"], end_y=e["end_y"],
                type_id=TYPE_IDS[e["kind"]], type_name=e["kind"],
                result_id=RESULT_IDS[e["result"]], result_name=e["result"], bodypart_id=body,
            ))
            prev_kind = e["kind"]
            action_id += 1
        st = nxt

    actions = pd.DataFrame(rows)
    pos_rows = []
    for s in steps:
        for t in (0, 1):
            team = eng.teams[t]
            for i in range(11):
                pos_rows.append((game_id, s.first_action, team.tid, team.players[i].pid,
                                 round(float(s.pos[t, i, 0]), 2), round(float(s.pos[t, i, 1]), 2)))
    positions = pd.DataFrame(pos_rows, columns=["game_id", "step_action_id", "team_id", "player_id", "x", "y"])
    goals = actions[(actions.type_name == "shot") & (actions.result_name == "success")]
    game = dict(game_id=game_id, home_team_id=home.tid, away_team_id=away.tid,
                home_score=int((goals.team_id == home.tid).sum()),
                away_score=int((goals.team_id == away.tid).sum()), seed=seed)
    result = MatchResult(game, actions, positions)
    if ground_truth:
        result.moments = decisive_moments(eng, steps, game_id, seed)
    return result


def _arm_mean(eng: Engine, start: State, conceding: int, seed: int, horizon: int,
              first=None) -> float:
    """Average danger over replays. `first` optionally forces the first action's outcome."""
    total = 0.0
    for k in range(ROLLOUTS):
        rng = np.random.default_rng((seed, k))
        st = start
        danger = 0.0
        steps_left = horizon
        if first is not None:
            spec, force = first
            _, _, _, st, shot, goal = eng.step(st, rng, force=force, spec=spec)
            steps_left -= 1
            if shot is not None and shot[0] != conceding:
                danger += shot[1]
            if goal:
                total += danger
                continue
        total += danger + eng.rollout(st, conceding, rng, steps_left)
    return total / ROLLOUTS


def decisive_moments(eng: Engine, steps: list[Step], game_id: int, seed: int) -> list[dict]:
    moments = []
    for s_idx, step in enumerate(steps):
        if step.shot is None or not (step.goal or step.shot[1] >= DECISIVE_XG):
            continue
        attacking = step.shot[0]
        conceding = 1 - attacking
        team = eng.teams[conceding]
        window = range(max(0, s_idx - WINDOW), s_idx)
        causes = []

        # On-ball: the conceding team lost the ball in the build-up.
        for i in window:
            w = steps[i]
            first = w.events[0]
            if (w.state.poss == conceding and first["kind"] in ONBALL_LOSS
                    and first["result"] == "fail"):
                cseed = seed * 1_000_003 + i
                hz = s_idx - i + HORIZON_EXTRA
                with_ = _arm_mean(eng, w.state, conceding, cseed, hz, (w.spec, "fail"))
                without = _arm_mean(eng, w.state, conceding, cseed, hz, (w.spec, "success"))
                causes.append(dict(kind="onball", player_id=team.players[first["player"]].pid,
                                   action_id=w.first_action, with_danger=with_,
                                   without_danger=without))

        # Off-ball: a defender out of position while the attack developed.
        seen = set()
        for i in window:
            w = steps[i]
            if w.state.poss != attacking:
                continue
            for lapse in w.state.lapses:
                if lapse[0] in seen:
                    continue
                seen.add(lapse[0])
                cseed = seed * 1_000_003 + 500_000 + i * 11 + lapse[0]
                hz = s_idx - i + HORIZON_EXTRA
                with_ = _arm_mean(eng, w.state, conceding, cseed, hz)
                fixed = replace(w.state, lapses=tuple(x for x in w.state.lapses if x != lapse))
                without = _arm_mean(eng, fixed, conceding, cseed, hz)
                causes.append(dict(kind="offball", player_id=team.players[lapse[0]].pid,
                                   action_id=w.first_action, with_danger=with_,
                                   without_danger=without,
                                   lapse_dx=lapse[1], lapse_dy=lapse[2]))

        contrib: dict[str, float] = {}
        for c in causes:
            effect = c["with_danger"] - c["without_danger"]
            c["effect"] = effect if effect >= EFFECT_FLOOR else 0.0
            contrib[c["player_id"]] = contrib.get(c["player_id"], 0.0) + c["effect"]
        total = sum(contrib.values())
        shot_event = step.events[0]
        moments.append(dict(
            game_id=game_id,
            shot_action_id=step.first_action,
            window_start_action_id=steps[window.start].first_action if len(window) else step.first_action,
            attacking_team_id=eng.teams[attacking].tid,
            conceding_team_id=team.tid,
            shooter_id=eng.teams[attacking].players[shot_event["player"]].pid,
            xg=step.shot[1],
            goal=step.goal,
            causes=causes,
            truth={k: v / total for k, v in contrib.items() if v > 0} if total > 1e-4 else {},
        ))
    return moments
