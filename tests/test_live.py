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
        seen_agent = None
        events = 0
        for _ in range(400):
            msg = await asyncio.wait_for(q.get(), timeout=10)
            events += msg["type"] == "event"
            if msg["type"] == "agent":
                seen_agent = msg
                break
        await hub.stop()
        return started, events, seen_agent

    started, events, agent = asyncio.run(scenario())
    assert started["transport"] == "in-process queue"
    assert events >= 5
    assert agent is not None and agent["result"]["status"] == "ready"
    assert agent["latency_s"] >= 0 and agent["result"]["audit"]["verdict"] != "unfair"
