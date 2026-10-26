"""Usage limits for the public demo: per-caller rate limits and a daily model budget.

The demo is open, with no sign-in, so judges can use it freely. These limits keep one busy caller
from spending the model budget or slowing everyone else down:

  - each caller (by IP address) gets a few model-backed requests a minute; past that, a 429 with
    a plain message and Retry-After;
  - the whole service gets a daily budget of model-backed runs; past that, the agents use their
    deterministic templates for the rest of the day, so the product keeps working and says so.

In-memory, for one replica. A multi-replica deployment would keep these counters in a shared
store or put Azure API Management in front.
"""

from __future__ import annotations

import os
import time
from collections import defaultdict, deque
from datetime import UTC, datetime

from fastapi import HTTPException, Request

PER_MINUTE = {"model": int(os.environ.get("MANYHANDS_MODEL_PER_MINUTE", "12")),
              "kickoff": int(os.environ.get("MANYHANDS_KICKOFF_PER_MINUTE", "4"))}
DAILY_MODEL_RUNS = int(os.environ.get("MANYHANDS_DAILY_MODEL_RUNS", "2000"))  # about $3.50 at measured cost
MAX_LIVE_MATCHES = int(os.environ.get("MANYHANDS_MAX_LIVE_MATCHES", "3"))


def client_id(request: Request) -> str:
    """The caller's address. Behind Container Apps ingress the first X-Forwarded-For entry is the client."""
    forwarded = request.headers.get("x-forwarded-for", "")
    return forwarded.split(",")[0].strip() or (request.client.host if request.client else "unknown")


class Limits:
    def __init__(self) -> None:
        self.hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self.day = ""
        self.model_runs = 0

    def check(self, kind: str, who: str, now: float | None = None) -> None:
        """Raise 429 when `who` has used up this minute's allowance for `kind`."""
        now = time.monotonic() if now is None else now
        q = self.hits[(kind, who)]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= PER_MINUTE[kind]:
            wait = int(60 - (now - q[0])) + 1
            raise HTTPException(429, f"Too many requests from you in the last minute. Try again in {wait} s.",
                                headers={"Retry-After": str(wait)})
        q.append(now)

    def take_model_run(self) -> bool:
        """Spend one model-backed run from today's budget. False means: use the templates."""
        today = datetime.now(UTC).date().isoformat()
        if today != self.day:
            self.day, self.model_runs = today, 0
        if self.model_runs >= DAILY_MODEL_RUNS:
            return False
        self.model_runs += 1
        return True

    def status(self) -> dict:
        return {"model_runs_today": self.model_runs, "daily_model_budget": DAILY_MODEL_RUNS,
                "per_minute": PER_MINUTE, "max_live_matches": MAX_LIVE_MATCHES}


limits = Limits()


def limit(kind: str):
    """A FastAPI dependency: `Depends(limit("model"))`."""
    def dependency(request: Request) -> None:
        limits.check(kind, client_id(request))
    return dependency
