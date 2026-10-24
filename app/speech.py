"""The commentator's voice: Azure AI Speech text to speech, keyless.

Auth is Microsoft Entra ID through DefaultAzureCredential (`az login` locally, the container's
managed identity on Azure), sent as `aad#<resource id>#<token>` to the regional endpoint. The
resource needs a custom domain and the Cognitive Services Speech User role. Our Foundry resource
has both, so the voice runs on the same resource as the agents.

Only verified text is ever spoken: the API takes a moment id and a style, never free text.
If Speech is not configured, slow or failing, the caller hands the text to the browser's own
voice instead, so the fan never sees an error.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
import urllib.request
from collections import OrderedDict
from dataclasses import dataclass
from xml.sax.saxutils import escape

log = logging.getLogger("gameday.speech")

SPEECH_TIMEOUT_S = 8.0
TOKEN_SCOPE = "https://cognitiveservices.azure.com/.default"
CACHE_MAX = 300
LOCALES = {"en": "en-GB", "es": "es-ES", "hi": "hi-IN"}


@dataclass(frozen=True)
class Voice:
    name: str
    style: str | None = None
    degree: float = 1.0
    rate: str = "0%"


# One voice per commentator style and language. English styles that need emotion use US voices
# that support speaking styles; the rest are plain neural voices.
VOICES: dict[tuple[str, str], Voice] = {
    ("classic", "en"): Voice("en-GB-RyanNeural"),
    ("hype", "en"): Voice("en-US-JasonNeural", style="excited", degree=1.6, rate="+8%"),
    ("stats", "en"): Voice("en-US-BrianNeural", rate="+4%"),
    ("tactician", "en"): Voice("en-US-GuyNeural", style="newscast", rate="-4%"),
    ("classic", "es"): Voice("es-ES-AlvaroNeural"),
    ("hype", "es"): Voice("es-MX-JorgeNeural", style="cheerful", degree=1.5, rate="+8%"),
    ("stats", "es"): Voice("es-ES-DarioNeural"),
    ("tactician", "es"): Voice("es-ES-EliasNeural", rate="-4%"),
    ("classic", "hi"): Voice("hi-IN-MadhurNeural"),
    ("hype", "hi"): Voice("hi-IN-AaravNeural", rate="+8%"),
    ("stats", "hi"): Voice("hi-IN-KunalNeural"),
    ("tactician", "hi"): Voice("hi-IN-RehaanNeural", rate="-4%"),
}


def voice_for(style: str, lang: str) -> Voice:
    return VOICES.get((style, lang)) or VOICES[("classic", lang if lang in LOCALES else "en")]


def ssml(text: str, style: str, lang: str) -> str:
    v = voice_for(style, lang)
    locale = v.name[:5]
    body = f'<prosody rate="{v.rate}">{escape(text)}</prosody>'
    if v.style:
        body = f'<mstts:express-as style="{v.style}" styledegree="{v.degree}">{body}</mstts:express-as>'
    return (
        f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
        f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{locale}">'
        f'<voice name="{v.name}">{body}</voice></speak>'
    )


class Speech:
    def __init__(self, region: str, resource_id: str) -> None:
        from azure.identity import DefaultAzureCredential

        self.url = f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1"
        self.resource_id = resource_id
        self._credential = DefaultAzureCredential()
        self._token: tuple[str, float] | None = None
        self._cache: OrderedDict[str, bytes] = OrderedDict()

    @classmethod
    def from_env(cls) -> Speech | None:
        region = os.getenv("SPEECH_REGION", "").strip()
        resource_id = os.getenv("SPEECH_RESOURCE_ID", "").strip()
        if not region or not resource_id or "<" in region + resource_id:
            return None
        try:
            return cls(region, resource_id)
        except Exception as e:  # missing SDK or bad config: the browser voice takes over
            log.warning("Azure AI Speech unavailable: %s", e)
            return None

    def _bearer(self) -> str:
        if self._token is None or self._token[1] - time.time() < 300:
            token = self._credential.get_token(TOKEN_SCOPE)
            self._token = (token.token, float(token.expires_on))
        return f"aad#{self.resource_id}#{self._token[0]}"

    def _synthesize(self, body: str) -> bytes:
        req = urllib.request.Request(self.url, data=body.encode("utf-8"), method="POST", headers={
            "Authorization": f"Bearer {self._bearer()}",
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": "audio-24khz-96kbitrate-mono-mp3",
            "User-Agent": "gameday-intelligence",
        })
        with urllib.request.urlopen(req, timeout=SPEECH_TIMEOUT_S) as r:
            return r.read()

    async def speak(self, text: str, style: str, lang: str) -> tuple[bytes | None, int, str]:
        """MP3 bytes, the time it took and a status for the trace. None means use the browser voice."""
        body = ssml(text, style, lang)
        key = hashlib.sha256(body.encode("utf-8")).hexdigest()
        if key in self._cache:
            self._cache.move_to_end(key)
            return self._cache[key], 0, "cached"
        started = time.perf_counter()
        try:
            audio = await asyncio.wait_for(asyncio.to_thread(self._synthesize, body), SPEECH_TIMEOUT_S)
        except Exception as e:
            log.warning("speech failed: %s", e)
            return None, round((time.perf_counter() - started) * 1000), f"error: {type(e).__name__}"
        self._cache[key] = audio
        if len(self._cache) > CACHE_MAX:
            self._cache.popitem(last=False)
        return audio, round((time.perf_counter() - started) * 1000), "ok"
