"""The live feed with the in-process transport: kick-off publishes events, a goal wakes the agents."""

import asyncio
import os
import sys
from pathlib import Path

os.environ["MANYHANDS_OFFLINE"] = "1"
os.environ.pop("EVENTHUB_NAMESPACE", None)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api import live  # noqa: E402
from services.api.app import store  # noqa: E402


def test_goal_on_the_stream_wakes_the_agents():
    async def scenario():
        live.INTERVAL_S = 0.0
        hub = live.Hub()
        hub.namespace = ""  # force the in-process transport
        await hub.start()
        L = store.ledgers[20003]
        first_goal = min(m.shot_action_id for m in L.moments)
        q = hub.subscribe(20003)
        started = await hub.kickoff(L, first_goal - 5)
        seen_agent = seen_line = None
        events = 0
        for _ in range(400):
            msg = await asyncio.wait_for(q.get(), timeout=10)
            events += msg["type"] == "event"
            if msg["type"] == "line" and seen_line is None:
                seen_line = msg
            if msg["type"] == "agent":
                seen_agent = msg
                break
        await hub.stop()
        return started, events, seen_agent, seen_line, hub

    started, events, agent, line, hub = asyncio.run(scenario())
    assert started["transport"] == "in-process queue"
    assert events >= 5
    assert agent is not None and agent["result"]["status"] == "ready"
    assert agent["latency_s"] >= 0 and agent["result"]["audit"]["verdict"] != "unfair"
    assert agent["line_latency_s"] is not None and agent["line_latency_s"] <= agent["latency_s"]
    assert agent["graphic_sent_to"].startswith("broadcast-graphics")
    # The fair line goes on air before the audience versions are written, and the decision is logged.
    assert line is not None and line["chain_id"] == agent["chain_id"] and line["line"] == agent["result"]["line"]
    assert hub.log[0]["decision"] == "aired" and hub.verify_log()["ok"]


def test_only_fair_lines_air_without_a_producer():
    async def scenario():
        hub = live.Hub()
        hub.namespace = ""
        for verdict in ("watch", "unfair"):
            assert await hub.publish_graphic(20003, "20003-300", "A line.", {"verdict": verdict, "si": 0.3}) is None
        assert await hub.publish_graphic(20003, "20003-300", None, None) is None  # a held result
        graphic = await hub.publish_graphic(20003, "20003-300", "A fair line.", {"verdict": "fair", "si": 0.0})
        assert graphic["approved_by"].startswith("policy") and hub.graphics_sent == 1

    asyncio.run(scenario())


def test_queued_line_needs_a_producer_and_a_reason():
    async def scenario():
        hub = live.Hub()
        hub.namespace = ""
        hub.queue["20003-300"] = {"game_id": 20003, "chain_id": "20003-300", "line": "Number 8 again.",
                                  "audit": {"verdict": "watch", "si": 0.31}, "status": "pending", "queued_at": 0.0}
        try:
            await hub.decide("20003-300", "approve", "")
            raise AssertionError("approved without a reason")
        except ValueError:
            pass
        assert hub.graphics_sent == 0 and not hub.log
        out = await hub.decide("20003-300", "approve", "Replay shows he was unmarked", "Sam (producer)")
        assert out["graphic_sent_to"] and hub.graphics_sent == 1
        assert out["record"]["decision"] == "approved" and out["record"]["by"] == "Sam (producer)"
        try:
            await hub.decide("20003-300", "reject")
            raise AssertionError("decided twice")
        except ValueError:
            pass
        return hub

    hub = asyncio.run(scenario())
    assert hub.verify_log() == {"ok": True, "entries": 1, "broken_at": None}


def test_decision_log_detects_tampering():
    hub = live.Hub()
    for i in range(3):
        hub._record({"chain_id": f"c{i}", "decision": "aired", "by": "policy", "reason": ""})
    assert hub.verify_log()["ok"]
    hub.log[1]["reason"] = "edited later"
    assert hub.verify_log() == {"ok": False, "entries": 3, "broken_at": 1}


def test_stricter_policy_queues_even_fair_lines():
    async def scenario():
        live.INTERVAL_S = 0.0
        hub = live.Hub()
        hub.namespace = ""
        await hub.start()
        L = store.ledgers[20003]
        first_goal = min(m.shot_action_id for m in L.moments)
        q = hub.subscribe(20003)
        await hub.kickoff(L, first_goal - 5, auto_air=False)
        line = None
        for _ in range(400):
            msg = await asyncio.wait_for(q.get(), timeout=10)
            if msg["type"] == "line":
                line = msg
                break
        await hub.stop()
        assert line["queued"] and line["graphic_sent_to"] is None and hub.graphics_sent == 0
        assert line["check"] and "Does the replay show" in line["check"]["question"]
        try:
            await hub.decide(line["chain_id"], "approve")
            raise AssertionError("aired before the evidence question was answered")
        except ValueError:
            pass
        out = await hub.decide(line["chain_id"], "approve", evidence="confirmed")  # Fair and confirmed: no reason
        assert out["graphic_sent_to"] and out["record"]["decision"] == "approved"
        assert out["record"]["evidence"] == "confirmed"

    asyncio.run(scenario())


def test_evidence_answers_gate_airing():
    async def scenario():
        hub = live.Hub()
        hub.namespace = ""
        check = {"action_id": 7, "index": 3, "minute": 16, "player_id": "p8", "question": "Did number 8 lose it?"}
        for cid, verdict in (("a", "fair"), ("b", "fair"), ("c", "watch")):
            hub.queue[cid] = {"game_id": 20003, "chain_id": cid, "line": "A line.", "check": check, "clock": None,
                              "audit": {"verdict": verdict, "si": 0.1}, "status": "pending", "queued_at": 0.0}
        for bad in (dict(evidence="rejected"), dict(evidence="unclear")):  # data wrong; or unsure with no reason
            try:
                await hub.decide("a", "approve", **bad)
                raise AssertionError(f"aired with {bad}")
            except ValueError:
                pass
        assert (await hub.decide("a", "approve", "Replay is blocked by a player", evidence="unclear"))["graphic_sent_to"]
        assert (await hub.decide("b", "reject", evidence="rejected"))["record"]["evidence"] == "rejected"
        try:
            await hub.decide("c", "approve", evidence="confirmed")  # Watch still needs a reason
            raise AssertionError("aired a Watch line without a reason")
        except ValueError:
            pass
        assert hub.graphics_sent == 1 and hub.verify_log()["ok"]

    asyncio.run(scenario())
