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

import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Never

from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler
from narrative_core.audit import JUSTIFIED_SHARE, audit, fair_rewrite
from narrative_core.scapegoat import Policy

from services.agents import models

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


@dataclass
class Evidence:
    request: Request
    facts: dict[str, Any]
    shares: dict[str, float]
    trace: list[Step] = field(default_factory=list)


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


def _ms(t0: float) -> int:
    return int((time.perf_counter() - t0) * 1000)


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
        names = store.roster_df.drop_duplicates("team_id").set_index("team_id")["team"].to_dict()
        facts = {
            "minute": summary["minute"], "goal": summary["goal"],
            "attacking_team": names[summary["attacking_team_id"]],
            "conceding_team": names[summary["conceding_team_id"]],
            "conceding_team_id": summary["conceding_team_id"],
            "game_id": int(L.game_id),
            "shooter": L.name(summary["shooter_id"]),
            "actions": summary["n_actions"],
            "contributors": [{"who": _label(roster, r["player_id"]), "share_pct": round(100 * r["share"]),
                              "what": r["reason"]} for r in summary["responsibility"]],
            "unsung": None if not summary["unsung"] else
                      {"who": summary["unsung"]["name"], "what": summary["unsung"]["reason"]},
        }
        ev = Evidence(req, facts, shares)
        ev.trace.append(Step("Investigator", "gathered evidence with the ledger tools", _ms(t0),
                             f"{summary['n_actions']} actions; {len(shares)} defending player(s) lost the ball"))
        if req.incoming:
            await ctx.send_message(Draft(ev, req.incoming, "incoming"))
        else:
            await ctx.send_message(ev)


NARRATOR_RULES = (
    "You are the Narrator for a live football broadcast. Write ONE line for an on-screen graphic, "
    "at most 25 words, from the facts only. Never invent players, numbers or events. Refer to "
    "defending players by shirt number. Blame must match the responsibility shares: name a single "
    "player as the cause only if their share is 60 percent or more; otherwise share it among the "
    "players with 15 percent or more, or describe the move without blame. Calm, broadcast tone. "
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
            ev.trace.append(Step("Narrator", "offline mode, used the template", _ms(t0)))
        return Draft(ev, _template(ev), "template", revisions, history)


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
            res = audit(d.text, ev.shares, store.roster(ev.facts["game_id"]), ev.facts["conceding_team_id"],
                        Policy(*ev.request.policy), goal=ev.facts["goal"]).to_dict()
        except Exception as exc:
            ev.trace.append(Step("Auditor", "could not run: held, nothing airs", _ms(t0), str(exc)))
            await ctx.yield_output(_result(ev, None, None, d, [], held=str(exc)))
            return
        d.history.append({"text": d.text, "source": d.source, "si": res["si"], "verdict": res["verdict"]})
        ev.trace.append(Step("Auditor", f"scored {res['si']:.2f}, {res['verdict']}", _ms(t0), d.text))
        if res["verdict"] == "unfair" and d.revisions < MAX_REVISIONS:
            d.reasons = res["reasons"] + [res["contrastive"]]
            await ctx.send_message(d)                      # back to the Narrator
        elif res["verdict"] == "unfair":
            # Revisions used up: the template shares blame exactly as the evidence does.
            fallback = Draft(ev, _template(ev), "template", d.revisions + 1, d.history)
            res = audit(fallback.text, ev.shares, store.roster(ev.facts["game_id"]), ev.facts["conceding_team_id"],
                        Policy(*ev.request.policy), goal=ev.facts["goal"]).to_dict()
            fallback.history.append({"text": fallback.text, "source": "template", "si": res["si"], "verdict": res["verdict"]})
            ev.trace.append(Step("Auditor", f"revisions used up: fair template scored {res['si']:.2f}", 0, fallback.text))
            await ctx.send_message(Approved(fallback, res))
        else:
            await ctx.send_message(Approved(d, res))


PERSONALIZER_RULES = (
    "You are the Personalizer for a football broadcast. From the approved line and the facts, write "
    "versions for different viewers. Keep every fact; never add blame beyond the approved line; "
    "refer to defending players by shirt number. At most 30 words each. No dashes. Reply with JSON "
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
                ev.trace.append(Step("Personalizer", "offline mode, used templates", _ms(t0)))
        store = _store()
        roster = store.roster(ev.facts["game_id"])
        variants = []
        for key, label in (("analyst", "Analyst"), ("casual", f"Casual fan of {ev.facts['conceding_team']}"),
                           ("club", f"Fan of {ev.facts['attacking_team']}"), ("focus", "Player focus"),
                           ("es", "Spanish speaker")):
            text = models.clean(str(texts.get(key, ""))) or a.draft.text
            source_text = a.draft.text if key == "es" else text  # translations are checked on the English source
            res = audit(source_text, ev.shares, roster, ev.facts["conceding_team_id"],
                        Policy(*ev.request.policy), goal=ev.facts["goal"])
            variants.append({"id": key, "audience": label, "text": text, "si": res.si, "verdict": res.verdict,
                             "aired": res.verdict != "unfair",
                             "note": "Checked on the English source before translation." if key == "es" else None})
        dropped = sum(not v["aired"] for v in variants)
        ev.trace.append(Step("Auditor", f"checked every version: {len(variants) - dropped} fair, {dropped} held", 0))
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
    )


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
    result = await build().run(req)
    outputs = result.get_outputs()
    if not outputs:
        raise RuntimeError("workflow produced no output")
    out: Result = outputs[-1]
    out.trace.append(asdict(Step("Workflow", "finished", _ms(t0))))
    return out
