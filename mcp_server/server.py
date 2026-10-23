"""The MCP server: the match tools in `mcp_server/tools.py`, over the Model Context Protocol.

It is served by the same FastAPI app at `/mcp` (streamable HTTP), so agents built with Microsoft
Agent Framework (`MCPStreamableHTTPTool`) and GitHub Copilot Agent Mode (`.vscode/mcp.json`) can
read the live match. Every tool is read-only and takes an optional `room` (default: the main match).
"""

from __future__ import annotations

import functools
import inspect
import os
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from mcp_server import tools

INSTRUCTIONS = (
    "Live match intelligence for a synthetic football match in Gameday Intelligence. All tools are read-only. "
    "Numbers come from deterministic code over event and tracking data; quote them, never estimate. "
    "Pass room='main' for the shared live match, or a replay room id."
)


def _security() -> TransportSecuritySettings:
    """DNS rebinding protection stays on; add the public host on Azure with MCP_ALLOWED_HOSTS."""
    hosts = ["127.0.0.1:*", "localhost:*", "[::1]:*"]
    origins = ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"]
    for host in filter(None, (h.strip() for h in os.getenv("MCP_ALLOWED_HOSTS", "").split(","))):
        hosts.append(host)
        origins.append(f"https://{host}")
    return TransportSecuritySettings(enable_dns_rebinding_protection=True, allowed_hosts=hosts, allowed_origins=origins)


def _bind(fn: Any, hub: Any) -> Any:
    """Turn tools.f(room_obj, ...) into an MCP tool f(..., room='main')."""
    sig = inspect.signature(fn)
    params = [p for name, p in sig.parameters.items() if name != "room"]
    params.append(inspect.Parameter("room", inspect.Parameter.KEYWORD_ONLY, default="main", annotation=str))

    @functools.wraps(fn)
    def tool(*args: Any, room: str = "main", **kwargs: Any) -> Any:
        found = hub.get(room)
        if found is None:
            raise ValueError(f"no room {room!r}; use 'main'")
        return fn(found, *args, **kwargs)

    tool.__signature__ = sig.replace(parameters=params)  # type: ignore[attr-defined]
    tool.__annotations__ = {k: v for k, v in fn.__annotations__.items() if k != "room"} | {"room": str}
    return tool


def create_mcp(hub: Any) -> FastMCP:
    mcp = FastMCP(
        "gameday-intelligence",
        instructions=INSTRUCTIONS,
        stateless_http=True,
        json_response=True,
        streamable_http_path="/mcp",
        transport_security=_security(),
    )
    for fn in tools.TOOLS:
        mcp.add_tool(_bind(fn, hub), name=fn.__name__, description=inspect.getdoc(fn))
    return mcp
