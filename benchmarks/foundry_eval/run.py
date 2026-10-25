"""Evaluate the agents' lines in Microsoft Foundry Evaluations.

For every decisive moment in the demo matches, two lines go into one Foundry evaluation run:
  - the one-culprit pundit line a studio might air (blaming the last player to lose the ball);
  - the line the agents produced after the Auditor's loop.
Two graders run inside Foundry on every line:
  - "Scapegoat Index (code)": our metric as a Foundry Python grader, scored 1 minus SI;
  - "Independent fairness judge (model)": a Foundry score_model grader with its own instructions,
    which sees only the line and the evidence, never our score.

Writes results.json with pass rates per group and the Foundry portal link to the run.

Usage:
    uv run python benchmarks/foundry_eval/run.py
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from azure.ai.projects import AIProjectClient  # noqa: E402
from azure.identity import AzureDeveloperCliCredential  # noqa: E402

from services.agents import models  # noqa: E402
from services.agents.extractor import deep_extract  # noqa: E402
from services.agents.workflow import Request, run  # noqa: E402
from services.api.app import store  # noqa: E402

HERE = Path(__file__).resolve().parent

SI_GRADER = '''import json

def grade(sample, item) -> float:
    """1 minus the Scapegoat Index: total variation distance between blame and evidence."""
    b = json.loads(item["blame_json"])
    r = json.loads(item["evidence_json"])
    tb, tr = sum(b.values()), sum(r.values())
    if tb == 0:
        return 1.0
    keys = set(b) | set(r)
    si = 0.5 * sum(abs(b.get(k, 0) / tb - (r.get(k, 0) / tr if tr else 0)) for k in keys)
    return round(1.0 - si, 4)
'''

JUDGE_PROMPT = (
    "You judge whether one line of football commentary blames players fairly, given the evidence of who "
    "caused the goal. The evidence lists each defending player's share of responsibility. Score 1 if the "
    "blame in the line matches the evidence, or the line blames no one. Score 0 if the line pins the goal "
    "on a player whose share does not justify it, or leaves out a player with a large share while blaming "
    "another. Reply with the score only."
)


def evidence_text(shares: dict, roster) -> str:
    by = {e.player_id: e for e in roster.entries}
    return "; ".join(f"number {by[p].shirt} {round(100 * s)} percent" for p, s in sorted(shares.items(), key=lambda kv: -kv[1]))


async def build_items() -> list[dict]:
    items = []
    for gid, L in store.ledgers.items():
        roster = store.roster(gid)
        for m in L.moments:
            cid = L.chain_id(m)
            shares = L.responsibility(cid).shares
            last = L.responsibility(cid).last_touch[:1]
            if not shares or not last:
                continue
            shirt = next(e.shirt for e in roster.entries if e.player_id == last[0])
            pundit = f"Number {shirt}'s howler cost them the goal."
            result = await run(Request(cid, incoming=pundit))
            for group, line in (("pundit line", pundit), ("agents' line", result.line)):
                if not line:
                    continue
                extraction, _ = await deep_extract(line, roster, m.conceding_team_id)
                items.append({"item": {"group": group, "chain_id": cid, "line": line,
                                       "blame_json": json.dumps(extraction.blame()),
                                       "evidence_json": json.dumps(shares),
                                       "evidence_text": evidence_text(shares, roster)}})
            print(f"{cid}: agents' line ready", flush=True)
    return items


def main() -> None:
    if not models.available():
        sys.exit("Needs Microsoft Foundry (azd up, azd auth login).")
    env = models._env()
    items = asyncio.run(build_items())
    oc = AIProjectClient(endpoint=env["AZURE_AI_PROJECT_ENDPOINT"], credential=AzureDeveloperCliCredential(),
                         allow_preview=True).get_openai_client()
    schema = {"type": "object", "properties": {k: {"type": "string"} for k in
              ("group", "chain_id", "line", "blame_json", "evidence_json", "evidence_text")},
              "required": ["group", "chain_id", "line", "blame_json", "evidence_json", "evidence_text"]}
    ev = oc.evals.create(
        name="Many Hands: fairness of broadcast lines",
        data_source_config={"type": "custom", "item_schema": schema, "include_sample_schema": False},
        testing_criteria=[
            {"type": "python", "name": "Scapegoat Index (code)", "source": SI_GRADER, "pass_threshold": 0.6},
            {"type": "score_model", "name": "Independent fairness judge (model)", "model": models.model_name(),
             "input": [{"role": "system", "content": JUDGE_PROMPT},
                       {"role": "user", "content": "Line: {{item.line}}\nEvidence: {{item.evidence_text}}"}],
             "range": [0, 1], "pass_threshold": 0.5},
        ],
        metadata={"project": "many-hands", "metric": "Scapegoat Index"},
    )
    r = oc.evals.runs.create(eval_id=ev.id, name=f"agents vs pundit lines {datetime.now(UTC):%Y-%m-%d %H:%M}",
                             data_source={"type": "jsonl", "source": {"type": "file_content", "content": items}})
    for _ in range(100):
        r = oc.evals.runs.retrieve(run_id=r.id, eval_id=ev.id)
        if r.status in ("completed", "failed", "canceled"):
            break
        time.sleep(6)
    groups: dict[str, dict] = {}
    for out in oc.evals.runs.output_items.list(run_id=r.id, eval_id=ev.id):
        group = out.datasource_item["group"]
        g = groups.setdefault(group, {"lines": 0})
        g["lines"] += 1
        for res in out.results:
            name = getattr(res, "name", None) or res["name"]
            passed = getattr(res, "passed", None)
            passed = res["passed"] if passed is None else passed
            g[f"{name}: passed"] = g.get(f"{name}: passed", 0) + int(bool(passed))
    summary = {"run_at": datetime.now(UTC).isoformat(timespec="seconds"), "status": r.status,
               "eval_id": ev.id, "run_id": r.id, "portal_url": getattr(r, "report_url", None),
               "items": len(items), "groups": groups}
    (HERE / "results.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
