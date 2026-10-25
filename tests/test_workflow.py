"""The agent workflow in offline mode: same graph, deterministic writers. Model mode is exercised
by the live smoke test (scripts/smoke_agents.py) because it needs Azure."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ["MANYHANDS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agents.workflow import Request, run  # noqa: E402

CHAIN = "20003-300"  # a goal where blame is genuinely shared


def go(req: Request):
    return asyncio.run(run(req))


def test_unfair_incoming_line_is_rewritten_and_never_airs_unchanged():
    r = go(Request(CHAIN, incoming="Number 8's howler cost them the goal."))
    assert r.status == "ready"
    assert r.history[0]["verdict"] == "unfair"
    assert r.audit["verdict"] == "fair" and r.line != r.history[0]["text"]
    assert [s["agent"] for s in r.trace][:3] == ["Investigator", "Auditor", "Narrator"]


def test_written_line_is_fair_and_personalised():
    r = go(Request(CHAIN))
    assert r.audit["verdict"] == "fair"
    assert {v["id"] for v in r.variants} == {"analyst", "casual", "club", "focus", "es"}
    assert all(v["verdict"] != "unfair" for v in r.variants if v["aired"])


def test_auditor_outage_fails_closed():
    r = go(Request(CHAIN, incoming="Number 8's howler cost them the goal.", simulate_auditor_outage=True))
    assert r.status == "held" and r.line is None and r.variants == []


def test_fair_incoming_line_passes_untouched():
    r = go(Request(CHAIN, incoming="Loose balls from number 8 and number 9 let them through."))
    assert r.revisions == 0 and r.line == "Loose balls from number 8 and number 9 let them through."


def test_unknown_chain_raises():
    with pytest.raises(HTTPException):
        go(Request("nope"))


def test_wrong_scoreline_never_airs():
    r = go(Request(CHAIN, incoming="Corran Vale go 1-0 up after loose balls from number 8 and number 9."))
    assert r.history[0]["verdict"] == "unfair" and r.history[0]["fact_errors"]
    assert "1-0" not in (r.line or "")
