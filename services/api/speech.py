"""The on-air voice: Azure AI Speech reads out lines that passed the fairness check, and nothing else.

A line becomes speakable only when the server itself approved it: the Auditor passed it, a producer
aired it, or it is an audience version that passed its own check. Any other text is refused, so the
voice cannot be used to read out a line the check rejected, or anything else.

Signed in with the app's managed identity (Entra ID) against the Foundry account's own endpoint. No
keys. Each line is synthesised once and cached.
"""

from __future__ import annotations

import time
from collections import OrderedDict
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx

from services.agents import models

VOICES = {"en": ("en-GB", "en-GB-SoniaNeural"), "es": ("es-ES", "es-ES-AlvaroNeural")}
MAX_CHARS = 400


class Voice:
    def __init__(self) -> None:
        self.approved: OrderedDict[str, float] = OrderedDict()   # text -> when it was approved
        self.cache: OrderedDict[tuple[str, str], bytes] = OrderedDict()
        self._token: tuple[str, float] | None = None
        self._credential = None

    # ------------------------------------------------------------------ what may be spoken
    def approve(self, text: str | None) -> None:
        if not text:
            return
        self.approved[text.strip()] = time.time()
        self.approved.move_to_end(text.strip())
        while len(self.approved) > 2000:
            self.approved.popitem(last=False)

    def approve_result(self, result) -> None:
        """Everything a workflow result lets go on air: a passing main line and its passing versions."""
        if getattr(result, "status", None) != "ready" or not result.audit or result.audit.get("verdict") == "unfair":
            return
        self.approve(result.line)
        for v in result.variants:
            if v.get("aired"):
                self.approve(v.get("text"))

    def allowed(self, text: str) -> bool:
        return text.strip() in self.approved

    # ------------------------------------------------------------------ synthesis
    def _endpoint(self) -> str | None:
        project = models._env().get("AZURE_AI_PROJECT_ENDPOINT")
        if not project:
            return None
        host = urlparse(project).hostname or ""
        return f"https://{host}/tts/cognitiveservices/v1"

    async def _bearer(self) -> str:
        if self._token and self._token[1] - time.time() > 300:
            return self._token[0]
        if self._credential is None:
            self._credential = models.async_credential()
        tok = await self._credential.get_token("https://cognitiveservices.azure.com/.default")
        self._token = (tok.token, float(tok.expires_on))
        return tok.token

    async def speak(self, text: str, lang: str = "en") -> bytes:
        text = text.strip()
        key = (text, lang)
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        endpoint = self._endpoint()
        if endpoint is None or not models.available():
            raise RuntimeError("the voice runs on the hosted version")
        locale, voice = VOICES[lang]
        ssml = (f"<speak version='1.0' xml:lang='{locale}'><voice name='{voice}'>"
                f"<prosody rate='-3%'>{escape(text[:MAX_CHARS])}</prosody></voice></speak>")
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(endpoint, content=ssml.encode("utf-8"), headers={
                "Authorization": f"Bearer {await self._bearer()}", "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": "audio-24khz-48kbitrate-mono-mp3", "User-Agent": "many-hands"})
        r.raise_for_status()
        self.cache[key] = r.content
        while len(self.cache) > 300:
            self.cache.popitem(last=False)
        return r.content


voice = Voice()
