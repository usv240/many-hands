"""Blame extraction: turn a sentence about a moment into a distribution of blame over players.

Two extractors share one output schema:
  - RuleExtractor: deterministic, offline, used as the fallback and in tests.
  - A model-based extractor (Microsoft Foundry, structured output) plugs into the same schema.

Rules enforced in code, whichever extractor runs: every mention must quote a span that exists
in the text, and unknown names are reported rather than guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from pydantic import BaseModel, Field, model_validator

STRENGTH_WORDS: list[tuple[int, tuple[str, ...]]] = [
    (3, ("howler", "cost them", "cost us", "all on", "entirely", "solely", "to blame",
         "gifted", "handed them", "calamit", "disaster", "lost them", "threw it away",
         "inexcusable", "unforgivable", "liabilit", "blunder")),
    (2, ("mistake", "error", "fault", "culprit", "guilty", "let them in", "switched off",
         "caught out", "beaten too easily", "sloppy", "careless", "ball-watching",
         "ball watching", "asleep", "should have done better", "nowhere")),
    (1, ("lost the ball", "gave the ball away", "misplaced", "heavy touch", "too high",
         "out of position", "failed to", "could not", "couldn't", "didn't track",
         "did not track", "slow to", "late to", "left", "allowed", "stepped out")),
]
CREDIT_WORDS = ("brilliant", "superb", "assist", "created", "unlocked", "won it", "clever",
                "excellent", "perfect", "great", "wonderful", "scored", "finished")
# Capitalised words that are not names. Anything else unknown is reported as unresolved.
COMMON_WORDS = frozenset(["a", "an", "the", "it", "that", "this", "these", "those", "he", "she", "they", "we", "you", "his", "her", "their", "its", "number", "no", "what", "when", "after", "then", "before", "but", "and", "or", "so", "if", "yes", "not", "another", "one", "two", "three", "first", "second", "half", "minute", "minutes", "goal", "shot", "pass", "cross", "corner", "penalty", "var", "referee", "keeper", "striker", "defence", "defense", "midfield", "team", "home", "away"])
TEAM_WORDS = ("the defence", "the defense", "the back line", "the backline", "the team",
              "the whole team", "everyone", "the midfield", "the back four", "the side")


class Mention(BaseModel):
    player_id: str | None = Field(description="Resolved player id, or null if unresolved")
    span: str = Field(description="The exact words in the text that refer to the player")
    strength: int = Field(ge=0, le=3, description="0 none, 1 mild, 2 clear, 3 sole blame")
    polarity: str = Field(pattern="^(blame|credit)$")
    group: bool = Field(default=False, description="True when the span names a group, not a player")
    members: list[str] = Field(default_factory=list, description="Player ids for a group span")


class Extraction(BaseModel):
    text: str
    mentions: list[Mention]
    unresolved: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def spans_must_exist(self) -> Extraction:
        low = self.text.lower()
        for m in self.mentions:
            if m.span.lower() not in low:
                raise ValueError(f"span not found in text: {m.span!r}")
        return self

    def blame(self) -> dict[str, float]:
        """Blame weights per player. Group mentions are spread evenly over their members."""
        out: dict[str, float] = {}
        for m in self.mentions:
            if m.polarity != "blame" or m.strength == 0:
                continue
            if m.group and m.members:
                for pid in m.members:
                    out[pid] = out.get(pid, 0.0) + m.strength / len(m.members)
            elif m.player_id:
                out[m.player_id] = out.get(m.player_id, 0.0) + m.strength
        return out


@dataclass
class RosterEntry:
    player_id: str
    name: str
    shirt: int
    team_id: str
    role: str = ""
    aliases: tuple[str, ...] = ()


@dataclass
class Roster:
    """Players on the pitch for one match, used to resolve references in text."""

    entries: list[RosterEntry]
    _by_surname: dict[str, list[RosterEntry]] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        for e in self.entries:
            for key in (e.name.split()[-1].lower(), *[a.lower() for a in e.aliases]):
                self._by_surname.setdefault(key, []).append(e)

    def team(self, team_id: str) -> list[RosterEntry]:
        return [e for e in self.entries if e.team_id == team_id]

    def by_shirt(self, team_id: str, shirt: int) -> RosterEntry | None:
        return next((e for e in self.team(team_id) if e.shirt == shirt), None)

    def by_role(self, team_id: str, role_word: str) -> RosterEntry | None:
        roles = {"keeper": ("GK",), "goalkeeper": ("GK",), "striker": ("ST",),
                 "centre back": ("RCB", "LCB"), "center back": ("RCB", "LCB")}
        wanted = roles.get(role_word, ())
        return next((e for e in self.team(team_id) if e.role in wanted), None)

    def by_surname(self, surname: str, team_id: str | None = None) -> list[RosterEntry]:
        hits = self._by_surname.get(surname.lower(), [])
        return [h for h in hits if team_id is None or h.team_id == team_id]


SHIRT_RE = re.compile(r"(?:number|no\.?|#)\s*(\d{1,2})\b", re.I)
ROLE_RE = re.compile(r"\b(the\s+)?(keeper|goalkeeper|striker|centre back|center back)\b", re.I)


class RuleExtractor:
    """Deterministic extraction for offline use. Conservative on purpose: when it cannot tell
    who is meant, it reports the span as unresolved instead of guessing."""

    def __init__(self, roster: Roster, conceding_team_id: str) -> None:
        self.roster = roster
        self.team_id = conceding_team_id

    def _strength(self, text: str) -> int:
        low = text.lower()
        for strength, words in STRENGTH_WORDS:
            if any(w in low for w in words):
                return strength
        return 0

    def extract(self, text: str) -> Extraction:
        low = text.lower()
        strength = self._strength(text)
        credit = any(w in low for w in CREDIT_WORDS)
        mentions: list[Mention] = []
        unresolved: list[str] = []
        seen: set[str] = set()

        def add(entry: RosterEntry | None, span: str) -> None:
            if entry is None:
                unresolved.append(span)
                return
            if entry.player_id in seen:
                return
            seen.add(entry.player_id)
            polarity = "blame" if strength > 0 else ("credit" if credit else "blame")
            mentions.append(Mention(player_id=entry.player_id, span=span, strength=strength,
                                    polarity=polarity))

        for m in SHIRT_RE.finditer(text):
            add(self.roster.by_shirt(self.team_id, int(m.group(1))), m.group(0))
        for m in ROLE_RE.finditer(text):
            add(self.roster.by_role(self.team_id, m.group(2).lower()), m.group(0))
        for word in re.findall(r"[A-Z][a-z]+(?:-[A-Z][a-z]+)?", text):
            hits = self.roster.by_surname(word, self.team_id)
            if len(hits) == 1:
                add(hits[0], word)
            elif len(hits) > 1 or (not hits and word.lower() not in COMMON_WORDS
                                   and not self.roster.by_surname(word)):
                unresolved.append(word)
        for tw in TEAM_WORDS:
            if tw in low and strength > 0:
                members = [e.player_id for e in self.roster.team(self.team_id)]
                if tw in ("the defence", "the defense", "the back line", "the backline", "the back four"):
                    members = [e.player_id for e in self.roster.team(self.team_id)
                               if e.role in ("RB", "RCB", "LCB", "LB")] or members
                idx = low.index(tw)
                mentions.append(Mention(player_id=None, span=text[idx: idx + len(tw)],
                                        strength=strength, polarity="blame", group=True,
                                        members=members))
                break
        return Extraction(text=text, mentions=mentions, unresolved=unresolved)
