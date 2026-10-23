"""HTTP and WebSocket API. Serves the built dashboard from web/dist when it exists.

    uvicorn app.main:app --port 8000
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.env import load_env

load_env()  # before anything reads FOUNDRY_PROJECT_ENDPOINT or the model names

from app.room import SPEEDS, Hub, MatchRoom, RoomConfig  # noqa: E402
from engine.league import build_league  # noqa: E402
from mcp_server.server import create_mcp, http_app  # noqa: E402

DIST = Path(__file__).resolve().parent.parent / "web" / "dist"


class NewRoom(BaseModel):
    start_minute: float = Field(default=0.0, ge=0.0, le=89.0)
    speed: float = 1.0


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=300)
    lang: Literal["en", "es", "hi"] = "en"
    audience: Literal["casual", "analyst"] = "casual"


class Control(BaseModel):
    action: Literal["speed", "pause", "resume", "restart"]
    value: float | None = None


def create_app(default: RoomConfig | None = None) -> FastAPI:
    hub = Hub(build_league(), default or RoomConfig.from_env())
    mcp = create_mcp(hub)
    mcp_app = http_app(mcp)  # creates the session manager the lifespan runs

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        async with mcp.session_manager.run():
            await hub.start()
            yield
            await hub.stop()

    app = FastAPI(title="Gameday Intelligence", lifespan=lifespan)
    app.state.hub = hub
    # MCP over streamable HTTP at /mcp, for agents and GitHub Copilot Agent Mode
    app.router.routes.extend(mcp_app.routes)

    def room_or_404(room_id: str) -> MatchRoom:
        room = hub.get(room_id)
        if room is None:
            raise HTTPException(404, "no such room")
        return room

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "rooms": len(hub.rooms)}

    @app.get("/api/rooms/{room_id}")
    async def room_state(room_id: str) -> dict[str, Any]:
        return room_or_404(room_id).hello()

    @app.get("/api/rooms/{room_id}/cues")
    async def room_cues(room_id: str) -> dict[str, Any]:
        """Timed, machine-readable overlay cues, ready for a broadcast renderer."""
        return {"cues": room_or_404(room_id).cues()}

    @app.get("/api/rooms/{room_id}/shots/{event_id}")
    async def shot(room_id: str, event_id: str) -> dict[str, Any]:
        """One shot: its metrics and a tracking replay of the 12 seconds before it."""
        found = room_or_404(room_id).shot(event_id)
        if found is None:
            raise HTTPException(404, "no such shot")
        return found

    @app.get("/api/rooms/{room_id}/trace")
    async def trace(room_id: str) -> dict[str, Any]:
        """Every agent step so far: Narrator drafts, Verifier verdicts, fallbacks, with timings."""
        room = room_or_404(room_id)
        return {"agents": room.agent_info(), "steps": list(room.trace)}

    @app.post("/api/rooms/{room_id}/ask")
    async def ask(room_id: str, body: Question) -> dict[str, Any]:
        """Ask the match: the Analyst agent answers from the MCP tools, every number re-read by code."""
        return await room_or_404(room_id).ask(body.question, body.lang, body.audience)

    @app.post("/api/rooms/{room_id}/recap")
    async def write_recap(room_id: str) -> dict[str, Any]:
        """Ask the Recap agent for the match report so far (it also writes one at full time)."""
        room = room_or_404(room_id)
        written = await room.write_recap()
        return {"recap": written, "agents": room.agent_info()}

    @app.get("/api/rooms/{room_id}/blueprint")
    async def blueprint(room_id: str) -> dict[str, Any]:
        """The Match Blueprint: overview, highlights, performers, shot difficulty, gravity, marking, leverage."""
        return room_or_404(room_id).blueprint()

    @app.get("/api/rooms/{room_id}/players/{player_id}")
    async def player(room_id: str, player_id: str) -> dict[str, Any]:
        """A player's game averages and every shot they took."""
        found = room_or_404(room_id).player(player_id)
        if found is None:
            raise HTTPException(404, "no such player")
        return found

    @app.post("/api/rooms")
    async def new_room(body: NewRoom) -> dict[str, Any]:
        if body.speed not in SPEEDS:
            raise HTTPException(422, f"speed must be one of {SPEEDS}")
        try:
            room = hub.private(body.start_minute, body.speed)
        except RuntimeError as e:
            raise HTTPException(429, str(e)) from e
        return {"room_id": room.room_id}

    @app.post("/api/rooms/{room_id}/control")
    async def control(room_id: str, body: Control) -> dict[str, Any]:
        try:
            return room_or_404(room_id).control(body.action, body.value)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e

    @app.websocket("/ws/{room_id}")
    async def stream(ws: WebSocket, room_id: str) -> None:
        room = hub.get(room_id)
        await ws.accept()
        if room is None:
            await ws.close(code=4404)
            return
        # Snapshot in the same step as subscribing, so every later message is newer than the snapshot.
        queue = room.subscribe()
        snapshot = room.hello()

        async def send() -> None:
            await ws.send_json(snapshot)
            while True:
                await ws.send_json(await queue.get())

        async def receive() -> None:
            while True:
                msg = await ws.receive_json()
                try:
                    room.control(str(msg.get("action")), msg.get("value"))
                except ValueError:
                    await ws.send_json({"type": "error", "message": "bad control"})

        tasks = [asyncio.create_task(send()), asyncio.create_task(receive())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        except WebSocketDisconnect:
            pass
        finally:
            for t in tasks:
                t.cancel()
            room.unsubscribe(queue)

    if DIST.exists():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="web")
    return app


app = create_app()
