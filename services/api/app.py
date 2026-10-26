"""Many Hands API, version 1.

Runs fully offline against the demo data pack (fictional matches), so judges can always hit it.
Model-backed features (writing lines, model-based extraction) are added by the agent service and
fall back to the deterministic versions here when unavailable.

Run locally:
    uv run uvicorn services.api.app:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from ledger_core.ledger import MatchLedger  # noqa: E402
from narrative_core.audit import audit  # noqa: E402
from narrative_core.extraction import Roster, RosterEntry  # noqa: E402
from narrative_core.scapegoat import Policy  # noqa: E402
from starlette.requests import Request as FastRequest  # noqa: E402  (the agents' Request is a different class)

from services.api.guard import client_id, limit, limits  # noqa: E402

DATA_DIR = Path(os.environ.get("MANYHANDS_DATA", ROOT / "demo_data"))
VERSION = "0.1.0"

@asynccontextmanager
async def lifespan(_app: FastAPI):
    from services.api.live import hub
    await hub.start()
    yield
    await hub.stop()


app = FastAPI(
    lifespan=lifespan,
    title="Many Hands API",
    version=VERSION,
    description=(
        "Traces every goal to everyone who caused it, scores any sentence for scapegoating, "
        "and suggests a fair rewrite. All match data here is synthetic and fictional."
    ),
)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def native(obj):
    """Convert numpy scalars inside dicts and lists to plain Python for JSON responses."""
    if isinstance(obj, dict):
        return {k: native(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [native(v) for v in obj]
    if hasattr(obj, "item") and not isinstance(obj, (str, bytes)):
        try:
            return obj.item()
        except (ValueError, TypeError):
            return obj
    return obj


# ---------------------------------------------------------------------- data
class Store:
    def __init__(self, data_dir: Path) -> None:
        self.games = pd.read_parquet(data_dir / "games.parquet")
        actions = pd.read_parquet(data_dir / "actions_rated.parquet")
        positions = pd.read_parquet(data_dir / "positions.parquet")
        self.roster_df = pd.read_parquet(data_dir / "roster.parquet")
        self.ledgers: dict[int, MatchLedger] = {}
        for gid in self.games.game_id:
            self.ledgers[int(gid)] = MatchLedger(
                int(gid), actions[actions.game_id == gid], positions[positions.game_id == gid],
                self.roster_df)
        self.chain_index = {cid: gid for gid, L in self.ledgers.items()
                            for cid in (L.chain_id(m) for m in L.moments)}

    def roster(self, game_id: int) -> Roster:
        g = self.games[self.games.game_id == game_id].iloc[0]
        rows = self.roster_df[self.roster_df.team_id.isin([g.home_team_id, g.away_team_id])]
        return Roster([RosterEntry(r.player_id, r.name, int(r.shirt), r.team_id, r.role)
                       for r in rows.itertuples()])

    def ledger_for_chain(self, chain_id: str) -> MatchLedger:
        try:
            return self.ledgers[self.chain_index[chain_id]]
        except KeyError as exc:
            raise HTTPException(404, f"unknown chain {chain_id}") from exc


store = Store(DATA_DIR)


# ---------------------------------------------------------------------- schemas
class PolicyIn(BaseModel):
    watch_above: float = Field(0.20, ge=0, le=1)
    unfair_above: float = Field(0.40, ge=0, le=1)


class AuditIn(BaseModel):
    chain_id: str = Field(description="A decisive moment, from GET /v1/matches/{id}/chains")
    text: str = Field(min_length=1, max_length=2000, description="The line to check")
    policy: PolicyIn = PolicyIn()
    method: str = Field("combined", pattern="^(combined|vaep|lasttouch)$")
    deep: bool = Field(False, description="Also read the line with gpt-5-mini for implied blame. "
                       "The score is still computed in code. Rules alone miss most implied blame.")


# ---------------------------------------------------------------------- routes
def _writer() -> str:
    from services.agents import models
    return f"{models.model_name()} on Microsoft Foundry" if models.available() else "template"


@app.get("/v1/health")
def health() -> dict:
    return {"status": "ok", "version": VERSION, "mode": "replay", "matches": len(store.ledgers),
            "models": {"extractor": "rules", "writer": _writer()}}


@app.get("/v1/matches")
def matches() -> list[dict]:
    names = store.roster_df.drop_duplicates("team_id").set_index("team_id")["team"].to_dict()
    out = []
    for g in store.games.itertuples():
        L = store.ledgers[int(g.game_id)]
        out.append({"game_id": int(g.game_id), "home": {"team_id": g.home_team_id, "name": names[g.home_team_id]},
                    "away": {"team_id": g.away_team_id, "name": names[g.away_team_id]},
                    "score": [int(g.home_score), int(g.away_score)],
                    "decisive_moments": len(L.moments), "goals": sum(m.goal for m in L.moments)})
    return out


@app.get("/v1/matches/{game_id}/chains")
def chains(game_id: int) -> list[dict]:
    L = store.ledgers.get(game_id)
    if L is None:
        raise HTTPException(404, f"unknown match {game_id}")
    return native([L.moment_summary(L.chain_id(m)) for m in L.moments])


@app.get("/v1/matches/{game_id}/roster")
def roster(game_id: int) -> list[dict]:
    if game_id not in store.ledgers:
        raise HTTPException(404, f"unknown match {game_id}")
    return native([e.__dict__ for e in store.roster(game_id).entries])


@app.get("/v1/chains/{chain_id}")
def chain(chain_id: str) -> dict:
    L = store.ledger_for_chain(chain_id)
    c = L.chain(chain_id)
    cols = ["action_id", "period_id", "time_seconds", "team_id", "player_id", "type_name",
            "result_name", "start_x", "start_y", "end_x", "end_y", "vaep_value", "offensive_value",
            "defensive_value"]
    summary = L.moment_summary(chain_id)
    summary["actions"] = json.loads(c[cols].to_json(orient="records"))
    return native(summary)


@app.get("/v1/chains/{chain_id}/responsibility")
def responsibility(chain_id: str, method: str = "combined") -> dict:
    L = store.ledger_for_chain(chain_id)
    r = L.responsibility(chain_id, method)
    return native({"chain_id": chain_id, "method": method, "conceding_team_id": r.conceding_team_id,
                   "shares": r.shares, "contributors": [c.__dict__ for c in r.contributors],
                   "last_touch": r.last_touch[:1]})


@app.get("/v1/chains/{chain_id}/counterfactual")
def counterfactual(chain_id: str, action_id: int) -> dict:
    return native(store.ledger_for_chain(chain_id).counterfactual(chain_id, action_id))


@app.post("/v1/audit")
async def audit_line(body: AuditIn, request: FastRequest) -> dict:
    L = store.ledger_for_chain(body.chain_id)
    m = L.moment(body.chain_id)
    r = L.responsibility(body.chain_id, body.method)
    try:
        policy = Policy(body.policy.watch_above, body.policy.unfair_above)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    roster = store.roster(int(L.game_id))
    extraction, read_by_model = None, False
    if body.deep:
        from services.agents import models
        from services.agents.extractor import deep_extract
        limits.check("model", client_id(request))
        models.templates_only(not limits.take_model_run())
        extraction, read_by_model = await deep_extract(body.text, roster, m.conceding_team_id)
    result = audit(body.text, r.shares, roster, m.conceding_team_id, policy, extraction=extraction, goal=m.goal)
    out = result.to_dict()
    out["chain_id"] = body.chain_id
    out["evidence_named"] = [{"player_id": p, "name": L.name(p), "shirt": L.shirt(p),
                              "share": round(s, 3)} for p, s in
                             sorted(r.shares.items(), key=lambda kv: -kv[1])]
    out["model_versions"] = {"extractor": "rules-0.1" + (" + gpt-5-mini reader" if read_by_model else ""),
                             "ledger": "vaep-synthetic-0.1"}
    return native(out)


# ---------------------------------------------------------------------- agents
class BroadcastIn(BaseModel):
    chain_id: str
    text: str | None = Field(None, max_length=2000, description="A line to check and fix. Omit to have the Narrator write one.")
    policy: PolicyIn = PolicyIn()
    featured: str | None = Field(None, description="Player id for the player-focus version")
    simulate_auditor_outage: bool = Field(False, description="Demonstrates fail-closed: nothing airs")


@app.post("/v1/broadcast", dependencies=[Depends(limit("model"))])
async def broadcast(body: BroadcastIn) -> dict:
    """Run the agent workflow on a moment: write or rewrite the line, audit it, personalise it."""
    from dataclasses import asdict

    from services.agents.workflow import Request, run
    store.ledger_for_chain(body.chain_id)  # 404 for unknown chains before any model call
    from services.agents import models
    models.templates_only(not limits.take_model_run())  # over today's budget: the templates, never an error
    result = await run(Request(body.chain_id, body.text, (body.policy.watch_above, body.policy.unfair_above),
                               body.featured, body.simulate_auditor_outage))
    from services.api.speech import voice
    voice.approve_result(result)  # the lines that passed may now be read out
    return native(asdict(result))


class SpeakIn(BaseModel):
    text: str = Field(min_length=1, max_length=400)
    lang: str = Field("en", pattern="^(en|es)$")


@app.post("/v1/speak", dependencies=[Depends(limit("model"))])
async def speak(body: SpeakIn):
    """Read a line aloud with Azure AI Speech. Only lines that passed the fairness check can be spoken."""
    from fastapi.responses import Response

    from services.api.speech import voice
    if not voice.allowed(body.text):
        raise HTTPException(403, "Only lines that passed the fairness check are read on air.")
    try:
        audio = await voice.speak(body.text, body.lang)
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    return Response(audio, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


# ---------------------------------------------------------------------- live feed
SSE_END = chr(10) * 2  # a Server-Sent Events message ends with a blank line


def sse(payload: dict) -> str:
    return "data: " + json.dumps(payload) + SSE_END

@app.post("/v1/matches/{game_id}/kickoff", dependencies=[Depends(limit("kickoff"))])
async def kickoff(game_id: int, start_action: int | None = None, auto_air: bool = True) -> dict:
    """Publish a match to Azure Event Hubs, starting shortly before its next goal. Goals wake the agents."""
    from services.api.live import hub
    L = store.ledgers.get(game_id)
    if L is None:
        raise HTTPException(404, f"unknown match {game_id}")
    from services.api.live import LiveFullError
    try:
        return await hub.kickoff(L, start_action, auto_air)
    except LiveFullError as exc:
        raise HTTPException(429, str(exc), headers={"Retry-After": "60"}) from exc


@app.post("/v1/matches/{game_id}/stop")
def stop(game_id: int) -> dict:
    from services.api.live import hub
    return {"stopped": hub.stop_match(game_id)}


@app.get("/v1/matches/{game_id}/live")
async def live_stream(game_id: int):
    """Server-Sent Events: every event from the hub, and every agent result as it lands."""
    from fastapi.responses import StreamingResponse

    from services.api.live import hub
    if game_id not in store.ledgers:
        raise HTTPException(404, f"unknown match {game_id}")

    async def gen():
        q = hub.subscribe(game_id)
        try:
            yield sse({"type": "hello", "transport": hub.transport})
            while True:
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                    yield sse(native(msg))
                except TimeoutError:
                    yield ": keep-alive" + SSE_END
        finally:
            hub.unsubscribe(game_id, q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/v1/metrics")
def metrics() -> dict:
    """Measured time from a goal reaching Event Hubs to a fair, audited line being ready."""
    from services.api.live import hub
    return {**hub.metrics(), "limits": limits.status()}


class RecapIn(BaseModel):
    audience: str = Field("casual", pattern="^(casual|analyst|es)$", description="casual, analyst, or es (Spanish)")
    policy: PolicyIn = PolicyIn()


@app.post("/v1/matches/{game_id}/recap", dependencies=[Depends(limit("model"))])
async def match_recap(game_id: int, body: RecapIn) -> dict:
    """The whole match as a short recap for one audience. Every sentence is checked against its goal's evidence."""
    from services.agents import models, recap
    if game_id not in store.ledgers:
        raise HTTPException(404, f"unknown match {game_id}")
    models.templates_only(not limits.take_model_run())
    return native(recap.to_dict(await recap.write(game_id, body.audience,
                                                  (body.policy.watch_above, body.policy.unfair_above))))


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    reason: str = Field("", max_length=500, description="Required to approve: the line did not pass the check")
    producer: str = Field("producer", min_length=1, max_length=60)
    evidence: str | None = Field(None, pattern="^(confirmed|rejected|unclear)$",
                                 description="The producer's answer to the Investigator's evidence question")


