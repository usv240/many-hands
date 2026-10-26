"""The live match feed: Azure Event Hubs in, agents out.

Kick-off publishes a fictional match's actions, in order, to the `match-events` event hub. A
consumer reads the hub; every event goes to the Studio over Server-Sent Events, and when a goal or
big chance arrives, the consumer wakes the agent workflow on that moment by itself. The time from
the goal reaching Event Hubs to a fair, audited line being ready is measured on every goal.

Without Event Hubs configured (local runs, tests), an in-process queue stands in, so the same code
path still works and the Studio says which transport is in use.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import time
from collections import defaultdict, deque
from dataclasses import asdict
from typing import Any

from services.agents import models

log = logging.getLogger("manyhands.live")
INTERVAL_S = 0.06          # time between published actions: a minute of play in about 2 seconds
LEAD_ACTIONS = 40          # a replay starts this many actions before the next goal
GENESIS = "0" * 64


def _digest(body: dict) -> str:
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Hub:
    def __init__(self) -> None:
        env = models._env()
        self.namespace = env.get("EVENTHUB_NAMESPACE") or ""
        self.name = env.get("EVENTHUB_NAME") or "match-events"
        self.graphics_name = env.get("EVENTHUB_GRAPHICS_NAME") or "broadcast-graphics"
        self.graphics_sent = 0
        self._graphics_producer = None
        self.local: asyncio.Queue[dict] = asyncio.Queue()
        self.subscribers: dict[int, set[asyncio.Queue]] = defaultdict(set)
        self.backlog: dict[int, deque] = defaultdict(lambda: deque(maxlen=400))
        self.latencies: deque[float] = deque(maxlen=200)       # goal to all five versions ready
        self.line_latencies: deque[float] = deque(maxlen=200)  # goal to the approved line on air or queued
        self.queue: dict[str, dict] = {}                       # lines waiting for a producer, by chain id
        self.log: list[dict] = []                              # hash-chained record of every decision
        self.running: dict[int, asyncio.Task] = {}
        self._consumer: asyncio.Task | None = None
        self._producer = None

    @property
    def transport(self) -> str:
        return "Azure Event Hubs" if self.namespace else "in-process queue"

    # ------------------------------------------------------------------ plumbing
    async def start(self) -> None:
        if self._consumer is None:
            self._consumer = asyncio.create_task(self._consume())

    async def stop(self) -> None:
        for t in [self._consumer, *self.running.values()]:
            if t:
                t.cancel()
        for producer in (self._producer, self._graphics_producer):
            if producer is not None:
                with contextlib.suppress(Exception):
                    await producer.close()

    def _fqdn(self) -> str:
        return f"{self.namespace}.servicebus.windows.net"

    async def _publish(self, payload: dict) -> None:
        if not self.namespace:
            await self.local.put(payload)
            return
        from azure.eventhub import EventData
        from azure.eventhub.aio import EventHubProducerClient
        if self._producer is None:
            self._producer = EventHubProducerClient(fully_qualified_namespace=self._fqdn(), eventhub_name=self.name,
                                                    credential=models.async_credential())
        batch = await self._producer.create_batch()
        batch.add(EventData(json.dumps(payload)))
        await self._producer.send_batch(batch)

    async def _send_graphics(self, payload: dict) -> None:
        """Write to the `broadcast-graphics` hub: graphics, audience versions and decision records."""
        if not self.namespace:
            return
        from azure.eventhub import EventData
        from azure.eventhub.aio import EventHubProducerClient
        if self._graphics_producer is None:
            self._graphics_producer = EventHubProducerClient(
                fully_qualified_namespace=self._fqdn(), eventhub_name=self.graphics_name,
                credential=models.async_credential())
        batch = await self._graphics_producer.create_batch()
        batch.add(EventData(json.dumps(payload)))
        await self._graphics_producer.send_batch(batch)

    async def publish_graphic(self, game_id: int, chain_id: str, line: str | None, audit: dict | None,
                              *, producer: str | None = None) -> dict | None:
        """Send an approved line to the broadcaster's graphics system.

        Policy: a line the Auditor scored Fair airs at once. Anything else airs only when a named
        producer approves it (`decide`). A held result has no line and sends nothing.
        """
        if not line or not audit:
            return None
        if audit.get("verdict") != "fair" and producer is None:
            return None
        graphic = {
            "kind": "lower-third", "game_id": game_id, "chain_id": chain_id, "line": line,
            "scapegoat_index": audit["si"], "verdict": audit["verdict"],
            "approved_by": producer or "policy: Fair lines air automatically",
            "duration_s": 7, "sent_at": time.time(),
        }
        await self._send_graphics(graphic)
        self.graphics_sent += 1
        return graphic

    # ------------------------------------------------------------------ editorial control
    def _record(self, entry: dict) -> dict:
        """Append to the hash-chained decision log: each record commits to the one before it."""
        body = {**entry, "at": round(time.time(), 3), "prev": self.log[-1]["hash"] if self.log else GENESIS}
        body["hash"] = _digest(body)
        self.log.append(body)
        return body

    def verify_log(self) -> dict:
        prev = GENESIS
        for i, e in enumerate(self.log):
            body = {k: v for k, v in e.items() if k != "hash"}
            if e["prev"] != prev or _digest(body) != e["hash"]:
                return {"ok": False, "entries": len(self.log), "broken_at": i}
            prev = e["hash"]
        return {"ok": True, "entries": len(self.log), "broken_at": None}

    async def _log(self, entry: dict) -> dict:
        record = self._record(entry)
        try:  # a durable copy outside this process
            await self._send_graphics({"kind": "decision", **record})
        except Exception as exc:
            log.warning("decision record not written to Event Hubs: %s", exc)
        return record

    async def decide(self, chain_id: str, decision: str, reason: str = "", producer: str = "producer") -> dict:
        """A producer's decision on a queued line. Airing a line the check did not pass needs a reason."""
        item = self.queue.get(chain_id)
        if item is None:
            raise KeyError(chain_id)
        if item["status"] != "pending":
            raise ValueError(f"already {item['status']}")
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be approve or reject")
        if decision == "approve" and not reason.strip():
            raise ValueError("a typed reason is needed to air a line the check did not pass")
        item["status"] = "approved" if decision == "approve" else "rejected"
        record = await self._log({"chain_id": chain_id, "line": item["line"], "verdict": item["audit"]["verdict"],
                                  "si": item["audit"]["si"], "decision": item["status"], "by": producer,
                                  "reason": reason.strip()})
        graphic = None
        if decision == "approve":
            graphic = await self.publish_graphic(item["game_id"], chain_id, item["line"], item["audit"],
                                                 producer=f"{producer}: {reason.strip()}")
        sent_to = f"{self.graphics_name} ({self.transport})" if graphic else None
        self._fan_out(item["game_id"], {"type": "decided", "item": item, "record": record, "graphic_sent_to": sent_to})
        return {"item": item, "record": record, "graphic_sent_to": sent_to}

    async def _consume(self) -> None:
        if not self.namespace:
            while True:
                await self._on_payload(await self.local.get())
        from azure.eventhub.aio import EventHubConsumerClient
        while True:  # reconnect forever; a dropped connection must not stop the feed
            try:
                client = EventHubConsumerClient(fully_qualified_namespace=self._fqdn(), eventhub_name=self.name,
                                                consumer_group="$Default", credential=models.async_credential())
                async with client:
                    async def on_event(_ctx, event):
                        if event is not None:
                            await self._on_payload(json.loads(event.body_as_str()))
                    await client.receive(on_event=on_event, starting_position="@latest")
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("event hub consumer restarting: %s", exc)
                await asyncio.sleep(3)

    def _fan_out(self, game_id: int, message: dict) -> None:
        self.backlog[game_id].append(message)
        for q in list(self.subscribers[game_id]):
            q.put_nowait(message)

    # ------------------------------------------------------------------ the feed
    async def _on_payload(self, p: dict) -> None:
        if p.get("kind") == "control":
            self._fan_out(p["game_id"], p)
            return
        game_id = p["game_id"]
        p["received_at"] = time.time()
        self._fan_out(game_id, {**p, "action_type": p.get("type"), "type": "event"})
        chain_id = f"{game_id}-{p['action_id']}"
        if p.get("decisive"):
            asyncio.create_task(self._wake_agents(game_id, chain_id, p["published_at"]))

    async def _wake_agents(self, game_id: int, chain_id: str, published_at: float) -> None:
        from services.agents.workflow import Request, run
        self._fan_out(game_id, {"type": "agent-start", "chain_id": chain_id, "at": time.time()})
        line_at: dict[str, Any] = {"latency": None, "sent_to": None}

        async def on_line(line: str, audit: dict) -> None:
            """The Auditor approved the main line: air it now if Fair, else queue it for a producer."""
            latency = time.time() - published_at
            line_at["latency"] = latency
            self.line_latencies.append(latency)
            if audit["verdict"] == "fair":
                sent = None
                try:
                    sent = await self.publish_graphic(game_id, chain_id, line, audit)
                except Exception as exc:  # the Studio still shows the line if the graphics hub is unreachable
                    log.warning("graphics publish failed: %s", exc)
                line_at["sent_to"] = f"{self.graphics_name} ({self.transport})" if sent else None
                await self._log({"chain_id": chain_id, "line": line, "verdict": "fair", "si": audit["si"],
                                 "decision": "aired", "by": "policy: Fair lines air automatically", "reason": ""})
            else:
                self.queue[chain_id] = {"game_id": game_id, "chain_id": chain_id, "line": line, "audit": audit,
                                        "status": "pending", "queued_at": time.time()}
                self._fan_out(game_id, {"type": "queued", "item": self.queue[chain_id]})
            self._fan_out(game_id, {"type": "line", "chain_id": chain_id, "line": line, "audit": audit,
                                    "line_latency_s": round(latency, 2), "graphic_sent_to": line_at["sent_to"]})

        try:
            result = await run(Request(chain_id, on_line=on_line))
            latency = time.time() - published_at
            self.latencies.append(latency)
            if result.status != "ready":
                await self._log({"chain_id": chain_id, "line": None, "verdict": None, "si": None,
                                 "decision": "held", "by": "Auditor", "reason": result.held_reason or ""})
            elif line_at["sent_to"]:
                versions = {v["id"]: v["text"] for v in result.variants if v["aired"]}
                with contextlib.suppress(Exception):
                    await self._send_graphics({"kind": "versions", "game_id": game_id, "chain_id": chain_id,
                                               "versions": versions, "sent_at": time.time()})
            self._fan_out(game_id, {"type": "agent", "chain_id": chain_id, "latency_s": round(latency, 2),
                                    "line_latency_s": None if line_at["latency"] is None else round(line_at["latency"], 2),
                                    "graphic_sent_to": line_at["sent_to"], "queued": chain_id in self.queue,
                                    "result": asdict(result)})
        except Exception as exc:
            self._fan_out(game_id, {"type": "agent-error", "chain_id": chain_id, "error": str(exc)[:200]})

    async def kickoff(self, ledger, start_action: int | None) -> dict:
        game_id = int(ledger.game_id)
        if game_id in self.running and not self.running[game_id].done():
            return {"status": "already running", "transport": self.transport}
        actions = ledger.actions.sort_values(["period_id", "action_id"])
        decisive = {m.shot_action_id for m in ledger.moments}
        if start_action is None:
            start_action = max(0, min(decisive) - LEAD_ACTIONS) if decisive else 0
        actions = actions[actions.action_id >= start_action]
        self.backlog[game_id].clear()

        async def play() -> None:
            await self._publish({"kind": "control", "type": "kickoff", "game_id": game_id,
                                 "transport": self.transport, "actions": int(len(actions))})
            for row in actions.itertuples(index=False):
                payload: dict[str, Any] = {
                    "game_id": game_id, "action_id": int(row.action_id), "period": int(row.period_id),
                    "clock_s": float(row.time_seconds), "team_id": row.team_id, "player_id": row.player_id,
                    "type": row.type_name, "result": row.result_name,
                    "x": round(float(row.start_x), 1), "y": round(float(row.start_y), 1),
                    "decisive": int(row.action_id) in decisive, "published_at": time.time(),
                }
                await self._publish(payload)
                await asyncio.sleep(INTERVAL_S)
            await self._publish({"kind": "control", "type": "full-time", "game_id": game_id})

        self.running[game_id] = asyncio.create_task(play())
        return {"status": "kicked off", "transport": self.transport, "from_action": int(start_action),
                "actions": int(len(actions)), "decisive_moments": sorted(int(d) for d in decisive if d >= start_action)}

    def stop_match(self, game_id: int) -> bool:
        t = self.running.get(game_id)
        if t and not t.done():
            t.cancel()
            return True
        return False

    def subscribe(self, game_id: int) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        for m in self.backlog[game_id]:
            q.put_nowait(m)
        self.subscribers[game_id].add(q)
        return q

    def unsubscribe(self, game_id: int, q: asyncio.Queue) -> None:
        self.subscribers[game_id].discard(q)

    def metrics(self) -> dict:
        def pct(values, p):
            v = sorted(values)
            return round(v[min(len(v) - 1, int(p * len(v)))], 2) if v else None
        return {"transport": self.transport, "goals_processed": len(self.latencies),
                "graphics_hub": self.graphics_name, "graphics_sent": self.graphics_sent,
                "queued_for_producer": sum(i["status"] == "pending" for i in self.queue.values()),
                "decisions_logged": len(self.log),
                "line_p50_s": pct(self.line_latencies, 0.5), "line_p95_s": pct(self.line_latencies, 0.95),
                "p50_s": pct(self.latencies, 0.5), "p95_s": pct(self.latencies, 0.95)}


hub = Hub()
