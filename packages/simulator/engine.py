"""A calibrated football match simulator with planted errors and counterfactual ground truth.

Why it exists: real match data never tells you the true cause of a goal. In this simulator we
know it, because we can replay any moment with one mistake removed and measure how much less
dangerous the attack becomes. That measured difference is the ground truth that our
responsibility model (which never sees it) is scored against.

Coordinates follow SPADL: a 105 by 68 metre pitch, the home team attacks towards x = 105 and the
away team towards x = 0. "Own frame" means coordinates as seen by a team attacking towards +x.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

import numpy as np

L, W = 105.0, 68.0
ROLES = ("GK", "RB", "RCB", "LCB", "LB", "DM", "RCM", "LCM", "RW", "ST", "LW")
# 4-3-3 shape in the own frame for a ball at the centre spot.
SLOTS = np.array(
    [[6, 34], [33, 8], [28, 25], [28, 43], [33, 60], [42, 34],
     [52, 20], [52, 48], [70, 10], [76, 34], [70, 58]],
    dtype=float,
)
LAPSE_PLAYERS = (1, 2, 3, 4, 5)  # full backs, centre backs and the holding midfielder
HALF_SECONDS = 2700.0


@dataclass(frozen=True)
class Player:
    pid: str
    name: str
    shirt: int
    role: str
    passing: float
    composure: float
    discipline: float
    finishing: float
    pace: float


@dataclass(frozen=True)
class Team:
    tid: str
    name: str
    short: str
    players: tuple[Player, ...]
    tempo: float  # above 1 means a more direct, forward-passing style


@dataclass(frozen=True)
class State:
    poss: int  # 0 home, 1 away
    bx: float
    by: float
    carrier: int
    clock: float
    period: int
    can_carry: bool
    # Active positional lapses of the defending team: (player index, dx, dy) in its own frame.
    lapses: tuple[tuple[int, float, float], ...] = ()


@dataclass(frozen=True)
class Spec:
    """An action the carrier has decided to attempt. Execution decides the outcome."""

    kind: str  # pass, cross, dribble (a carry), take_on, shot, clearance
    actor: int
    tx: float
    ty: float
    receiver: int
    p_success: float
    xg: float = 0.0


@dataclass(frozen=True)
class Params:
    """Tuned so match aggregates sit near real football (see calibrate.py)."""

    pass_base: float = 1.9
    pass_dist: float = 0.045
    pass_open: float = 0.17
    pass_press: float = 0.8
    carry_prob: float = 0.86
    lapse_rate: float = 0.075
    xg_scale: float = 0.44
    shot_zone: float = 1.0


def own(team: int, x: float, y: float) -> tuple[float, float]:
    return (x, y) if team == 0 else (L - x, W - y)


def sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def xg_model(ox: float, oy: float, pressure: float, finishing: float, scale: float) -> float:
    """Chance an average finish scores from this spot, in the shooter's own frame."""
    dx = max(L - ox, 0.5)
    dy = oy - W / 2
    dist = math.hypot(dx, dy)
    angle = math.atan2(7.32 * dx, dx * dx + dy * dy - (7.32 / 2) ** 2)
    if angle < 0:
        angle += math.pi
    z = -1.45 + 1.9 * angle - 0.085 * dist + (0.35 if pressure > 4 else -0.35 if pressure < 1.5 else 0)
    return float(min(0.95, sigmoid(z) * (0.75 + 0.5 * finishing) * scale))


