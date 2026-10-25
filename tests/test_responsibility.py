import math

import pandas as pd
import pytest
from hypothesis import given
from hypothesis import strategies as st
from ledger_core.responsibility import (
    last_touch_ranking,
    onball_blame,
    onball_credit,
    ranking,
)

DEF, ATT = "D", "A"


def chain(rows):
    return pd.DataFrame(rows, columns=["team_id", "player_id", "vaep_value"])


def test_blame_goes_to_defenders_who_lost_value():
    c = chain([
        (DEF, "d8", -0.04),   # blind pass under pressure
        (ATT, "a9", 0.02),
        (DEF, "d5", -0.02),   # heavy touch
        (DEF, "d4", 0.01),    # a good action adds no blame
        (ATT, "a10", 0.30),   # shot
    ])
    shares = onball_blame(c, DEF)
    assert set(shares) == {"d8", "d5"}
    assert math.isclose(shares["d8"], 2 / 3)
    assert ranking(shares) == ["d8", "d5"]


def test_credit_goes_to_attackers_who_added_value():
    c = chain([(ATT, "a9", 0.02), (ATT, "a10", 0.06), (DEF, "d5", -0.02)])
    assert ranking(onball_credit(c, ATT)) == ["a10", "a9"]


def test_last_touch_orders_by_recency():
    c = chain([(DEF, "d8", -0.04), (DEF, "d5", -0.01), (ATT, "a9", 0.1), (DEF, "d8", 0.0)])
    assert last_touch_ranking(c, DEF) == ["d8", "d5"]


def test_no_lost_value_gives_empty_blame():
    assert onball_blame(chain([(DEF, "d1", 0.1), (ATT, "a1", 0.2)]), DEF) == {}


def test_missing_columns_raise():
    with pytest.raises(ValueError):
        onball_blame(pd.DataFrame({"team_id": [DEF]}), DEF)


rows = st.lists(
    st.tuples(st.sampled_from([DEF, ATT]), st.sampled_from(["x", "y", "z"]),
              st.floats(min_value=-1, max_value=1)),
    min_size=1, max_size=30,
)


@given(rows)
def test_blame_shares_sum_to_one_or_are_empty(r):
    shares = onball_blame(chain(r), DEF)
    assert shares == {} or math.isclose(sum(shares.values()), 1.0)


@given(rows)
def test_relabelling_players_relabels_shares(r):
    swap = {"x": "y", "y": "x", "z": "z"}
    original = onball_blame(chain(r), DEF)
    swapped = onball_blame(chain([(t, swap[p], v) for t, p, v in r]), DEF)
    assert {swap[k]: v for k, v in original.items()} == pytest.approx(swapped)
