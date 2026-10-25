"""Score the Auditor with and without its gpt-5-mini reader on the recorded red-team attacks.

Uses attacks.json from run.py (no new attacks are generated). Reports, for the held-out match and
for all matches: attacks the Judge rated Unfair that the Auditor caught; hard negatives (attacks the
Judge rated Fair) wrongly flagged Unfair; and fair control lines wrongly flagged Unfair.

Caveat, stated in the results: the Judge and the reader are separate agents with different
instructions, but both run on gpt-5-mini. Agreement between them is not independent human labelling.

Usage:
    uv run python benchmarks/redteam/eval_reader.py
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "packages"))

from narrative_core.audit import audit  # noqa: E402

from services.agents.extractor import deep_extract  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from run import HELD_OUT_GAME, UNFAIR, controls, moments  # noqa: E402


async def verdicts(items: list[tuple[str, dict]], sem: asyncio.Semaphore) -> list[tuple[str, str, bool]]:
    async def one(text: str, mo: dict):
        async with sem:
            extraction, used = await deep_extract(text, mo["roster"], mo["conceding"])
        rules = audit(text, mo["shares"], mo["roster"], mo["conceding"], goal=mo["goal"]).verdict
        deep = audit(text, mo["shares"], mo["roster"], mo["conceding"], extraction=extraction, goal=mo["goal"]).verdict
        return rules, deep, used
    return await asyncio.gather(*(one(t, mo) for t, mo in items))


def summary(rows: list[dict]) -> dict:
    unfair = [r for r in rows if r["judge_si"] > UNFAIR]
    fair = [r for r in rows if r["judge_si"] <= 0.20]
    return {
        "judge_unfair": len(unfair),
        "caught_rules": sum(r["rules"] == "unfair" for r in unfair),
        "caught_with_reader": sum(r["deep"] == "unfair" for r in unfair),
        "hard_negatives": len(fair),
        "hard_negatives_unfair_rules": sum(r["rules"] == "unfair" for r in fair),
        "hard_negatives_unfair_with_reader": sum(r["deep"] == "unfair" for r in fair),
    }


async def main() -> None:
    all_m = moments()
    by_id = {m["chain_id"]: m for m in all_m}
    attacks = json.loads((HERE / "attacks.json").read_text(encoding="utf-8"))
    sem = asyncio.Semaphore(8)
    res = await verdicts([(a["text"], by_id[a["chain_id"]]) for a in attacks], sem)
    rows = [{"chain_id": a["chain_id"], "game_id": by_id[a["chain_id"]]["game_id"], "judge_si": a["judge"]["si"],
             "rules": r, "deep": d, "reader_used": u} for a, (r, d, u) in zip(attacks, res, strict=True)]
    ctrl = controls(all_m)
    cres = await verdicts(ctrl, sem)
    out = {
        "reader_calls_succeeded": sum(r["reader_used"] for r in rows),
        "attacks": len(rows),
        "held_out": summary([r for r in rows if r["game_id"] == HELD_OUT_GAME]),
        "all": summary(rows),
        "controls": {"lines": len(ctrl), "unfair_rules": sum(r == "unfair" for r, _, _ in cres),
                     "unfair_with_reader": sum(d == "unfair" for _, d, _ in cres)},
        "caveat": "Judge and reader are separate agents but share the gpt-5-mini model; not human labels.",
    }
    (HERE / "reader_results.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
