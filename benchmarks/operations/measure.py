"""Operations benchmark: what it costs and how long it takes to check every goal of a match.

Runs the full agent workflow (Microsoft Agent Framework on Microsoft Foundry, gpt-5-mini) on every
decisive moment in the demo matches, the way the live feed does when a goal arrives, and records:
time to the fair line, time to all five audience versions, model calls, tokens and cost.

Usage:
    uv run python benchmarks/operations/measure.py
"""

from __future__ import annotations

import asyncio
import json
import statistics
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from services.agents import models  # noqa: E402
from services.agents.workflow import Request, run  # noqa: E402
from services.api.app import store  # noqa: E402

HERE = Path(__file__).resolve().parent
MATCHES_PER_SEASON = 380


def pct(values: list[float], p: float) -> float:
    v = sorted(values)
    return round(v[min(len(v) - 1, int(p * len(v)))], 2)


async def main() -> None:
    if not models.available():
        sys.exit("Needs the agents on Microsoft Foundry (azd up, azd auth login).")
    rows = []
    for gid, L in store.ledgers.items():
        for m in L.moments:
            cid = L.chain_id(m)
            t0 = asyncio.get_running_loop().time()
            r = await run(Request(cid))
            total = asyncio.get_running_loop().time() - t0
            rows.append({"game_id": gid, "chain_id": cid, "status": r.status, "verdict": r.audit and r.audit["verdict"],
                         "line_ready_s": r.line_ready_s, "all_versions_s": round(total, 2), **(r.usage or {})})
            print(f"{cid:12} line {r.line_ready_s}s all {total:.1f}s cost ${r.usage['cost_usd']:.5f}", flush=True)
    per_match: dict[int, float] = {}
    for row in rows:
        per_match[row["game_id"]] = per_match.get(row["game_id"], 0.0) + row["cost_usd"]
    goals_per_match = statistics.mean(sum(1 for r in rows if r["game_id"] == g) for g in per_match)
    cost_per_goal = statistics.mean(r["cost_usd"] for r in rows)
    out = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"), "model": models.model_name(),
        "price_per_million_tokens_usd": models.PRICE_PER_M,
        "moments": len(rows), "matches": len(per_match), "all_ready": sum(r["status"] == "ready" for r in rows),
        "line_ready_s": {"p50": pct([r["line_ready_s"] for r in rows if r["line_ready_s"]], 0.5),
                         "p95": pct([r["line_ready_s"] for r in rows if r["line_ready_s"]], 0.95)},
        "all_versions_s": {"p50": pct([r["all_versions_s"] for r in rows], 0.5),
                           "p95": pct([r["all_versions_s"] for r in rows], 0.95)},
        "model_calls_per_goal": round(statistics.mean(r["calls"] for r in rows), 1),
        "tokens_per_goal": round(statistics.mean(r["input_tokens"] + r["output_tokens"] for r in rows)),
        "cost_per_goal_usd": round(cost_per_goal, 5),
        "cost_per_match_usd": round(statistics.mean(per_match.values()), 4),
        "decisive_moments_per_match": round(goals_per_match, 1),
        "cost_per_season_usd": round(statistics.mean(per_match.values()) * MATCHES_PER_SEASON, 2),
        "note": "Agent time only, measured from this machine to Foundry in East US 2. The live feed adds Event Hubs transit, measured separately by /v1/metrics.",
        "rows": rows,
    }
    (HERE / "results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