class Engine:
    def __init__(self, home: Team, away: Team, params: Params | None = None) -> None:
        self.teams = (home, away)
        self.p = params or Params()

    # ------------------------------------------------------------------ positions
    def team_positions(self, team: int, st: State) -> np.ndarray:
        bx, by = own(team, st.bx, st.by)
        in_poss = team == st.poss
        pos = SLOTS.copy()
        pos[1:, 0] += (bx - 52.5) * 0.6 + (5.0 if in_poss else -5.0)
        width = 1.0 if in_poss else 0.75
        pos[1:, 1] = W / 2 + (pos[1:, 1] - W / 2) * width + (by - W / 2) * (0.2 if in_poss else 0.35)
        pos[0] = [min(max(3 + bx * 0.12, 2), 18), W / 2 + (by - W / 2) * 0.15]
        if not in_poss:
            for i, dx, dy in st.lapses:
                pos[i, 0] += dx
                pos[i, 1] += dy
        pos[:, 0] = np.clip(pos[:, 0], 1, L - 1)
        pos[:, 1] = np.clip(pos[:, 1], 1, W - 1)
        if team == 1:
            pos = np.array([L, W]) - pos
        return pos

    def positions(self, st: State, rng: np.random.Generator) -> np.ndarray:
        """Positions of all 22 players, shape (2, 11, 2), in absolute coordinates."""
        pos = np.stack([self.team_positions(0, st), self.team_positions(1, st)])
        pos += rng.normal(0, 1.2, pos.shape)
        ball = np.array([st.bx, st.by])
        pos[st.poss, st.carrier] = ball
        # The nearest defender presses the ball.
        d = 1 - st.poss
        dist = np.linalg.norm(pos[d, 1:] - ball, axis=1)
        j = int(np.argmin(dist)) + 1
        if dist[j - 1] < 18:
            pos[d, j] = pos[d, j] + 0.72 * (ball - pos[d, j])
        pos[..., 0] = np.clip(pos[..., 0], 0.5, L - 0.5)
        pos[..., 1] = np.clip(pos[..., 1], 0.5, W - 0.5)
        return pos

    # ------------------------------------------------------------------ decisions
    def choose(self, st: State, pos: np.ndarray, rng: np.random.Generator) -> Spec:
        t, c = st.poss, st.carrier
        pl = self.teams[t].players[c]
        ox, oy = own(t, st.bx, st.by)
        ball = np.array([st.bx, st.by])
        press = float(np.min(np.linalg.norm(pos[1 - t] - ball, axis=1)))
        dist_goal = math.hypot(L - ox, oy - W / 2)

        if c != 0:
            p_shot = 0.0
            if ox > 72:
                p_shot = 0.13 if dist_goal < 13 else 0.06 if dist_goal < 20 else 0.015 if dist_goal < 28 else 0.0
            if rng.random() < p_shot * self.p.shot_zone:
                xg = xg_model(ox, oy, press, pl.finishing, self.p.xg_scale)
                return Spec("shot", c, *own(t, L, W / 2), -1, 0.0, xg)
            if ox > 82 and abs(oy - W / 2) > 17 and rng.random() < 0.1:
                return self._cross(st, pos, rng)
            if press < 2.8 and ox > 40 and rng.random() < 0.025:
                p = 0.42 + 0.5 * (pl.pace - 0.7)
                tx, ty = own(t, min(ox + 5, L - 2), oy + rng.normal(0, 2))
                return Spec("take_on", c, tx, ty, c, p)
            if ox < 26 and press < 6 and rng.random() < 0.125:
                return self._clearance(st, pos, rng)
            if st.can_carry and rng.random() < self.p.carry_prob:
                step = rng.uniform(2, 11) * (1.0 if ox < 92 else 0.3)
                tx, ty = own(t, min(ox + step, L - 1.5), min(max(oy + rng.normal(0, 3.5), 2), W - 2))
                return Spec("dribble", c, tx, ty, c, 0.93 if press < 2.5 else 0.985)
        return self._pass(st, pos, rng, pl, press)

    def _pass(self, st: State, pos: np.ndarray, rng, pl: Player, press: float) -> Spec:
        t, c = st.poss, st.carrier
        ox, _ = own(t, st.bx, st.by)
        ball = np.array([st.bx, st.by])
        mates = pos[t]
        opp = pos[1 - t]
        weights, cand = [], []
        for j in range(11):
            if j == c or (j == 0 and ox > 35):
                continue
            d = float(np.linalg.norm(mates[j] - ball))
            if d < 3:
                continue
            gain = own(t, *mates[j])[0] - ox
            openness = float(np.min(np.linalg.norm(opp - mates[j], axis=1)))
            w = math.exp(0.04 * gain * self.teams[t].tempo + 0.2 * min(openness, 8) - 0.1 * d)
            weights.append(w * (0.05 if d > 40 else 1.0))
            cand.append((j, d, openness))
        weights_arr = np.array(weights) / sum(weights)
        j, d, openness = cand[int(rng.choice(len(cand), p=weights_arr))]
        tx, ty = mates[j] + rng.normal(0, 1.0, 2)
        z = (self.p.pass_base + 3.0 * (pl.passing - 0.75) - self.p.pass_dist * d
             + self.p.pass_open * min(openness, 10) - (self.p.pass_press if press < 2.5 else 0))
        return Spec("pass", c, float(tx), float(ty), j, sigmoid(z))

    def _cross(self, st: State, pos: np.ndarray, rng) -> Spec:
        t = st.poss
        tx, ty = own(t, rng.uniform(93, 101), rng.uniform(27, 41))
        j = int(np.argmin(np.linalg.norm(pos[t, 1:] - [tx, ty], axis=1))) + 1
        openness = float(np.min(np.linalg.norm(pos[1 - t] - [tx, ty], axis=1)))
        return Spec("cross", st.carrier, tx, ty, j, 0.18 + 0.05 * min(openness, 4))

    def _clearance(self, st: State, pos: np.ndarray, rng) -> Spec:
        t = st.poss
        ox, oy = own(t, st.bx, st.by)
        tx, ty = own(t, min(ox + rng.uniform(30, 50), L - 5), rng.uniform(5, W - 5))
        j = int(np.argmin(np.linalg.norm(pos[t, 1:] - [tx, ty], axis=1))) + 1
        return Spec("clearance", st.carrier, tx, ty, j, 0.4)

    # ------------------------------------------------------------------ execution
    def _new_lapses(self, defending: int, rng) -> tuple[tuple[int, float, float], ...]:
        out = []
        for i in LAPSE_PLAYERS:
            pl = self.teams[defending].players[i]
            if rng.random() < self.p.lapse_rate * (1 - pl.discipline) / 0.25:
                if rng.random() < 0.55:  # caught upfield
                    out.append((i, float(rng.uniform(7, 14)), float(rng.normal(0, 2))))
                else:  # drawn towards the ball side, leaving the zone
                    side = 1.0 if SLOTS[i, 1] < W / 2 else -1.0
                    out.append((i, float(rng.normal(0, 2)), float(side * rng.uniform(7, 12))))
        return tuple(out)

    def _turnover(self, st: State, x: float, y: float, new_carrier: int, rng, dt: float) -> State:
        new_poss = 1 - st.poss
        return State(new_poss, x, y, new_carrier, st.clock + dt, st.period, True,
                     self._new_lapses(st.poss, rng))

    def _restart(self, st: State, team: int, rng, kind: str, dt: float) -> State:
        if kind == "kickoff":
            return State(team, L / 2, W / 2, 9, st.clock + dt, st.period, False,
                         self._new_lapses(1 - team, rng))
        x, y = own(team, 6, W / 2)
        return State(team, x, y, 0, st.clock + dt, st.period, False, self._new_lapses(1 - team, rng))

    def execute(self, st: State, spec: Spec, pos: np.ndarray, rng, force: str | None = None):
        """Run an action. Returns (events, next state, (shooting team, xg) or None, goal)."""
        t, a = st.poss, spec.actor
        d_team = 1 - t
        sx, sy = st.bx, st.by
        if force == "success":
            ok = True
        elif force == "fail":
            ok = False
        else:
            ok = rng.random() < spec.p_success

        def ev(kind, team, player, x0, y0, x1, y1, result, dt=0.0):
            return dict(kind=kind, team=team, player=player, start_x=x0, start_y=y0,
                        end_x=x1, end_y=y1, result=result, clock=st.clock + dt)

        if spec.kind == "shot":
            goal = rng.random() < spec.xg if force is None else force == "success"
            evs = [ev("shot", t, a, sx, sy, spec.tx, spec.ty, "success" if goal else "fail")]
            if goal:
                return evs, self._restart(st, d_team, rng, "kickoff", 45), (t, spec.xg), True
            if rng.random() < 0.25:
                gx, gy = own(d_team, 3, W / 2)
                evs.append(ev("keeper_save", d_team, 0, gx, gy, gx, gy, "success", 1))
                nxt = State(d_team, gx, gy, 0, st.clock + 6, st.period, False, self._new_lapses(t, rng))
                return evs, nxt, (t, spec.xg), False
            return evs, self._restart(st, d_team, rng, "goalkick", 15), (t, spec.xg), False

        dist = math.hypot(spec.tx - sx, spec.ty - sy)
        if spec.kind in ("pass", "cross", "clearance"):
            dt = 1.95 + dist / 16
            if ok:
                nxt = replace(st, bx=spec.tx, by=spec.ty, carrier=spec.receiver,
                              clock=st.clock + dt, can_carry=True)
                return [ev(spec.kind, t, a, sx, sy, spec.tx, spec.ty, "success")], nxt, None, False
            f = rng.uniform(0.45, 0.95)
            ix, iy = sx + (spec.tx - sx) * f, sy + (spec.ty - sy) * f
            k = int(np.argmin(np.linalg.norm(pos[d_team, 1:] - [ix, iy], axis=1))) + 1
            evs = [ev(spec.kind, t, a, sx, sy, ix, iy, "fail")]
            if rng.random() < 0.11:
                evs.append(ev("interception", d_team, k, ix, iy, ix, iy, "success", dt))
            return evs, self._turnover(st, ix, iy, k, rng, dt + 0.5), None, False

        if spec.kind in ("dribble", "take_on"):
            dt = 1.0 + dist / 6
            if ok:
                nxt = replace(st, bx=spec.tx, by=spec.ty, clock=st.clock + dt,
                              can_carry=spec.kind == "take_on")
                return [ev(spec.kind, t, a, sx, sy, spec.tx, spec.ty, "success")], nxt, None, False
            k = int(np.argmin(np.linalg.norm(pos[d_team, 1:] - [sx, sy], axis=1))) + 1
            evs = [ev(spec.kind, t, a, sx, sy, sx, sy, "fail")]
            if rng.random() < 0.5:
                evs.append(ev("tackle", d_team, k, sx, sy, sx, sy, "success", dt))
            return evs, self._turnover(st, sx, sy, k, rng, dt + 0.5), None, False

        raise ValueError(f"unknown action kind {spec.kind}")

    def step(self, st: State, rng, force: str | None = None, spec: Spec | None = None):
        pos = self.positions(st, rng)
        spec = spec or self.choose(st, pos, rng)
        evs, nxt, shot, goal = self.execute(st, spec, pos, rng, force)
        return pos, spec, evs, nxt, shot, goal

    # ------------------------------------------------------------------ counterfactuals
    def rollout(self, st: State, conceding: int, rng, horizon: int) -> float:
        """Expected danger for one sample: total xG the other team creates within the horizon."""
        danger = 0.0
        for _ in range(horizon):
            _, _, _, st, shot, goal = self.step(st, rng)
            if shot is not None and shot[0] != conceding:
                danger += shot[1]
            if goal:
                break
        return danger
