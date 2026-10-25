"""Off-ball responsibility: blame for where defenders stood, not only for what they did.

Idea (simplified from Bischofberger et al. 2026): each time the attacking side made the chance
more dangerous, the defenders closest to where that action ended were the ones responsible for
stopping it. Their share of that increase falls off with distance. Only positions are used; the
ledger never sees the simulator's internal lapse flags, so this is a fair test of the method.
"""

from __future__ import annotations

from collections.abc import Hashable

import numpy as np
import pandas as pd
from narrative_core.scapegoat import normalize

SIGMA_M = 10.0      # how quickly responsibility fades with distance, in metres
NEAREST_K = 4       # only the nearest defenders carry responsibility for an action


def offball_blame(chain: pd.DataFrame, positions: pd.DataFrame, defending_team_id: Hashable,
                  value_col: str = "offensive_value") -> dict[Hashable, float]:
    """Share of positional blame per defender for the attacking actions in a chain.

    `positions` holds one row per player per step: step_action_id, team_id, player_id, x, y.
    Attacking actions that raised the chance of scoring (positive `value_col`) are weighted by
    that increase and shared among the nearest defenders to the action's end point.
    """
    if "step_action_id" not in chain.columns:
        raise ValueError("chain needs a step_action_id column to look up positions")
    att = chain[(chain["team_id"] != defending_team_id) & (chain[value_col] > 0)]
    if att.empty:
        return {}
    defenders = positions[positions["team_id"] == defending_team_id]
    by_step = {sid: g for sid, g in defenders.groupby("step_action_id")}
    weights: dict[Hashable, float] = {}
    for row in att.itertuples(index=False):
        g = by_step.get(row.step_action_id)
        if g is None:
            continue
        d = np.hypot(g["x"].to_numpy() - row.end_x, g["y"].to_numpy() - row.end_y)
        k = np.exp(-(d**2) / (2 * SIGMA_M**2))
        order = np.argsort(d)[:NEAREST_K]
        total = k[order].sum()
        if total <= 0:
            continue
        for idx in order:
            pid = g["player_id"].iloc[idx]
            weights[pid] = weights.get(pid, 0.0) + float(row[chain.columns.get_loc(value_col)]) * k[idx] / total
    return normalize(weights)


def combine(onball: dict, offball: dict, lam: float) -> dict:
    """Blend on-ball and off-ball shares. lam weights the off-ball part."""
    keys = set(onball) | set(offball)
    return normalize({k: onball.get(k, 0.0) + lam * offball.get(k, 0.0) for k in keys})
