import pandas as pd
from ledger_core.chains import chain_for, find_moments


def actions(rows):
    return pd.DataFrame(rows, columns=["game_id", "period_id", "action_id", "team_id", "player_id",
                                       "type_name", "result_name", "scores"])


def test_chain_starts_after_conceding_teams_last_controlled_action():
    a = actions([
        (1, 1, 0, "D", "d1", "pass", "success", 0.01),   # last controlled action by D
        (1, 1, 1, "D", "d8", "pass", "fail", 0.02),       # the loss
        (1, 1, 2, "A", "a9", "dribble", "success", 0.1),
        (1, 1, 3, "A", "a10", "shot", "success", 0.3),
    ])
    moments = find_moments(a)
    assert len(moments) == 1
    m = moments[0]
    assert m.goal and m.conceding_team_id == "D" and m.start_action_id == 0
    assert chain_for(a, m)["action_id"].tolist() == [0, 1, 2, 3]


def test_low_quality_miss_is_not_decisive_but_goal_is():
    a = actions([
        (1, 1, 0, "A", "a9", "shot", "fail", 0.02),
        (1, 1, 1, "A", "a9", "shot", "fail", 0.2),
        (1, 1, 2, "A", "a9", "shot", "success", 0.01),
    ])
    ids = [m.shot_action_id for m in find_moments(a)]
    assert ids == [1, 2]


def test_window_cap_and_period_boundary():
    rows = [(1, 1, i, "A", "a1", "dribble", "success", 0.05) for i in range(40)]
    rows.append((1, 2, 40, "A", "a9", "shot", "success", 0.3))
    m = find_moments(actions(rows))[0]
    assert m.start_action_id == 40  # a new period stops the chain