@app.get("/v1/queue")
def queue() -> list[dict]:
    """Live lines the check did not pass as Fair. They wait here for a producer; nothing airs until one decides."""
    from services.api.live import hub
    return native(sorted(hub.queue.values(), key=lambda i: -i["queued_at"]))


@app.post("/v1/queue/{chain_id}/decision")
async def decide(chain_id: str, body: DecisionIn) -> dict:
    from services.api.live import hub
    try:
        return native(await hub.decide(chain_id, body.decision, body.reason, body.producer, body.evidence))
    except KeyError as exc:
        raise HTTPException(404, f"nothing queued for {chain_id}") from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.get("/v1/log")
def decision_log() -> dict:
    """Every live decision (aired by policy, approved, rejected, held), hash-chained, with a verification."""
    from services.api.live import hub
    return native({"verify": hub.verify_log(), "entries": hub.log[-200:]})


# ---------------------------------------------------------------------- website
# In the container the built site sits next to the API, so one address serves both.
WEB_DIST = ROOT / "apps" / "web" / "dist"
if WEB_DIST.exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="assets")
    app.mount("/data", StaticFiles(directory=WEB_DIST / "data"), name="data")

    @app.get("/{path:path}", include_in_schema=False)
    def site(path: str) -> FileResponse:
        target = (WEB_DIST / path).resolve()
        if path and target.is_file() and WEB_DIST.resolve() in target.parents:
            return FileResponse(target)
        return FileResponse(WEB_DIST / "index.html")  # client-side routes
