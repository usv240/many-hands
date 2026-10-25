import math

import pytest
from hypothesis import given
from hypothesis import strategies as st
from narrative_core.scapegoat import (
    Policy,
    Verdict,
    blame_inflation,
    normalize,
    scapegoat_index,
    verdict,
)

players = st.sampled_from(["p1", "p2", "p3", "p4", "p5", "p6"])
weights = st.dictionaries(players, st.floats(min_value=0, max_value=10), min_size=1)


@given(weights, weights)
def test_si_is_between_zero_and_one(b, r):
    si = scapegoat_index(b, r)
    assert 0.0 <= si <= 1.0 + 1e-9


@given(weights)
def test_story_matching_evidence_scores_zero(r):
    if normalize(r):
        assert math.isclose(scapegoat_index(r, r), 0.0, abs_tol=1e-9)


@given(weights, weights)
def test_si_is_symmetric_when_both_sides_blame(b, r):
    if normalize(b) and normalize(r):
        assert math.isclose(scapegoat_index(b, r), scapegoat_index(r, b), abs_tol=1e-9)


@given(weights)
def test_sentence_blaming_no_one_is_fair(r):
    assert scapegoat_index({}, r) == 0.0
    assert scapegoat_index({"p1": 0.0}, r) == 0.0


def test_sole_blame_equals_one_minus_that_players_share():
    evidence = {"p5": 0.19, "p8": 0.34, "p4": 0.27, "p2": 0.20}
    assert math.isclose(scapegoat_index({"p5": 1}, evidence), 1 - 0.19)


def test_justified_blame_is_never_unfair():
    # One player holds at least 60 percent, so blaming them alone is at most 0.40.
    evidence = {"p5": 0.6, "p8": 0.25, "p4": 0.15}
    si = scapegoat_index({"p5": 1}, evidence)
    assert verdict(si) is not Verdict.UNFAIR


def test_blame_without_evidence_is_maximal():
    assert scapegoat_index({"p5": 1}, {}) == 1.0


def test_inflation():
    infl = blame_inflation({"p5": 1}, {"p5": 0.2, "p8": 0.8})
    assert math.isclose(infl["p5"], 5.0)


@pytest.mark.parametrize(
    ("si", "expected"),
    [(0.0, Verdict.FAIR), (0.2, Verdict.FAIR), (0.21, Verdict.WATCH), (0.4, Verdict.WATCH),
     (0.41, Verdict.UNFAIR), (1.0, Verdict.UNFAIR)],
)
def test_verdict_bands(si, expected):
    assert verdict(si) is expected


def test_policy_rejects_inverted_thresholds():
    with pytest.raises(ValueError):
        Policy(watch_above=0.5, unfair_above=0.3)
