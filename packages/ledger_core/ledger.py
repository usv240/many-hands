"""The Responsibility Ledger for one match: moments, chains, blame, credit and the unsung.

This is the single read model behind the API, the MCP tools and the agents. It is pure Python
over rated actions (SPADL plus VAEP columns) and optional positions, so it runs anywhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from ledger_core.chains import Moment, chain_for, find_moments
from ledger_core.offball import combine, offball_blame
from ledger_core.responsibility import (
    last_touch_ranking,
    onball_blame,
    onball_credit,
    ranking,
)

OFFBALL_WEIGHT = 0.0  # measured on the synthetic ground truth: positional blame did not help


@dataclass
class Contributor:
    player_id: str
    share: float
    reason: str


@dataclass
class Responsibility:
    chain_id: str
    method: str
    conceding_team_id: str
    shares: dict[str, float]
    contributors: list[Contributor]
    last_touch: list[str]
    n_actions: int


@dataclass
class MatchLedger:
    game_id: object
    actions: pd.DataFrame
    positions: pd.DataFrame | None = None
    roster: pd.DataFrame | None = None
    moments: list[Moment] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.actions = self.actions.sort_values(["period_id", "action_id"]).reset_index(drop=True)
        self.moments = find_moments(self.actions)
        self._by_id = {self.chain_id(m): m for m in self.moments}

    # ------------------------------------------------------------------ lookups
    @staticmethod
    def chain_id(m: Moment) -> str:
        return f"{m.game_id}-{m.shot_action_id}"

    def moment(self, chain_id: str) -> Moment:
        try:
            return self._by_id[chain_id]
        except KeyError as exc:
            raise KeyError(f"unknown chain {chain_id}") from exc

    def chain(self, chain_id: str) -> pd.DataFrame:
        return chain_for(self.actions, self.moment(chain_id))

    def name(self, player_id: str) -> str:
        if self.roster is None:
            return str(player_id)
        row = self.roster[self.roster.player_id == player_id]
        return str(row.name.iloc[0]) if not row.empty else str(player_id)

    def shirt(self, player_id: str) -> int | None:
        if self.roster is None:
            return None
        row = self.roster[self.roster.player_id == player_id]
        return int(row.shirt.iloc[0]) if not row.empty else None

    # ------------------------------------------------------------------ responsibility
    def responsibility(self, chain_id: str, method: str = "combined") -> Responsibility:
        m = self.moment(chain_id)
        c = self.chain(chain_id)
        d = m.conceding_team_id
        if method == "lasttouch":
            last = last_touch_ranking(c.iloc[:-1], d)
            shares = {last[0]: 1.0} if last else {}
        else:
            on = onball_blame(c, d)
            if method == "vaep" or self.positions is None or OFFBALL_WEIGHT == 0:
                shares = on
            else:
                off = offball_blame(c, self.positions, d)
                shares = combine(on, off, OFFBALL_WEIGHT) if method == "combined" else off
        contributors = [Contributor(p, s, self._reason(c, p, d)) for p, s in
                        sorted(shares.items(), key=lambda kv: -kv[1])]
        return Responsibility(chain_id, method, d, shares, contributors,
                              last_touch_ranking(c.iloc[:-1], d), int(len(c)))

    def _reason(self, chain: pd.DataFrame, player_id: str, team_id: str) -> str:
        mine = chain[(chain.player_id == player_id) & (chain.team_id == team_id)]
        losses = mine[mine.vaep_value < 0].sort_values("vaep_value")
        if losses.empty:
            return "involved in the build-up"
        a = losses.iloc[0]
        kind = str(a.type_name).replace("_", " ")
        outcome = "lost the ball" if a.result_name != "success" else "played it backwards under pressure"
        where = "in own half" if (a.start_x < 52.5) == (team_id == chain.team_id.iloc[0]) else "upfield"
        return f"{kind} that {outcome} {where}, {int(a.time_seconds // 60)}:{int(a.time_seconds % 60):02d}"

    # ------------------------------------------------------------------ credit
    def credit(self, chain_id: str) -> dict[str, float]:
        m = self.moment(chain_id)
        return onball_credit(self.chain(chain_id), m.attacking_team_id)

    def unsung(self, chain_id: str) -> Contributor | None:
        """The attacker who added the most value without taking the shot."""
        m = self.moment(chain_id)
        cred = {p: s for p, s in self.credit(chain_id).items() if p != m.shooter_id}
        if not cred:
            return None
        p = ranking(cred)[0]
        c = self.chain(chain_id)
        best = c[(c.player_id == p)].sort_values("vaep_value", ascending=False).iloc[0]
        return Contributor(p, cred[p], f"{str(best.type_name).replace('_', ' ')} that raised the danger most")

    # ------------------------------------------------------------------ counterfactual
    def counterfactual(self, chain_id: str, action_id: int) -> dict:
        """What the chain's danger looks like if one defending loss is treated as recovered.

        Uses the ledger's own values: the share of accumulated danger that disappears when this
        action's loss is removed. A model-replayed version lives in the agent service.
        """
        c = self.chain(chain_id)
        m = self.moment(chain_id)
        d = m.conceding_team_id
        losses = c[(c.team_id == d) & (c.vaep_value < 0)]
        total = float(-losses.vaep_value.sum())
        row = losses[losses.action_id == action_id]
        if row.empty or total <= 0:
            return {"action_id": action_id, "danger_removed_pct": 0.0}
        return {"action_id": action_id, "player_id": str(row.player_id.iloc[0]),
                "danger_removed_pct": round(100 * float(-row.vaep_value.iloc[0]) / total, 1)}

    # ------------------------------------------------------------------ summaries
    def moment_summary(self, chain_id: str) -> dict:
        m = self.moment(chain_id)
        r = self.responsibility(chain_id)
        u = self.unsung(chain_id)
        c = self.chain(chain_id)
        return {
            "chain_id": chain_id, "game_id": m.game_id, "goal": m.goal,
            "attacking_team_id": m.attacking_team_id, "conceding_team_id": m.conceding_team_id,
            "shooter_id": m.shooter_id, "clock_s": float(c.time_seconds.iloc[-1]),
            "period": int(c.period_id.iloc[-1]), "n_actions": int(len(c)),
            "minute": int(c.time_seconds.iloc[-1] // 60) + (45 if int(c.period_id.iloc[-1]) == 2 else 0),
            "responsibility": [{"player_id": x.player_id, "name": self.name(x.player_id),
                                "shirt": self.shirt(x.player_id), "share": round(x.share, 3),
                                "reason": x.reason} for x in r.contributors],
            "last_touch": r.last_touch[:1],
            "unsung": None if u is None else {"player_id": u.player_id, "name": self.name(u.player_id),
                                               "shirt": self.shirt(u.player_id),
                                               "share": round(u.share, 3), "reason": u.reason},
        }
