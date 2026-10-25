"""Every red-team attack is a permanent test.

Offline (every commit): each attack's recorded, code-verified reading must still score Unfair, so
the scoring path can never quietly start letting scapegoating through.
Live (MANYHANDS_LIVE=1, needs Azure): the Auditor's gpt-5-mini reader must still catch at least
90 percent of the attacks (measured: 77 to 79 of 83), and the rules alone must still be measured honestly.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from narrative_core.audit import audit  # noqa: E402
from narrative_core.extraction import Extraction, Mention  # noqa: E402

from services.api.app import store  # noqa: E402

CASES = json.loads((ROOT / "benchmarks" / "redteam" / "cases.json").read_text(encoding="utf-8"))


def context(chain_id: str):
    L = store.ledger_for_chain(chain_id)
    m = L.moment(chain_id)
    return L.responsibility(chain_id).shares, store.roster(int(L.game_id)), m.conceding_team_id, m.goal


@pytest.mark.parametrize("case", CASES["must_be_unfair"], ids=lambda c: c["text"][:50])
def test_recorded_attack_scores_unfair(case):
    shares, roster, team, goal = context(case["chain_id"])
    mentions = [Mention(player_id=m["player_id"], span=m["span"], strength=m["strength"], polarity="blame")
                for m in case["judge_mentions"]]
    result = audit(case["text"], shares, roster, team, extraction=Extraction(text=case["text"], mentions=mentions),
                   goal=goal)
    assert result.verdict == "unfair"


@pytest.mark.skipif(os.environ.get("MANYHANDS_LIVE") != "1", reason="needs the agents on Microsoft Foundry")
def test_live_reader_still_catches_the_attacks():
    from services.agents.extractor import deep_extract

    async def caught(case):
        shares, roster, team, goal = context(case["chain_id"])
        extraction, _ = await deep_extract(case["text"], roster, team)
        return audit(case["text"], shares, roster, team, extraction=extraction, goal=goal).verdict == "unfair"

    async def run():
        return await asyncio.gather(*(caught(c) for c in CASES["must_be_unfair"]))

    hits = asyncio.run(run())
    assert sum(hits) / len(hits) >= 0.90  # measured 77 to 79 of 83 across runs; the model varies
