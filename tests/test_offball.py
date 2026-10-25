import math

import pandas as pd
import pytest
from ledger_core.offball import combine, offball_blame


def positions(rows):
    return pd.DataFrame(rows, columns=["step_action_id", "team_id", "player_id", "x", "y"])


def chain(rows):
    return pd.DataFrame(rows, columns=["step_action_id", "team_id", "player_id", "end_x", "end_y",
                                       "offensive_value"])


def test_nearest_defender_carries_most_blame():
    c = chain([(1, "A", "a9", 90.0, 34.0, 0.1)])
    p = positions([(1, "D", "d4", 88.0, 34.0), (1, "D", "d5", 70.0, 34.0), (1, "D", "d2", 60.0, 10.0),
                   (1, "A", "a9", 90.0, 34.0)])
    shares = offball_blame(c, p, "D")
    assert shares["d4"] > shares["d5"] > shares["d2"]
    assert math.isclose(sum(shares.values()), 1.0)


def test_defensive_actions_add_no_offball_blame():
    c = chain([(1, "D", "d4", 50.0, 34.0, 0.2)])
    p = positions([(1, "D", "d4", 50.0, 34.0)])
    assert offball_blame(c, p, "D") == {}


def test_requires_step_column():
    with pytest.raises(ValueError):
        offball_blame(pd.DataFrame({"team_id": ["A"], "offensive_value": [0.1]}), positions([]), "D")


def test_combine_with_zero_lambda_is_onball():
    assert combine({"d4": 1.0}, {"d5": 1.0}, 0.0) == {"d4": 1.0}
