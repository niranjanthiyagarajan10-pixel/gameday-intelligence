"""The one door for every model call.

Calls go to a model deployed in Microsoft Foundry through Microsoft Agent Framework
(`Agent(client=FoundryChatClient(...))`). Every call gets an 8 second timeout and is timed for the
trace panel. A failure never raises to the caller: it comes back as a result with `ok=False`, and
the caller serves the template fallback, so a fan never sees an error.

Backends:
- `foundry` when FOUNDRY_PROJECT_ENDPOINT is set. Auth is DefaultAzureCredential: `az login`
  locally, the container's managed identity on Azure Container Apps. No keys anywhere.
- `replay` when REPLAY_MODE=1: answers from `data/replays/agent_cache.json`, recorded from earlier
  Foundry runs, so the demo works with Foundry off.
- `offline` otherwise: every call reports "no model configured" and the template is used.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

log = logging.getLogger("gameday.llm")

MODEL_TIMEOUT_S = 8.0
ASK_TIMEOUT_S = 25.0
MAX_IN_FLIGHT = 4  # concurrent model calls per process; more only trips the deployment's rate limit
RATE_LIMIT_BACKOFF_S = (0.6, 1.2, 2.4)  # a whole Ask the match run: several model calls plus tool calls
CACHE_PATH = Path(__file__).resolve().parent.parent / "data" / "replays" / "agent_cache.json"


@dataclass(frozen=True)
class LLMResult:
    text: str | None
    ok: bool
    backend: str
    model: str
    ms: int
    error: str | None = None


class Backend(Protocol):
    name: str

    async def complete(self, *, agent: str, instructions: str, prompt: str, model: str) -> str: ...


class NoModel(RuntimeError):
    """No model is configured, so the caller should use its fallback."""


class OfflineBackend:
    name = "offline"

    async def complete(self, *, agent: str, instructions: str, prompt: str, model: str) -> str:
        raise NoModel("no Foundry endpoint configured")


class FoundryBackend:
    """A model deployment in a Microsoft Foundry project, called through Microsoft Agent Framework."""

    name = "foundry"

    def __init__(self, endpoint: str) -> None:
        from agent_framework.foundry import FoundryChatClient
        from azure.identity.aio import DefaultAzureCredential

        self._endpoint = endpoint
        self._credential = DefaultAzureCredential()
        self._client_type = FoundryChatClient
        self._clients: dict[str, object] = {}

    def _client(self, model: str) -> object:
        # One client per model, reused across calls on the same event loop, as the docs advise.
        if model not in self._clients:
            self._clients[model] = self._client_type(
                project_endpoint=self._endpoint, model=model, credential=self._credential
            )
        return self._clients[model]

    async def run_with_tools(self, *, agent: str, instructions: str, prompt: str, model: str,
                             mcp_url: str) -> tuple[str, list[str]]:
        """An agent run that may call our MCP server's tools; returns its reply and the tools it called."""
        from agent_framework import Agent, MCPStreamableHTTPTool

        async with MCPStreamableHTTPTool(name="gameday", url=mcp_url) as mcp:
            runner = Agent(client=self._client(model), name=agent, instructions=instructions)
            response = await runner.run(prompt, tools=mcp)
        called = []
        for message in getattr(response, "messages", []) or []:
            for content in getattr(message, "contents", []) or []:
                if "FunctionCall" in type(content).__name__ and getattr(content, "name", None):
                    called.append(str(content.name))
        return response.text, called

    async def warm(self, model: str) -> None:
        """One tiny call at startup: the first call on a fresh connection takes about 7 s (auth and
        connection setup), later ones about 2 s, so the first real card must not pay for it."""
        await self._credential.get_token("https://ai.azure.com/.default")
        await self.complete(agent="Warmup", instructions="Reply with one word.", prompt="Say ok", model=model)

    async def complete(self, *, agent: str, instructions: str, prompt: str, model: str) -> str:
        from agent_framework import Agent

        runner = Agent(client=self._client(model), name=agent, instructions=instructions)
        # gpt-5-mini at its default reasoning effort takes about 19 s on a Narrator prompt; low takes about 6 s.
        # Only reasoning models (gpt-5, o-series) accept an effort; gpt-4.1 models would reject it.
        effort = os.getenv("REASONING_EFFORT", "low") if model.startswith(("gpt-5", "o")) else ""
        response = await runner.run(prompt, options={"reasoning": {"effort": effort}} if effort else None)
        return response.text


def cache_key(agent: str, model: str, instructions: str, prompt: str) -> str:
    raw = json.dumps([agent, model, instructions, prompt], ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


class ReplayCache:
    """Model answers recorded from Foundry runs, keyed by agent, model and the exact prompt."""

    def __init__(self, path: Path = CACHE_PATH) -> None:
        self.path = path
        self.entries: dict[str, str] = {}
        if path.exists():
            self.entries = json.loads(path.read_text(encoding="utf-8"))

    def get(self, key: str) -> str | None:
        return self.entries.get(key)

    def put(self, key: str, text: str) -> None:
        self.entries[key] = text

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.entries, ensure_ascii=False, indent=1), encoding="utf-8")


