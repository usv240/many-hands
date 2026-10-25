"""Decisive moments and the chains of actions that led to them.

A decisive moment is a goal, a good chance, or a big swing in the chance of scoring. Its chain
is every action from the moment the conceding team last had the ball under control up to the
shot, capped at a window so very old actions are not blamed for a chance much later.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

SHOT_TYPES = ("shot", "shot_penalty", "shot_freekick")
CONTROL_TYPES = ("pass", "cross", "dribble", "take_on", "clearance", "throw_in", "goalkick",
                 "freekick_short", "freekick_crossed", "corner_short", "corner_crossed")


@dataclass(frozen=True)
class Moment:
    game_id: object
    shot_action_id: int
    attacking_team_id: object
    conceding_team_id: object
    shooter_id: object
    goal: bool
    start_action_id: int
    xg: float | None = None


def find_moments(actions: pd.DataFrame, min_xg: float = 0.07, max_window: int = 25,
                 xg_col: str | None = None) -> list[Moment]:
    """Return decisive moments in one match's rated actions, in match order."""
    a = actions.sort_values(["period_id", "action_id"]).reset_index(drop=True)
    teams = a["team_id"].unique().tolist()
    out = []
    for i in a.index[a["type_name"].isin(SHOT_TYPES)]:
        row = a.loc[i]
        goal = row["result_name"] == "success"
        xg = float(row[xg_col]) if xg_col and xg_col in a.columns and pd.notna(row[xg_col]) else None
        quality = xg if xg is not None else float(row.get("scores", 0.0))
        if not goal and quality < min_xg:
            continue
        attacking = row["team_id"]
        conceding = next((t for t in teams if t != attacking), None)
        start = i
        for j in range(i - 1, max(i - max_window, -1), -1):
            prev = a.loc[j]
            if prev["period_id"] != row["period_id"]:
                break
            start = j
            if prev["team_id"] == conceding and prev["type_name"] in CONTROL_TYPES \
                    and prev["result_name"] == "success":
                break
        out.append(Moment(row["game_id"], int(row["action_id"]), attacking, conceding,
                          row["player_id"], bool(goal), int(a.loc[start, "action_id"]), xg))
    return out


def chain_for(actions: pd.DataFrame, moment: Moment) -> pd.DataFrame:
    a = actions[(actions["game_id"] == moment.game_id)]
    return a[(a["action_id"] >= moment.start_action_id) &
             (a["action_id"] <= moment.shot_action_id)].sort_values("action_id").reset_index(drop=True)
