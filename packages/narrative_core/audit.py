"""Audit a sentence about a moment: who it blames, how fair that is, and a fairer version.

This is the deterministic core of the Auditor agent. A model-based extractor can replace
RuleExtractor, and a model-based rewriter can replace the template, but the score itself is
always computed here, in code, from the extraction and the ledger. That is what makes it
tamper-resistant: an instruction hidden in the text cannot change the number.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from narrative_core.extraction import Extraction, Roster, RuleExtractor
from narrative_core.scapegoat import (
    Policy,
    Verdict,
    blame_inflation,
    normalize,
    percents,
    scapegoat_index,
    verdict,
)

JUSTIFIED_SHARE = 0.60


@dataclass
class AuditResult:
    text: str
    si: float
    verdict: str
    blame: dict[str, float]
    evidence: dict[str, float]
    inflation: dict[str, float]
    mentions: list[dict]
    unresolved: list[str]
    reasons: list[str]
    contrastive: str
    fair_rewrite: str | None
    justified: bool

    def to_dict(self) -> dict:
        return asdict(self)


def _label(roster: Roster | None, pid: str) -> str:
    if roster is None:
        return pid
    e = next((x for x in roster.entries if x.player_id == pid), None)
    return f"number {e.shirt}" if e else pid


def contrastive(evidence: dict[str, float], blamed: str | None, roster: Roster | None) -> str:
    """Why this player and not that one, in one sentence."""
    r = normalize(evidence)
    if not r:
        return "The evidence does not point to any defending mistake behind this moment."
    pc = percents(r)
    order = sorted(r.items(), key=lambda kv: -kv[1])
    top = order[0][0]
    if blamed and blamed in r and blamed != top:
        return (f"{_label(roster, blamed).capitalize()} carried {pc[blamed]}% of the danger; "
                f"{_label(roster, top)} carried {pc[top]}%, the largest share.")
    if blamed and blamed not in r:
        return (f"The evidence gives {_label(roster, blamed)} no share of this moment; "
                f"{_label(roster, top)} carried the largest share at {pc[top]}%.")
    if len(order) == 1:
        return f"{_label(roster, top).capitalize()} carried all of the measurable danger."
    second = order[1][0]
    return (f"{_label(roster, top).capitalize()} carried {pc[top]}% of the danger, "
            f"{_label(roster, second)} {pc[second]}%.")


def fair_rewrite(evidence: dict[str, float], roster: Roster | None, goal: bool = True) -> str:
    """A template line that keeps the facts and shares blame the way the evidence does."""
    r = sorted(normalize(evidence).items(), key=lambda kv: -kv[1])
    outcome = "the goal" if goal else "the chance"
    if not r:
        return f"A well-worked move created {outcome}; no single defensive mistake stands out."
    if r[0][1] >= JUSTIFIED_SHARE:
        return (f"{_label(roster, r[0][0]).capitalize()} lost the ball, and that error "
                f"led directly to {outcome}.")
    names = [_label(roster, p) for p, s in r[:3] if s >= 0.15]
    if len(names) == 1:
        return f"A loss of the ball by {names[0]} led to {outcome}, with the defence unable to recover."
    joined = ", ".join(names[:-1]) + f" and {names[-1]}"
    return f"Mistakes by {joined} combined to let the attack through for {outcome}."


def audit(text: str, evidence: dict[str, float], roster: Roster | None = None,
          conceding_team_id: str | None = None, policy: Policy = Policy(),
          extraction: Extraction | None = None, goal: bool = True) -> AuditResult:
    if extraction is None:
        if roster is None or conceding_team_id is None:
            raise ValueError("roster and conceding_team_id are needed to extract blame from text")
        extraction = RuleExtractor(roster, conceding_team_id).extract(text)
    blame = extraction.blame()
    si = scapegoat_index(blame, evidence)
    v = verdict(si, policy)
    r = normalize(evidence)
    # No counted mistake is missing evidence, not proof of innocence: a person decides. Measured on
    # held-out known-cause matches, this cut wrong Unfair calls on deserved blame from 21 to 6 percent.
    no_evidence = bool(normalize(blame)) and not r
    if no_evidence:
        v = Verdict.WATCH
    top = max(r, key=r.get) if r else None
    justified = bool(top and r[top] >= JUSTIFIED_SHARE and set(normalize(blame)) == {top})
    blamed = max(blame, key=blame.get) if blame else None
    reasons: list[str] = []
    if not blame:
        reasons.append("The line blames no one, so it scores 0.")
    elif no_evidence:
        reasons.append("No defender lost the ball in this move, so the evidence can neither support nor rule "
                       "out this blame. A producer decides.")
    elif v is Verdict.FAIR:
        reasons.append("The blame in the line matches the evidence.")
    else:
        infl = blame_inflation(blame, evidence)
        worst = max(infl, key=infl.get)
        reasons.append(f"{_label(roster, worst).capitalize()} gets {infl[worst]:.1f} times the blame the "
                       f"evidence supports.")
        missing = [p for p, s in r.items() if s >= 0.15 and p not in blame]
        if missing:
            reasons.append("Not mentioned despite a real share: " +
                           ", ".join(f"{_label(roster, p)} ({percents(r)[p]}%)" for p in missing) + ".")
    if extraction.unresolved:
        reasons.append("Could not tell who is meant by: " + ", ".join(extraction.unresolved) + ".")
    return AuditResult(
        text=text, si=round(si, 3), verdict=v.value, blame=normalize(blame), evidence=r,
        inflation={k: round(x, 2) for k, x in blame_inflation(blame, evidence).items()},
        mentions=[m.model_dump() for m in extraction.mentions],
        unresolved=list(extraction.unresolved), reasons=reasons,
        contrastive=contrastive(evidence, blamed, roster),
        fair_rewrite=None if v is Verdict.FAIR else fair_rewrite(evidence, roster, goal),
        justified=justified,
    )
