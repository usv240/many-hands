"""The Auditor's reader: gpt-5-mini finds implied blame that word rules miss.

The red team showed the rule-based extraction catches explicit blame ("howler", "cost them") but
misses implication ("standing a yard off", "never really engages"). This reader closes that gap
while keeping the guarantees that matter:

  - every mention must quote words that really are in the line (checked in code, else dropped);
  - the Scapegoat Index is still computed in code from the merged mentions, never by a model;
  - the rules stay as a floor: a model can add blame the rules missed, but cannot remove any.
"""

from __future__ import annotations

import asyncio
import json

from narrative_core.extraction import Extraction, Mention, Roster, RuleExtractor

from services.agents import models

RETRY_AFTER_S = 1.5

READER = (
    "Read the commentary in its original language, including Spanish. Quote spans in that language, "
    "never translate the quoted evidence. Report which DEFENDING players it blames for the goal "
    "or chance, including implied blame: tone, emphasis, implication or criticism of positioning, effort "
    "or decisions. Do not count neutral description or credit. For each blamed player give the shirt "
    "number, the exact words in the line that refer to them (span), and strength: 1 mild criticism, "
    "2 clear blame, 3 the line makes them the cause. Quote words exactly. Reply with JSON only: "
    '{"blamed": [{"shirt": 5, "span": "...", "strength": 2}]}'
)


def _team_text(roster: Roster, team_id: str) -> str:
    return "Defending players: " + "; ".join(
        f"number {e.shirt} {e.name} ({e.role})" for e in roster.team(team_id))


async def model_mentions(text: str, roster: Roster, team_id: str) -> list[Mention]:
    raw = await models.ask(models.agent("AuditorReader", READER), f"{_team_text(roster, team_id)}\nLine: {text}")
    data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
    low = text.lower()
    out: list[Mention] = []
    for b in data.get("blamed", []):
        entry = roster.by_shirt(team_id, int(b.get("shirt", -1)))
        span = str(b.get("span", "")).strip()
        if entry is None or not span or span.lower() not in low:
            continue  # an invented mention is dropped, never trusted
        out.append(Mention(player_id=entry.player_id, span=span, polarity="blame",
                           strength=max(1, min(3, int(b.get("strength", 1))))))
    return out


def merge(rules: Extraction, extra: list[Mention]) -> Extraction:
    """One mention per player, at the stronger of the two readings. Group mentions are kept as they are."""
    best: dict[str, Mention] = {}
    groups = []
    for m in [*rules.mentions, *extra]:
        if m.group or not m.player_id:
            groups.append(m)
        elif m.polarity == "blame" and (m.player_id not in best or m.strength > best[m.player_id].strength):
            best[m.player_id] = m
    credit = [m for m in rules.mentions if m.polarity == "credit" and m.player_id not in best]
    return Extraction(text=rules.text, mentions=[*best.values(), *groups, *credit], unresolved=rules.unresolved)


async def deep_extract(text: str, roster: Roster, team_id: str, *, required: bool = False) -> tuple[Extraction, bool]:
    """Rules plus the model reader. Returns (extraction, model_was_used)."""
    rules = RuleExtractor(roster, team_id).extract(text)
    if not models.available():
        return rules, False
    try:
        extra = await model_mentions(text, roster, team_id)
    except Exception as exc:
        if not required:
            return rules, False
        await asyncio.sleep(RETRY_AFTER_S)  # one retry: a passing throttle should not hold a line
        try:
            extra = await model_mentions(text, roster, team_id)
        except Exception:
            raise RuntimeError("model fairness reader unavailable; publication held") from exc
    return merge(rules, extra), True
