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


def test_real_reader_outage_holds_publication(monkeypatch):
    from services.agents import extractor, models

    async def unavailable(*args, **kwargs):
        raise TimeoutError("reader timed out")

    monkeypatch.setattr(models, "available", lambda: True)
    monkeypatch.setattr(extractor, "model_mentions", unavailable)
    r = go(Request(CHAIN, incoming="Number 8's howler cost them the goal."))
    assert r.status == "held"
    assert r.line is None
    assert not r.variants
    assert "reader unavailable" in r.held_reason


def test_reader_best_effort_is_explicit(monkeypatch):
    from services.agents import extractor, models
    from services.api.app import store

    async def unavailable(*args, **kwargs):
        raise TimeoutError("reader timed out")

    monkeypatch.setattr(models, "available", lambda: True)
    monkeypatch.setattr(extractor, "model_mentions", unavailable)
    ledger = store.ledger_for_chain(CHAIN)
    moment = ledger.moment(CHAIN)
    _, used = asyncio.run(extractor.deep_extract(
        "Number 8 lost the ball.", store.roster(int(ledger.game_id)), moment.conceding_team_id))
    assert not used


def test_variants_check_actual_translation_and_wrong_scores(monkeypatch):
    from services.agents import workflow

    texts = {"analyst": "Corran Vale lead 99-98.", "casual": "A goal.",
             "club": "A goal.", "focus": "A goal.",
             "es": "El número 8 tuvo toda la culpa del gol."}
    checked = []
    original = workflow.deep_extract

    async def reader(text, roster, team_id, **kwargs):
        checked.append(text)
        return await original(text, roster, team_id, **kwargs)

    monkeypatch.setattr(workflow, "deep_extract", reader)
    monkeypatch.setattr(workflow, "_variant_templates", lambda *args: texts)
    r = go(Request(CHAIN))
    variants = {v["id"]: v for v in r.variants}
    assert texts["es"] in checked
    assert not variants["es"]["aired"]  # no multilingual reader in offline mode
    assert "requires the model reader" in variants["es"]["note"]
    assert not variants["analyst"]["aired"]
    assert "99-98" in variants["analyst"]["note"]


def test_variant_reader_failure_holds_only_that_variant(monkeypatch):
    from services.agents import workflow

    original = workflow.deep_extract

    async def reader(text, roster, team_id, **kwargs):
        if text == "An unavailable variant.":
            raise RuntimeError("reader unavailable")
        return await original(text, roster, team_id, **kwargs)

    monkeypatch.setattr(workflow, "deep_extract", reader)
    monkeypatch.setattr(workflow, "_variant_templates", lambda *args: {
        "analyst": "An unavailable variant.", "casual": "A goal.",
        "club": "A goal.", "focus": "A goal.", "es": "Un gol."})
    r = go(Request(CHAIN))
    variants = {v["id"]: v for v in r.variants}
    assert r.line
    assert not variants["analyst"]["aired"]
    assert variants["analyst"]["si"] is None
    assert variants["casual"]["aired"]


def test_investigator_picks_the_action_to_check():
    r = go(Request(CHAIN))
    assert r.check and r.check["player_id"] == max(r.audit["evidence"], key=r.audit["evidence"].get)
    assert r.check["question"].startswith("Look at action")


def test_own_goal_wording_and_misspelt_names_are_fact_errors():
    from services.agents.workflow import _fact_errors
    names = ["Rafe Quilian", "Yan Belain", "Corran Vale"]
    assert _fact_errors("An own clearance from number 8 let Quilian in.", {"names": names})
    assert _fact_errors("Despeje en propia puerta del número 8.", {"names": names})
    assert any("Quilan" in e for e in _fact_errors("Quilan scored again.", {"names": names}))
    assert not _fact_errors("A clearance in his own half by number 8 let Quilian score for Corran Vale.", {"names": names})
