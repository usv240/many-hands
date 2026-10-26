"""The Many Hands agent workflow, on Microsoft Agent Framework.

    Investigator -> Narrator <-> Auditor -> Personalizer -> output
                                  |
                                  +-> (Auditor fails) held: nothing airs

Investigator  gathers the evidence with the ledger tools (the same ones the MCP server exposes).
Narrator      writes the line, or rewrites a line it was handed, with gpt-5-mini on Microsoft Foundry.
Auditor       scores the line in code. A model never decides the score, so text that tries to
              instruct a model cannot change it. Unfair lines go back with reasons, at most twice;
              after that a template that is fair by construction is used.
Personalizer  writes audience versions and a translation with gpt-5-mini; each is audited again.

Every model step has a deterministic fallback, and every step is recorded in the trace.
"""

from __future__ import annotations

import asyncio
import json
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from narrative_core.audit import JUSTIFIED_SHARE, audit, fair_rewrite
from narrative_core.scapegoat import Policy, percents

from services.agents import models
from services.agents.extractor import deep_extract

MAX_REVISIONS = 2


# ---------------------------------------------------------------------------------- messages
@dataclass
class Step:
    agent: str
    action: str
    ms: int
    detail: str = ""
    model: bool = False


@dataclass
class Request:
    chain_id: str
    incoming: str | None = None          # a line someone wants to air; None means write one
    policy: tuple[float, float] = (0.20, 0.40)
    featured: str | None = None
    simulate_auditor_outage: bool = False
    # Called with (line, audit) the moment the Auditor approves the main line, before the audience
    # versions are written, so a live graphic does not wait for them.
    on_line: Callable[[str, dict, dict | None], Awaitable[None]] | None = None


@dataclass
class Evidence:
    request: Request
    facts: dict[str, Any]
    shares: dict[str, float]
    trace: list[Step] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)
    line_ready_s: float | None = None  # when the fair line was approved: what the lower third needs
    check: dict | None = None          # the one action a producer should look at before this airs


@dataclass
class Draft:
    evidence: Evidence
    text: str
    source: str                          # incoming, narrator, narrator-rewrite, template
    revisions: int = 0
    history: list[dict] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)


@dataclass
class Approved:
    draft: Draft
    audit: dict


@dataclass
class Result:
    status: str                          # aired-ready, held
    line: str | None
    audit: dict | None
    source: str | None
    revisions: int
    history: list[dict]
    variants: list[dict]
    trace: list[dict]
    model: str
    model_used: bool
    held_reason: str | None = None
    line_ready_s: float | None = None
    usage: dict | None = None
    check: dict | None = None


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


def _si(si: float) -> str:
    """Two decimals exactly as the browser's toFixed(2) shows them (half up on the stored binary value),
    so the trace and the badge always agree: 0.475 is 0.47 in both."""
    return str(Decimal(si).quantize(Decimal("0.01"), ROUND_HALF_UP))


# ---------------------------------------------------------------------------------- context
def _store():
    from services.api.app import store
    return store


def _label(roster, pid: str) -> str:
    e = next((x for x in roster.entries if x.player_id == pid), None)
    return f"number {e.shirt} ({e.name})" if e else pid


# ---------------------------------------------------------------------------------- executors
class Investigator(Executor):
    @handler
    async def investigate(self, req: Request, ctx: WorkflowContext[Evidence | Draft]) -> None:
        t0 = time.perf_counter()
        store = _store()
        L = store.ledger_for_chain(req.chain_id)
        summary = L.moment_summary(req.chain_id)
        roster = store.roster(int(L.game_id))
        shares = L.responsibility(req.chain_id).shares
        pcs = percents(shares)  # the same whole percentages the Studio shows
        names = store.roster_df.drop_duplicates("team_id").set_index("team_id")["team"].to_dict()
        score = _score_after(L, req.chain_id, names)
        facts = {
            "minute": summary["minute"], "goal": summary["goal"],
            "attacking_team": names[summary["attacking_team_id"]],
            "conceding_team": names[summary["conceding_team_id"]],
            "conceding_team_id": summary["conceding_team_id"],
            "game_id": int(L.game_id),
            "names": [e.name for e in roster.entries] + list(names.values()),  # for the spelling check
            "shooter": L.name(summary["shooter_id"]),
            "score_after": score,
            "actions": summary["n_actions"],
            "contributors": [{"who": _label(roster, r["player_id"]), "share_pct": pcs.get(r["player_id"], 0),
                              "what": r["reason"]} for r in summary["responsibility"]],
            "unsung": None if not summary["unsung"] else
                      {"who": summary["unsung"]["name"], "what": summary["unsung"]["reason"]},
        }
        ev = Evidence(req, facts, shares)
        ev.check = deciding_check(L, req.chain_id, shares, roster)
        ev.trace.append(Step("Investigator", "gathered evidence with the ledger tools", _ms(t0),
                             f"{summary['n_actions']} actions; {len(shares)} defending player(s) lost the ball"))
        if req.incoming:
            await ctx.send_message(Draft(ev, req.incoming, "incoming"))
        else:
            await ctx.send_message(ev)


