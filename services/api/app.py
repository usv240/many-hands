"""Many Hands API, version 1.

Runs fully offline against the demo data pack (fictional matches), so judges can always hit it.
Model-backed features (writing lines, model-based extraction) are added by the agent service and
fall back to the deterministic versions here when unavailable.

Run locally:
    uv run uvicorn services.api.app:app --reload --port 8000
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages"))

from ledger_core.ledger import MatchLedger  # noqa: E402
from narrative_core.audit import audit  # noqa: E402
from narrative_core.extraction import Roster, RosterEntry  # noqa: E402
from narrative_core.scapegoat import Policy  # noqa: E402

DATA_DIR = Path(os.environ.get("MANYHANDS_DATA", ROOT / "demo_data"))
VERSION = "0.1.0"

app = FastAPI(
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
def audit_line(body: AuditIn) -> dict:
    L = store.ledger_for_chain(body.chain_id)
    m = L.moment(body.chain_id)
    r = L.responsibility(body.chain_id, body.method)
    try:
        policy = Policy(body.policy.watch_above, body.policy.unfair_above)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result = audit(body.text, r.shares, store.roster(int(L.game_id)), m.conceding_team_id,
                   policy, goal=m.goal)
    out = result.to_dict()
    out["chain_id"] = body.chain_id
    out["evidence_named"] = [{"player_id": p, "name": L.name(p), "shirt": L.shirt(p),
                              "share": round(s, 3)} for p, s in
                             sorted(r.shares.items(), key=lambda kv: -kv[1])]
    out["model_versions"] = {"extractor": "rules-0.1", "ledger": "vaep-synthetic-0.1"}
    return native(out)


# ---------------------------------------------------------------------- agents
class BroadcastIn(BaseModel):
    chain_id: str
    text: str | None = Field(None, max_length=2000, description="A line to check and fix. Omit to have the Narrator write one.")
    policy: PolicyIn = PolicyIn()
    featured: str | None = Field(None, description="Player id for the player-focus version")
    simulate_auditor_outage: bool = Field(False, description="Demonstrates fail-closed: nothing airs")


@app.post("/v1/broadcast")
async def broadcast(body: BroadcastIn) -> dict:
    """Run the agent workflow on a moment: write or rewrite the line, audit it, personalise it."""
    from dataclasses import asdict

    from services.agents.workflow import Request, run
    store.ledger_for_chain(body.chain_id)  # 404 for unknown chains before any model call
    result = await run(Request(body.chain_id, body.text, (body.policy.watch_above, body.policy.unfair_above),
                               body.featured, body.simulate_auditor_outage))
    return native(asdict(result))


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
