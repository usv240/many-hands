import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.api.app import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(scope="module")
def first_goal_chain() -> str:
    gid = client.get("/v1/matches").json()[0]["game_id"]
    chains = client.get(f"/v1/matches/{gid}/chains").json()
    return next(c["chain_id"] for c in chains if c["goal"])


def test_health_reports_replay_mode():
    h = client.get("/v1/health").json()
    assert h["status"] == "ok" and h["mode"] == "replay" and h["matches"] >= 1


def test_chain_has_actions_and_responsibility(first_goal_chain):
    c = client.get(f"/v1/chains/{first_goal_chain}").json()
    assert c["actions"] and c["responsibility"]
    assert abs(sum(r["share"] for r in c["responsibility"]) - 1) < 0.01


def test_audit_unfair_then_fair_rewrite(first_goal_chain):
    c = client.get(f"/v1/chains/{first_goal_chain}").json()
    top = c["responsibility"][0]
    # Blame an uninvolved defender by shirt number: must be unfair and come with a fair version.
    roster = client.get(f"/v1/matches/{c['game_id']}/roster").json()
    uninvolved = next(e for e in roster if e["team_id"] == c["conceding_team_id"]
                      and e["player_id"] not in {r["player_id"] for r in c["responsibility"]})
    r = client.post("/v1/audit", json={"chain_id": first_goal_chain,
                                       "text": f"Number {uninvolved['shirt']}'s howler cost them the game."}).json()
    assert r["verdict"] == "unfair" and r["fair_rewrite"]
    # Blaming the main contributor alone, when they hold the lot, is fair.
    r2 = client.post("/v1/audit", json={"chain_id": first_goal_chain,
                                        "text": f"Number {top['shirt']} lost the ball."}).json()
    assert r2["verdict"] in ("fair", "watch")


def test_unknown_chain_is_404():
    assert client.post("/v1/audit", json={"chain_id": "nope", "text": "x"}).status_code == 404


def test_bad_policy_is_422(first_goal_chain):
    r = client.post("/v1/audit", json={"chain_id": first_goal_chain, "text": "x",
                                       "policy": {"watch_above": 0.5, "unfair_above": 0.3}})
    assert r.status_code == 422
