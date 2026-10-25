"""Model access for the agents: Microsoft Foundry through Agent Framework, signed in with Entra ID.

Locally the credential is your `azd auth login`; on Azure Container Apps it is the app's managed
identity. No keys anywhere. If no Foundry project is configured, `available()` is False and every
agent uses its deterministic fallback, so the product still works (and says so).
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
from functools import lru_cache
from pathlib import Path

from agent_framework import Agent

TIMEOUT_S = float(os.environ.get("MANYHANDS_MODEL_TIMEOUT", "12"))
FAST = {"reasoning": {"effort": "minimal"}}  # measured: 1.3 s per line versus 5.6 s by default
DASHES = re.compile(r"\s*[‒–—―]\s*")
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


def available() -> bool:
    return bool(_env().get("AZURE_AI_PROJECT_ENDPOINT")) and os.environ.get("MANYHANDS_OFFLINE") != "1"


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


def clean(text: str) -> str:
    """House style: no em or en dashes, no surrounding quotes, single line."""
    text = DASHES.sub(", ", text.strip()).replace("\n", " ")
    return text.strip().strip('"').strip()


async def ask(a: Agent, prompt: str, options: dict | None = None) -> str:
    """Run an agent with a timeout. Raises on failure so the caller can fall back."""
    response = await asyncio.wait_for(a.run(prompt, options=options or FAST), timeout=TIMEOUT_S)
    return clean(response.text)
