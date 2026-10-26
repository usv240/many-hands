"""The match recap: the whole story of a match, for one audience, checked sentence by sentence.

    Recapper (gpt-5-mini on Microsoft Foundry) -> Auditor, once per sentence -> recap

The Recapper writes a short recap from the ledger's facts, and tags each sentence with the goal it
is about. The Auditor reads every sentence and scores it against that goal's evidence, in code.
A sentence about a goal that scapegoats, or gets the score wrong, is replaced by the fair line for
that goal; a sentence about no goal must blame no one. Nothing the Auditor rejects reaches the recap.
Without the model, the recap is built from the fair template lines, and says so.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field

from narrative_core.audit import audit, fair_rewrite
from narrative_core.scapegoat import Policy, percents

from services.agents import models
from services.agents.extractor import deep_extract

RECAP_TIMEOUT_S = 30  # a recap is ten sentences, not one line
READS_AT_ONCE = 4     # measured: ten-plus parallel reads tripped the deployment's per-minute request limit

AUDIENCES = {
    "casual": "a casual fan: plain words, no statistics, about 90 words",
    "analyst": "an analyst: who contributed and by how much, with minutes, about 110 words",
    "es": "a Spanish-speaking fan: write everything in Spanish (shirt numbers as \"el número 8\"), plain words, about 90 words",
}

RECAPPER_RULES = (
    "You are the Recapper for a football broadcaster. Write a short match recap from the facts only. "
    "Never invent players, numbers or events. Refer to defending players by shirt number only. "
    "Blame must match the responsibility shares of each goal: name one player as the cause only if their share "
    "is 60 percent or more; otherwise share it among the players with 15 percent or more, or describe the move. "
    "Give credit to attackers, including the unsung player when one is listed. Use the scores exactly as given. "
    "Write every score with a hyphen, like 2-1, and use no other dashes. Reply with JSON only: "
    '{"title": "...", "sentences": [{"chain_id": "<the goal this sentence is about, or null>", "text": "..."}]}'
)


@dataclass
class Sentence:
    text: str
    chain_id: str | None
    si: float | None = None
    verdict: str = "fair"
    replaced: str | None = None          # the Recapper's sentence, when the Auditor swapped it out
    reasons: list[str] = field(default_factory=list)


@dataclass
class Recap:
    game_id: int
    audience: str
    title: str
    sentences: list[Sentence]
    model_used: bool
    model: str
    replaced: int
    seconds: float
    usage: dict | None = None
    note: str | None = None              # why the recap was built from the fair lines, when it was


def _facts(store, game_id: int) -> tuple[dict, dict]:
    """Every goal of the match, in order, with its evidence. Also the shares by chain, for the Auditor."""
    from services.agents.workflow import _label, _score_after
    L = store.ledgers[game_id]
    roster = store.roster(game_id)
    names = store.roster_df.drop_duplicates("team_id").set_index("team_id")["team"].to_dict()
    g = store.games[store.games.game_id == game_id].iloc[0]
    goals, shares = [], {}
    for m in L.moments:
        if not m.goal:
            continue
        cid = L.chain_id(m)
        s = L.moment_summary(cid)
        shares[cid] = (L.responsibility(cid).shares, s["conceding_team_id"], _score_after(L, cid, names))
        goals.append({
            "chain_id": cid, "minute": s["minute"], "scorer": L.name(s["shooter_id"]),
            "scoring_team": names[s["attacking_team_id"]], "conceding_team": names[s["conceding_team_id"]],
            "score_after": shares[cid][2]["text"],
            "contributors": [{"who": _label(roster, r["player_id"]), "share_pct": percents(shares[cid][0]).get(r["player_id"], 0),
                              "what": r["reason"]} for r in s["responsibility"]],
            "unsung": None if not s["unsung"] else {"who": s["unsung"]["name"], "what": s["unsung"]["reason"]},
        })
    facts = {"home": names[g.home_team_id], "away": names[g.away_team_id],
             "final_score": f"{names[g.home_team_id]} {int(g.home_score)} {names[g.away_team_id]} {int(g.away_score)}",
             "goals": goals}
    return facts, shares


def _template(store, game_id: int, facts: dict, shares: dict, audience: str) -> tuple[str, list[Sentence]]:
    roster = store.roster(game_id)
    out = []
    for gl in facts["goals"]:
        ev, _team, _score = shares[gl["chain_id"]]
        out.append(Sentence(f"{gl['minute']}': {fair_rewrite(ev, roster, True)} {gl['scorer']} scored; "
                            f"{gl['score_after']}.", gl["chain_id"]))
    title = facts["final_score"]
    return title, out


async def write(game_id: int, audience: str = "casual", policy: tuple[float, float] = (0.20, 0.40)) -> Recap:
    from services.agents.workflow import SCORELINE, _fact_errors
    from services.api.app import store
    if game_id not in store.ledgers:
        raise KeyError(game_id)
    if audience not in AUDIENCES:
        raise ValueError(f"audience must be one of {', '.join(AUDIENCES)}")
    t0 = time.perf_counter()
    tally = models.start_usage()
    facts, shares = _facts(store, game_id)
    roster = store.roster(game_id)
    title, sentences, used, note = None, None, False, None
    if models.available():
        for attempt in range(2):  # one retry: a passing throttle should not cost the reader their recap
            try:
                raw = await models.ask(models.agent("Recapper", RECAPPER_RULES),
                                       f"Audience: {AUDIENCES[audience]}\nFacts: {json.dumps(facts, ensure_ascii=False)}",
                                       timeout=RECAP_TIMEOUT_S)
                data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                title = models.clean(str(data["title"]))
                sentences = [Sentence(models.clean(str(s["text"])),
                                      s.get("chain_id") if s.get("chain_id") in shares else None)
                             for s in data["sentences"] if str(s.get("text", "")).strip()]
                used = bool(sentences)
                break
            except Exception as exc:  # noqa: BLE001  the template recap below is fair by construction
                note = f"The Recapper could not answer ({type(exc).__name__}), so the recap is built from the fair lines."
                if attempt == 0:
                    await asyncio.sleep(1.5)
    else:
        note = f"The recap is built from the fair lines ({models.offline_reason()})."
    if not sentences:
        title, sentences = _template(store, game_id, facts, shares, audience)
    else:
        note = None

    # The Auditor: every sentence, in parallel, against the evidence of the goal it is about. A sentence
    # about no goal is read for blame of either team's players, since there is no evidence to weigh it by.
    g = store.games[store.games.game_id == game_id].iloc[0]
    both = [g.home_team_id, g.away_team_id]
    gate = asyncio.Semaphore(READS_AT_ONCE)

    async def one(text: str, team: str):
        async with gate:
            return await deep_extract(text, roster, team, required=used)

    async def read(s: Sentence):
        teams = [shares[s.chain_id][1]] if s.chain_id else both
        readings = await asyncio.gather(*(one(s.text, t) for t in teams))
        return next((r for r in readings if r[0].blame()), readings[0])  # any blame found, else the first

    reads = await asyncio.gather(*(read(s) for s in sentences), return_exceptions=True)
    real_scores = [sorted(score["goals"]) for _ev, _team, score in shares.values()]
    final = []
    for s, reading in zip(sentences, reads, strict=True):
        if isinstance(reading, BaseException):  # the check could not run on this sentence: it does not air
            if s.chain_id:
                ev, _team, _score = shares[s.chain_id]
                final.append(Sentence(fair_rewrite(ev, roster, True), s.chain_id, 0.0, "fair", s.text,
                                      ["The check could not read this sentence, so the fair line replaced it."]))
            continue
        extraction, _ = reading
        if s.chain_id:
            ev, team, score = shares[s.chain_id]
            res = audit(s.text, ev, roster, team, Policy(*policy), extraction=extraction, goal=True)
            errors = _fact_errors(s.text, {"score_after": score})
            if res.verdict == "unfair" or errors:
                fixed = fair_rewrite(ev, roster, True)
                final.append(Sentence(fixed, s.chain_id, 0.0, "fair", s.text, errors + res.reasons))
            else:
                final.append(Sentence(s.text, s.chain_id, res.si, res.verdict))
        elif extraction.blame():  # blame with no goal to check it against: dropped
            continue
        elif any(sorted(map(int, pair)) not in real_scores for pair in SCORELINE.findall(s.text)):
            continue                     # a score that never happened in this match: dropped
        else:
            final.append(Sentence(s.text, None, 0.0, "fair"))
    return Recap(game_id, audience, title or facts["final_score"], final, used, models.model_name(),
                 sum(s.replaced is not None for s in final), round(time.perf_counter() - t0, 2),
                 {**tally, "cost_usd": round(models.usage_cost(tally), 6)}, note)


def to_dict(r: Recap) -> dict:
    return asdict(r)
