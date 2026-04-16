"""Countdown Timer — event-driven WebSocket push (no polling)"""

import asyncio
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

app = FastAPI(title="Countdown Timer")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# ── Shared timer state ────────────────────────────────────────────────────────
_state = {"end_time": 0.0, "duration": 60, "running": False}
_clients: set[WebSocket] = set()

# Background task handle – cancelled/restarted on each Start
_expiry_task: asyncio.Task | None = None


def _snapshot() -> dict:
    if _state["running"]:
        remaining = max(0, int(_state["end_time"] - time.time()))
    else:
        remaining = max(0, _state["duration"])
    done = remaining == 0 and not _state["running"]
    return {"remaining": remaining, "running": _state["running"], "done": done}


async def _broadcast(data: dict):
    dead = set()
    for ws in _clients:
        try:
            await ws.send_json(data)
        except Exception:
            dead.add(ws)
    _clients.difference_update(dead)


async def _expiry_watcher(duration: float):
    """Sleep until the timer expires, then push the final state once."""
    await asyncio.sleep(duration)
    if _state["running"]:
        _state["running"] = False
        await _broadcast({"remaining": 0, "running": False, "done": True})


# ── Routes ────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ── WebSocket ─────────────────────────────────────────────────────────────────
@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    global _expiry_task
    await ws.accept()
    _clients.add(ws)

    # Send current state immediately on connect
    await ws.send_json(_snapshot())

    try:
        async for msg in ws.iter_json():
            action = msg.get("action")

            if action == "start":
                minutes = int(msg.get("minutes", 0))
                seconds = int(msg.get("seconds", 0))
                duration = minutes * 60 + seconds or 60

                _state["duration"] = duration
                _state["end_time"] = time.time() + duration
                _state["running"] = True

                # Cancel any previous expiry watcher, start a new one
                if _expiry_task and not _expiry_task.done():
                    _expiry_task.cancel()
                _expiry_task = asyncio.create_task(_expiry_watcher(duration))

                await _broadcast(_snapshot())

            elif action == "pause":
                remaining = max(0, int(_state["end_time"] - time.time()))
                _state["duration"] = remaining
                _state["running"] = False
                if _expiry_task and not _expiry_task.done():
                    _expiry_task.cancel()
                await _broadcast(_snapshot())

            elif action == "reset":
                _state["duration"] = 60
                _state["end_time"] = 0.0
                _state["running"] = False
                if _expiry_task and not _expiry_task.done():
                    _expiry_task.cancel()
                await _broadcast(_snapshot())

    except (WebSocketDisconnect, Exception):
        pass
    finally:
        _clients.discard(ws)
