"""Model access for the agents: Microsoft Foundry through Agent Framework, signed in with Entra ID.

Locally the credential is your `azd auth login`; on Azure Container Apps it is the app's managed
identity. No keys anywhere. If no Foundry project is configured, `available()` is False and every
agent uses its deterministic fallback, so the product still works (and says so).
"""

from __future__ import annotations

import asyncio
import contextvars
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

from agent_framework import Agent

TIMEOUT_S = float(os.environ.get("MANYHANDS_MODEL_TIMEOUT", "12"))
FAST = {"reasoning": {"effort": "minimal"}}  # measured: 1.3 s per line versus 5.6 s by default
DASHES = re.compile(r"\s*[‒–—―]\s*")
SCORE_DASH = re.compile(r"(\d)\s*[‒–—―]\s*(\d)")  # "2–3" is a scoreline, not a pause: keep it as "2-3"
QUOTES = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _env() -> dict[str, str]:
    env = dict(os.environ)
    dotenv = Path(__file__).resolve().parents[2] / ".env"
    if dotenv.exists() and "AZURE_AI_PROJECT_ENDPOINT" not in env:
        for line in dotenv.read_text().splitlines():
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip('"'))
    return env


_budget_spent: contextvars.ContextVar[bool] = contextvars.ContextVar("budget_spent", default=False)


def available() -> bool:
    return (bool(_env().get("AZURE_AI_PROJECT_ENDPOINT")) and os.environ.get("MANYHANDS_OFFLINE") != "1"
            and not _budget_spent.get())


def templates_only(spent: bool) -> None:
    """Mark this request as over the daily model budget: every agent uses its template instead."""
    _budget_spent.set(spent)


def offline_reason() -> str:
    return "today's model budget is used up" if _budget_spent.get() else "offline mode"


def model_name() -> str:
    return _env().get("AZURE_OPENAI_DEPLOYMENT", "gpt-5-mini")


def async_credential():
    """Managed identity on Azure; your `azd auth login` locally. Never a key."""
    from azure.identity.aio import AzureDeveloperCliCredential, ManagedIdentityCredential

    env = _env()
    if env.get("IDENTITY_ENDPOINT") or env.get("MSI_ENDPOINT"):  # running on Azure
        return ManagedIdentityCredential(client_id=env.get("AZURE_CLIENT_ID"))
    azd = Path(env.get("LOCALAPPDATA", "")) / "Programs" / "Azure Dev CLI"
    if not shutil.which("azd") and azd.exists():
        os.environ["PATH"] = os.environ.get("PATH", "") + os.pathsep + str(azd)
    return AzureDeveloperCliCredential()


@lru_cache(maxsize=1)
def _client():
    from agent_framework.foundry import FoundryChatClient

    env = _env()
    return FoundryChatClient(project_endpoint=env["AZURE_AI_PROJECT_ENDPOINT"], model=model_name(),
                             credential=async_credential())


def agent(name: str, instructions: str) -> Agent:
    return Agent(client=_client(), name=name, instructions=instructions)


FIELD_LEAK = re.compile(r"\b[a-z]+_[a-z_]+\b\s*:?")  # e.g. "score_after:" copied from the facts


def clean(text: str) -> str:
    """House style: straight quotes, no em or en dashes, no surrounding quotes, single line."""
    text = DASHES.sub(", ", SCORE_DASH.sub(r"\1-\2", text.strip().translate(QUOTES))).replace("\n", " ")
    return text.strip().strip('"').strip()


def leaked_fields(text: str) -> list[str]:
    """Internal field names the model copied from its instructions instead of writing prose."""
    return [m.group(0).rstrip(": ") for m in FIELD_LEAK.finditer(text.lower())]


# Token use per workflow run, so the cost of checking a goal is measured, not estimated.
# Global Standard list prices for gpt-5-mini, USD per million tokens (Azure, Oct 2026).
PRICE_PER_M = {"input": 0.25, "output": 2.00}
_usage: contextvars.ContextVar[dict | None] = contextvars.ContextVar("usage", default=None)


def start_usage() -> dict:
    tally = {"calls": 0, "input_tokens": 0, "output_tokens": 0}
    _usage.set(tally)
    return tally


def usage_cost(tally: dict) -> float:
    return (tally["input_tokens"] * PRICE_PER_M["input"] + tally["output_tokens"] * PRICE_PER_M["output"]) / 1e6


async def ask(a: Agent, prompt: str, options: dict | None = None) -> str:
    """Run an agent with a timeout. Raises on failure so the caller can fall back."""
    response = await asyncio.wait_for(a.run(prompt, options=options or FAST), timeout=TIMEOUT_S)
    tally = _usage.get()
    if tally is not None and response.usage_details:
        tally["calls"] += 1
        tally["input_tokens"] += int(response.usage_details.get("input_token_count") or 0)
        tally["output_tokens"] += int(response.usage_details.get("output_token_count") or 0)
    return clean(response.text)