class ReplayBackend:
    name = "replay"

    def __init__(self, cache: ReplayCache) -> None:
        self.cache = cache

    async def complete(self, *, agent: str, instructions: str, prompt: str, model: str) -> str:
        found = self.cache.get(cache_key(agent, model, instructions, prompt))
        if found is None:
            raise NoModel("not in the replay cache")
        return found


class LLM:
    def __init__(
        self,
        backend: Backend | None = None,
        *,
        fast: str = "gpt-5-mini",
        strong: str = "gpt-5-mini",
        timeout_s: float = MODEL_TIMEOUT_S,
        record: ReplayCache | None = None,
    ) -> None:
        self.backend = backend or OfflineBackend()
        self.fast = fast
        self.strong = strong
        self.timeout_s = timeout_s
        self.record = record  # when set, every good Foundry answer is kept for replay mode
        self._slots = asyncio.Semaphore(MAX_IN_FLIGHT)

    @classmethod
    def from_env(cls) -> LLM:
        fast = os.getenv("MODEL_FAST", "gpt-5-mini")
        strong = os.getenv("MODEL_STRONG", fast)
        if os.getenv("REPLAY_MODE", "0") == "1":
            return cls(ReplayBackend(ReplayCache()), fast=fast, strong=strong)
        endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT", "").strip()
        if endpoint and "<" not in endpoint:
            try:
                backend: Backend = FoundryBackend(endpoint)
            except Exception as e:  # missing SDK or bad config: run on templates rather than crash
                log.warning("Foundry backend unavailable, using templates: %s", e)
                backend = OfflineBackend()
            record = ReplayCache() if os.getenv("RECORD_REPLAY", "0") == "1" else None
            return cls(backend, fast=fast, strong=strong, record=record)
        return cls(OfflineBackend(), fast=fast, strong=strong)

    async def warm(self) -> None:
        warm = getattr(self.backend, "warm", None)
        if warm is not None:
            try:
                await asyncio.wait_for(warm(self.strong), timeout=30)
            except Exception as e:  # warming is a nicety; the first real call will retry auth
                log.warning("could not warm the model connection: %s", e)

    async def ask(self, *, agent: str, instructions: str, prompt: str, mcp_url: str,
                  timeout_s: float = ASK_TIMEOUT_S) -> tuple[LLMResult, list[str]]:
        """A tool-using agent run. It makes several model calls (plan, tool calls, answer), so it gets a
        longer overall budget than one call; on failure the caller answers with its fallback."""
        model = self.strong
        started = time.perf_counter()
        took = lambda: round((time.perf_counter() - started) * 1000)  # noqa: E731
        run = getattr(self.backend, "run_with_tools", None)
        if run is None:
            return LLMResult(None, False, self.backend.name, model, 0, "no model with tools configured"), []
        try:
            text, called = await asyncio.wait_for(
                run(agent=agent, instructions=instructions, prompt=prompt, model=model, mcp_url=mcp_url), timeout=timeout_s)
        except TimeoutError:
            return LLMResult(None, False, self.backend.name, model, took(), f"timed out after {timeout_s:.0f} s"), []
        except Exception as e:  # never an error on screen
            log.warning("%s run failed: %s", agent, e)
            return LLMResult(None, False, self.backend.name, model, took(), f"{type(e).__name__}: {e}"[:200]), []
        return LLMResult(text, True, self.backend.name, model, took()), called

    @property
    def live(self) -> bool:
        """True when calls can reach a model (Foundry or the replay cache)."""
        return not isinstance(self.backend, OfflineBackend)

    async def complete(self, *, agent: str, instructions: str, prompt: str, model: str | None = None) -> LLMResult:
        model = model or self.strong
        started = time.perf_counter()

        def took() -> int:
            return round((time.perf_counter() - started) * 1000)

        async def call() -> str:
            # At most a few calls in flight, and a short wait and retry when Foundry says 429 (rate limit),
            # all inside the one time budget: a burst of key moments queues rather than failing.
            async with self._slots:
                for wait in RATE_LIMIT_BACKOFF_S:
                    try:
                        return await self.backend.complete(agent=agent, instructions=instructions, prompt=prompt, model=model)
                    except Exception as e:
                        if "429" not in str(e) and "rate limit" not in str(e).lower():
                            raise
                        log.info("%s rate limited, retrying in %.1f s", agent, wait)
                        await asyncio.sleep(wait)
                return await self.backend.complete(agent=agent, instructions=instructions, prompt=prompt, model=model)

        try:
            text = await asyncio.wait_for(call(), timeout=self.timeout_s)
        except TimeoutError:
            log.info("%s timed out after %.0f s", agent, self.timeout_s)
            return LLMResult(None, False, self.backend.name, model, took(), f"timed out after {self.timeout_s:.0f} s")
        except NoModel as e:
            return LLMResult(None, False, self.backend.name, model, took(), str(e))
        except Exception as e:  # any SDK, auth or network failure becomes a fallback, never an error on screen
            log.warning("%s call failed: %s", agent, e)
            return LLMResult(None, False, self.backend.name, model, took(), f"{type(e).__name__}: {e}"[:200])
        if self.record is not None and self.backend.name == "foundry":
            self.record.put(cache_key(agent, model, instructions, prompt), text)
            self.record.save()
        log.info("%s answered in %d ms via %s", agent, took(), self.backend.name)
        return LLMResult(text, True, self.backend.name, model, took())
