"""The Scapegoat Index: how far the blame in a sentence is from the blame in the evidence.

SI is the total variation distance between two distributions over players:
  b, the blame a sentence assigns (from blame extraction), and
  r, the responsibility the evidence assigns (from the ledger).
SI is 0 when the story matches the evidence and approaches 1 when the story pins the moment
on players the evidence does not support. A sentence that blames no one scores 0.
"""

from __future__ import annotations

from collections.abc import Hashable, Mapping
from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    FAIR = "fair"
    WATCH = "watch"
    UNFAIR = "unfair"


@dataclass(frozen=True)
class Policy:
    """Per-tenant thresholds. Defaults follow the technical design, section 4.5."""

    watch_above: float = 0.20
    unfair_above: float = 0.40

    def __post_init__(self) -> None:
        if not 0.0 <= self.watch_above <= self.unfair_above <= 1.0:
            raise ValueError("thresholds must satisfy 0 <= watch_above <= unfair_above <= 1")


def normalize[K: Hashable](weights: Mapping[K, float]) -> dict[K, float]:
    """Scale non-negative weights to sum to 1. Negative weights count as 0."""
    clipped = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(clipped.values())
    if total == 0:
        return {}
    return {k: v / total for k, v in clipped.items() if v > 0}


def scapegoat_index[K: Hashable](blame: Mapping[K, float], evidence: Mapping[K, float]) -> float:
    """Total variation distance between narrative blame and evidence responsibility."""
    b = normalize(blame)
    if not b:
        return 0.0
    r = normalize(evidence)
    if not r:
        return 1.0  # blame with no supporting evidence at all
    keys = b.keys() | r.keys()
    return 0.5 * sum(abs(b.get(k, 0.0) - r.get(k, 0.0)) for k in keys)


def blame_inflation[K: Hashable](
    blame: Mapping[K, float], evidence: Mapping[K, float], floor: float = 0.01
) -> dict[K, float]:
    """How many times more blame each named player gets than the evidence supports."""
    b, r = normalize(blame), normalize(evidence)
    return {k: v / max(r.get(k, 0.0), floor) for k, v in b.items()}


def verdict(si: float, policy: Policy = Policy()) -> Verdict:
    if si > policy.unfair_above:
        return Verdict.UNFAIR
    if si > policy.watch_above:
        return Verdict.WATCH
    return Verdict.FAIR
