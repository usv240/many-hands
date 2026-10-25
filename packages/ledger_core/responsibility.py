"""Responsibility attribution for decisive moments.

A chain is the ordered list of actions that led to a decisive moment, with an action value
per action (VAEP: change in the chance of scoring minus change in the chance of conceding).
Functions here are pure: they take a chain and return shares that sum to 1.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping

import pandas as pd
from narrative_core.scapegoat import normalize

REQUIRED_COLUMNS = {"team_id", "player_id", "vaep_value"}


def _check(chain: pd.DataFrame) -> None:
    missing = REQUIRED_COLUMNS - set(chain.columns)
    if missing:
        raise ValueError(f"chain is missing columns: {sorted(missing)}")


MIN_FRACTION = 0.2   # a loss counts only if it is at least this share of the chain's largest loss
MIN_ABS = 0.002      # and at least this big in absolute terms (ordinary play is noisier than this)


# Defaults chosen on the synthetic ground-truth benchmark (benchmarks/synthetic/tune_ledger.py):
# counting only actions that lost the ball, with the final turnover weighted double, brings the
# ledger level with last-touch blame on distance to the truth (0.147 vs 0.148) while still
# sharing blame when more than one mistake caused the chance.
ONLY_FAILURES = True
LAST_TURNOVER_BOOST = 2.0  # extra weight on the action that finally handed the ball over


def onball_blame(chain: pd.DataFrame, defending_team_id: Hashable,
                 min_fraction: float = MIN_FRACTION, min_abs: float = MIN_ABS,
                 only_failures: bool = ONLY_FAILURES,
                 last_turnover_boost: float = LAST_TURNOVER_BOOST) -> dict[Hashable, float]:
    """Share of blame per defending player, from the actions they made on the ball.

    Every *material* loss of value by the defending side adds to that player's blame. A loss is
    material when it is at least `min_fraction` of the largest loss in the chain and at least
    `min_abs`; smaller dips are ordinary play, not mistakes, and counting them dilutes the real
    cause (measured on the synthetic ground-truth benchmark).

    `only_failures` restricts blame to actions that actually lost the ball (result not success).
    `last_turnover_boost` multiplies the weight of the final such loss before the chance, the
    proximate cause. Shares sum to 1, or the result is empty if no defending action lost value.
    """
    _check(chain)
    d = chain[(chain["team_id"] == defending_team_id) & chain["player_id"].notna()]
    loss = (-d["vaep_value"]).clip(lower=0)
    if "result_name" in d.columns:
        failed = d["result_name"] != "success"
        if only_failures and failed.any():
            loss = loss.where(failed, 0.0)
        if last_turnover_boost != 1.0 and failed.any():
            loss = loss.copy()
            loss.loc[failed[failed].index[-1]] *= last_turnover_boost
    if loss.empty or loss.max() <= 0:
        return {}
    material = loss[(loss >= min_fraction * loss.max()) & (loss >= min_abs)]
    weights = material.groupby(d.loc[material.index, "player_id"]).sum()
    return normalize(weights.to_dict())


def onball_credit(chain: pd.DataFrame, attacking_team_id: Hashable) -> dict[Hashable, float]:
    """Share of credit per attacking player: the positive values of their actions."""
    _check(chain)
    a = chain[(chain["team_id"] == attacking_team_id) & chain["player_id"].notna()]
    weights = a["vaep_value"].clip(lower=0).groupby(a["player_id"]).sum()
    return normalize(weights.to_dict())


def last_touch_ranking(chain: pd.DataFrame, defending_team_id: Hashable) -> list[Hashable]:
    """Baseline: defending players ordered from the most recent touch backwards."""
    _check(chain)
    d = chain[(chain["team_id"] == defending_team_id) & chain["player_id"].notna()]
    seen: list[Hashable] = []
    for player in reversed(d["player_id"].tolist()):
        if player not in seen:
            seen.append(player)
    return seen


def ranking(shares: Mapping[Hashable, float]) -> list[Hashable]:
    """Players ordered by share, largest first. Ties break on the player id for stability."""
    return [k for k, _ in sorted(shares.items(), key=lambda kv: (-kv[1], str(kv[0])))]
