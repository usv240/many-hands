"""Usage limits on the public demo: per-caller rate limits, the daily model budget, the live-match cap."""

import asyncio
import os
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

os.environ["MANYHANDS_OFFLINE"] = "1"
os.environ.pop("EVENTHUB_NAMESPACE", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agents import models  # noqa: E402
from services.api import guard, live  # noqa: E402
from services.api.app import store  # noqa: E402


def test_a_caller_is_limited_per_minute_and_recovers():
    lim = guard.Limits()
    for i in range(guard.PER_MINUTE["model"]):
        lim.check("model", "1.2.3.4", now=100.0 + i)
    with pytest.raises(HTTPException) as err:
        lim.check("model", "1.2.3.4", now=120.0)
    assert err.value.status_code == 429 and "Retry-After" in err.value.headers
    lim.check("model", "5.6.7.8", now=120.0)            # another caller is unaffected
    lim.check("model", "1.2.3.4", now=100.0 + 61)       # a minute later the first caller can go again


def test_daily_budget_runs_out_and_resets(monkeypatch):
    monkeypatch.setattr(guard, "DAILY_MODEL_RUNS", 2)
    lim = guard.Limits()
    assert lim.take_model_run() and lim.take_model_run()
    assert not lim.take_model_run()
    lim.day = "1999-01-01"                              # a new day
    assert lim.take_model_run()


def test_over_budget_the_agents_use_templates_and_say_why(monkeypatch):
    monkeypatch.setenv("MANYHANDS_OFFLINE", "0")
    monkeypatch.setattr(models, "_env", lambda: {"AZURE_AI_PROJECT_ENDPOINT": "https://example"})
    assert models.available()
    models.templates_only(True)
    try:
        assert not models.available()
        assert models.offline_reason() == "today's model budget is used up"
    finally:
        models.templates_only(False)


def test_too_many_live_matches_are_refused(monkeypatch):
    monkeypatch.setattr(guard, "MAX_LIVE_MATCHES", 1)

    async def scenario():
        hub = live.Hub()
        hub.namespace = ""
        hub.running[1] = asyncio.create_task(asyncio.sleep(5))
        try:
            with pytest.raises(live.LiveFullError):
                await hub.kickoff(store.ledgers[20003], None)
        finally:
            hub.running[1].cancel()

    asyncio.run(scenario())


def test_client_id_prefers_the_forwarded_address():
    class R:
        headers = {"x-forwarded-for": "9.9.9.9, 10.0.0.1"}
        client = None
    assert guard.client_id(R()) == "9.9.9.9"
