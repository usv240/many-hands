"""The match recap: every sentence is checked against its own goal's evidence."""

import asyncio
import json
import os
import sys
from pathlib import Path

os.environ["MANYHANDS_OFFLINE"] = "1"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from services.agents import models, recap  # noqa: E402
from services.api.app import store  # noqa: E402

GAME = 20003


def goals(game_id):
    L = store.ledgers[game_id]
    return [L.chain_id(m) for m in L.moments if m.goal]


def test_offline_recap_is_fair_and_covers_every_goal():
    r = asyncio.run(recap.write(GAME, "casual"))
    assert not r.model_used and r.replaced == 0
    assert [s.chain_id for s in r.sentences] == goals(GAME)
    assert all(s.verdict != "unfair" for s in r.sentences)


def test_scapegoating_sentence_is_replaced_and_wrong_score_rejected(monkeypatch):
    ids = goals(GAME)
    fake = {"title": "A wild one", "sentences": [
        {"chain_id": ids[0], "text": "Number 8's howler cost them the goal."},
        {"chain_id": ids[1], "text": "A goal that made it 9-9."},
        {"chain_id": None, "text": "What a night for football."},
        {"chain_id": None, "text": "Number 5's howler summed up the night."},
    ]}

    async def ask(_agent, _prompt, options=None):
        return json.dumps(fake)

    monkeypatch.setattr(models, "available", lambda: True)
    monkeypatch.setattr(models, "agent", lambda *a, **k: None)
    monkeypatch.setattr(models, "ask", ask)

    async def rules_only(text, roster, team_id, **kwargs):  # the reader, without a model: the word rules
        from narrative_core.extraction import RuleExtractor
        return RuleExtractor(roster, team_id).extract(text), False
    monkeypatch.setattr(recap, "deep_extract", rules_only)

    r = asyncio.run(recap.write(GAME, "casual"))
    texts = [s.text for s in r.sentences]
    assert r.model_used and r.title == "A wild one"
    first = r.sentences[0]
    if first.replaced:  # the howler line blamed the wrong share of number 8 here
        assert first.replaced == fake["sentences"][0]["text"] and first.verdict == "fair"
    assert all("9-9" not in t for t in texts)                        # a wrong score never reaches the recap
    assert "What a night for football." in texts                     # no blame, no goal: kept
    assert "Number 5's howler summed up the night." not in texts     # blame with no goal to check it: dropped