NARRATOR_RULES = (
    "You are the Narrator for a live football broadcast. Write ONE line for an on-screen graphic, "
    "at most 25 words, from the facts only. Never invent players, numbers or events. Refer to "
    "defending players by shirt number only (\"number 8\"), never with their name in brackets. Blame must match the responsibility shares: name a single "
    "player as the cause only if their share is 60 percent or more; otherwise share it among the "
    "players with 15 percent or more, or describe the move without blame. If you mention the score, "
    "use the score given in the facts, written naturally (for example 'Corran Vale lead 3-2'); never "
    "state any other number and never copy field names from the facts. Calm, broadcast tone. "
    "Never write \"own clearance\", \"own pass\" or anything that sounds like an own goal: say \"a clearance in his own half\". In Spanish say \"en su propio campo\", never \"propia puerta\" or \"autogol\". "
    "No dashes. Output only the line."
)


class Narrator(Executor):
    @handler
    async def write(self, ev: Evidence, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(await self._compose(ev, None))

    @handler
    async def rewrite(self, d: Draft, ctx: WorkflowContext[Draft]) -> None:
        await ctx.send_message(await self._compose(d.evidence, d))

    async def _compose(self, ev: Evidence, previous: Draft | None) -> Draft:
        t0 = time.perf_counter()
        prompt = "Facts: " + json.dumps(ev.facts, ensure_ascii=False)
        if previous:
            prompt += (f"\nThe line below was rejected by the fairness auditor. Rewrite it so it keeps the "
                       f"facts and tone but shares blame as the evidence does.\nRejected: {previous.text}\n"
                       f"Reasons: {' '.join(previous.reasons)}")
        history = previous.history if previous else []
        revisions = previous.revisions + 1 if previous else 0
        if models.available():
            try:
                text = await models.ask(models.agent("Narrator", NARRATOR_RULES), prompt)
                ev.trace.append(Step("Narrator", "rewrote the line" if previous else "wrote the line",
                                     _ms(t0), text, model=True))
                return Draft(ev, text, "narrator-rewrite" if previous else "narrator", revisions, history)
            except Exception as exc:  # fall back, never block the broadcast
                ev.trace.append(Step("Narrator", "model unavailable, used the template", _ms(t0), type(exc).__name__))
        else:
            ev.trace.append(Step("Narrator", f"{models.offline_reason()}, used the template", _ms(t0)))
        return Draft(ev, _template(ev), "template", revisions, history)


SCORELINE = re.compile(r"(?<![0-9])(\d{1,2})(?:\s*-\s*|\s+a\s+)(\d{1,2})(?![0-9])")  # "2-3", and Spanish "2 a 3"


def _score_after(ledger, chain_id: str, names: dict) -> dict:
    m = ledger.moment(chain_id)
    a = ledger.actions
    shots = a[(a.type_name == "shot") & (a.result_name == "success") & (a.action_id <= m.shot_action_id)]
    teams = list(dict.fromkeys(a.team_id))
    goals = {t: int((shots.team_id == t).sum()) for t in teams}
    return {"text": " ".join(f"{names[t]} {goals[t]}" for t in teams), "goals": [goals[t] for t in teams]}


def _fact_errors(text: str, facts: dict) -> list[str]:
    """Numbers the code can check: any scoreline must be the real score after this moment."""
    real = sorted(facts.get("score_after", {}).get("goals", []))
    errors = []
    for x, y in SCORELINE.findall(text):
        if real and sorted([int(x), int(y)]) != real:
            errors.append(f"The line says {x}-{y}, but the score after this moment is {facts['score_after']['text']}.")
    leaks = models.leaked_fields(text)
    if leaks:
        errors.append(f"The line copies internal field names ({', '.join(leaks)}) instead of plain words.")
    if OWN_GOAL.search(text):  # our matches have no own goals; the model once turned "own-half clearance" into one
        errors.append("The line reads like an own goal; this goal was not one. Say \"in his own half\".")
    errors += [f"\"{w}\" looks like a misspelling of {right}." for w, right in misspelled(text, facts.get("names", []))]
    return errors


OWN_GOAL = re.compile(r"\bown[ -]goal|\bown (?:clearance|pass|touch|header)\b|\bautogol|\bpropia (?:puerta|meta)\b", re.I)


def misspelled(text: str, names: list[str]) -> list[tuple[str, str]]:
    """Capitalised words that are close to a known player or club name but not it: "Quilan" for "Quilian"."""
    import difflib
    known = {w for n in names for w in n.split() if len(w) > 3}
    out = []
    for w in set(re.findall(r"\b[A-Z][a-z]{3,}\b", text)) - known:
        close = difflib.get_close_matches(w, known, n=1, cutoff=0.8)
        if close:
            out.append((w, close[0]))
    return sorted(out)


def _template(ev: Evidence) -> str:
    from narrative_core.extraction import Roster
    store = _store()
    roster: Roster = store.roster(ev.facts["game_id"])
    return fair_rewrite(ev.shares, roster, ev.facts["goal"])


class Auditor(Executor):
    @handler
    async def check(self, d: Draft, ctx: WorkflowContext[Draft | Approved, Result]) -> None:
        t0 = time.perf_counter()
        ev = d.evidence
        try:
            if ev.request.simulate_auditor_outage:
                raise RuntimeError("fairness check unavailable (simulated)")
            store = _store()
            roster = store.roster(ev.facts["game_id"])
            extraction, read_by_model = await deep_extract(d.text, roster, ev.facts["conceding_team_id"], required=True)
            res = audit(d.text, ev.shares, roster, ev.facts["conceding_team_id"], Policy(*ev.request.policy),
                        extraction=extraction, goal=ev.facts["goal"]).to_dict()
        except Exception as exc:
            ev.trace.append(Step("Auditor", "could not run: held, nothing airs", _ms(t0), str(exc)))
            await ctx.yield_output(_result(ev, None, None, d, [], held=str(exc)))
            return
        bad_facts = _fact_errors(d.text, ev.facts)
        if bad_facts:  # a wrong number is treated like unfair blame: it cannot air
            res["verdict"] = "unfair"
            res["reasons"] = bad_facts + res["reasons"]
        d.history.append({"text": d.text, "source": d.source, "si": res["si"], "verdict": res["verdict"],
                          "fact_errors": bad_facts})
        how = "rules and gpt-5-mini reader" if read_by_model else "rules"
        ev.trace.append(Step("Auditor", f"scored {_si(res['si'])}, {res['verdict']} ({how}; score in code)", _ms(t0),
                             d.text, model=read_by_model))
        if res["verdict"] == "unfair" and d.revisions < MAX_REVISIONS:
            d.reasons = res["reasons"] + [res["contrastive"]]
            await ctx.send_message(d)                      # back to the Narrator
        elif res["verdict"] == "unfair":
            # Revisions used up: the template shares blame exactly as the evidence does.
            fallback = Draft(ev, _template(ev), "template", d.revisions + 1, d.history)
            res = audit(fallback.text, ev.shares, store.roster(ev.facts["game_id"]), ev.facts["conceding_team_id"],
                        Policy(*ev.request.policy), goal=ev.facts["goal"]).to_dict()
            fallback.history.append({"text": fallback.text, "source": "template", "si": res["si"], "verdict": res["verdict"]})
            ev.trace.append(Step("Auditor", f"revisions used up: fair template scored {_si(res['si'])}", 0, fallback.text))
            await _line_ready(ev, fallback.text, res)
            await ctx.send_message(Approved(fallback, res))
        else:
            await _line_ready(ev, d.text, res)
            await ctx.send_message(Approved(d, res))


async def _line_ready(ev: Evidence, line: str, res: dict) -> None:
    ev.line_ready_s = round(time.perf_counter() - ev.started, 2)
    if ev.request.on_line is None:
        return
    try:
        await ev.request.on_line(line, res, ev.check)
    except Exception as exc:  # the audience versions still follow; the caller logs its own failure
        ev.trace.append(Step("Auditor", "could not hand the line on", 0, type(exc).__name__))


PERSONALIZER_RULES = (
    "You are the Personalizer for a football broadcast. From the approved line and the facts, write "
    "versions for different viewers. Keep every fact; never add blame beyond the approved line; "
    "refer to defending players by shirt number. At most 30 words each. No dashes. "
    "Never write \"own clearance\", \"own pass\" or anything that sounds like an own goal: say \"a clearance in his own half\". In Spanish say \"en su propio campo\", never \"propia puerta\" or \"autogol\". Reply with JSON "
    'only: {"analyst": "...", "casual": "...", "club": "...", "focus": "...", "es": "..."} where '
    "analyst is numbers-first, casual is plain words for a fan of the conceding team with no blame, "
    "club celebrates the move for the scoring team's fans and credits the unsung player, focus follows "
    "the featured player in context, and es is the approved line translated into Spanish."
)


class Personalizer(Executor):
    @handler
    async def personalize(self, a: Approved, ctx: WorkflowContext[Never, Result]) -> None:
        t0 = time.perf_counter()
        ev = a.draft.evidence
        featured = ev.request.featured or (max(ev.shares, key=ev.shares.get) if ev.shares else None)
        texts: dict[str, str] | None = None
        if models.available():
            try:
                prompt = (f"Approved line: {a.draft.text}\nFacts: {json.dumps(ev.facts, ensure_ascii=False)}\n"
                          f"Featured player id: {featured}")
                raw = await models.ask(models.agent("Personalizer", PERSONALIZER_RULES), prompt)
                texts = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                ev.trace.append(Step("Personalizer", "wrote 5 audience versions", _ms(t0), "", model=True))
            except Exception as exc:
                ev.trace.append(Step("Personalizer", "model unavailable, used templates", _ms(t0), type(exc).__name__))
        if not texts:
            texts = _variant_templates(ev, a.draft.text)
            if not models.available():
                ev.trace.append(Step("Personalizer", f"{models.offline_reason()}, used templates", _ms(t0)))
        store = _store()
        roster = store.roster(ev.facts["game_id"])
        audiences = (("analyst", "Analyst"), ("casual", f"Casual fan of {ev.facts['conceding_team']}"),
                     ("club", f"Fan of {ev.facts['attacking_team']}"), ("focus", "Player focus"),
                     ("es", "Spanish speaker"))
        texts_by_key = {k: models.clean(str(texts.get(k, ""))) or a.draft.text for k, _ in audiences}
        # Check the actual output, including Spanish: checking its source cannot catch a changed translation.
        reads = await asyncio.gather(
            *(deep_extract(texts_by_key[k], roster, ev.facts["conceding_team_id"], required=True)
              for k, _ in audiences), return_exceptions=True)
        variants = []
        for (key, label), reading in zip(audiences, reads, strict=True):
            text = texts_by_key[key]
            if isinstance(reading, BaseException):
                variants.append({"id": key, "audience": label, "text": text, "si": None, "verdict": "held",
                                 "aired": False, "note": "Fairness reader unavailable; this version is held."})
                continue
            extraction, read_by_model = reading
            res = audit(text, ev.shares, roster, ev.facts["conceding_team_id"],
                        Policy(*ev.request.policy), extraction=extraction, goal=ev.facts["goal"])
            bad_facts = _fact_errors(text, ev.facts)
            translation_unchecked = key == "es" and text != a.draft.text and not read_by_model
            notes = bad_facts + (["Translation requires the model reader; this version is held."]
                                 if translation_unchecked else [])
            variants.append({"id": key, "audience": label, "text": text, "si": res.si,
                             "verdict": "unfair" if bad_facts else res.verdict,
                             "aired": res.verdict != "unfair" and not notes,
                             "note": " ".join(notes) if notes else (
                                 "Output checked in Spanish." if key == "es" and read_by_model else None)})
        dropped = sum(not v["aired"] for v in variants)
        ev.trace.append(Step("Auditor", f"checked every version: {len(variants) - dropped} passed, {dropped} held", 0))
        await ctx.yield_output(_result(ev, a.draft.text, a.audit, a.draft, variants))


def _variant_templates(ev: Evidence, line: str) -> dict[str, str]:
    f = ev.facts
    top = f["contributors"][0] if f["contributors"] else None
    single = bool(top) and top["share_pct"] >= JUSTIFIED_SHARE * 100
    analyst = f"{f['minute']}'. {f['actions']} actions. " + "; ".join(
        f"{c['who'].split(' (')[0]} {c['share_pct']}%" for c in f["contributors"] if c["share_pct"] >= 15)
    casual = (f"Tough moment for {f['conceding_team']}: one loose ball and {f['attacking_team']} took it."
              if single else f"Tough one for {f['conceding_team']}: a couple of loose balls gave them a way in.")
    club = f"What a move from {f['attacking_team']}, finished by {f['shooter'].split()[-1]}."
    focus = f"Following {top['who'].split(' (')[0]}: one moment in a full match." if top else line
    return {"analyst": analyst, "casual": casual, "club": club, "focus": focus, "es": line}


def _result(ev: Evidence, line, audit_res, draft: Draft | None, variants, held: str | None = None) -> Result:
    return Result(
        status="held" if held else "ready",
        line=None if held else line, audit=audit_res, source=draft.source if draft else None,
        revisions=draft.revisions if draft else 0, history=draft.history if draft else [],
        variants=variants, trace=[asdict(s) for s in ev.trace], model=models.model_name(),
        model_used=any(s.model for s in ev.trace), held_reason=held,
        line_ready_s=None if held else ev.line_ready_s, check=ev.check,
    )


def deciding_check(ledger, chain_id: str, shares: dict[str, float], roster) -> dict | None:
    """The one action the verdict leans on most: the biggest lost ball by the most responsible player.

    The Investigator hands this to the producer as a single question, and the line waits for the answer.
    """
    if not shares:
        return None
    top = max(shares, key=shares.get)
    c = ledger.chain(chain_id).reset_index(drop=True)
    losses = c[(c.player_id == top) & (c.result_name != "success")].sort_values("vaep_value")
    if losses.empty:
        return None
    a = losses.iloc[0]
    index = int(c.index[c.action_id == a.action_id][0]) + 1
    minute = int(a.time_seconds // 60) + (45 if int(a.period_id) == 2 else 0)
    kind = "carry" if a.type_name == "dribble" else str(a.type_name).replace("_", " ")
    who = _label(roster, top)
    return {"action_id": int(a.action_id), "index": index, "minute": minute, "player_id": top,
            "question": f"Look at action {index} of the build-up ({minute}'). Does the replay show {who} "
                        f"losing the ball with that {kind}?"}


# ---------------------------------------------------------------------------------- build and run
def build():
    inv, nar, aud, per = Investigator(id="investigator"), Narrator(id="narrator"), Auditor(id="auditor"), Personalizer(id="personalizer")
    return (
        WorkflowBuilder(name="many-hands", start_executor=inv, max_iterations=20)
        .add_edge(inv, nar, condition=lambda m: isinstance(m, Evidence))
        .add_edge(inv, aud, condition=lambda m: isinstance(m, Draft))
        .add_edge(nar, aud)
        .add_edge(aud, nar, condition=lambda m: isinstance(m, Draft))
        .add_edge(aud, per, condition=lambda m: isinstance(m, Approved))
        .build()
    )


async def run(req: Request) -> Result:
    t0 = time.perf_counter()
    tally = models.start_usage()
    result = await build().run(req)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError("workflow produced no output")
    out: Result = outputs[-1]
    out.usage = {**tally, "cost_usd": round(models.usage_cost(tally), 6)}
    out.trace.append(asdict(Step("Workflow", "finished", _ms(t0))))
    return out
