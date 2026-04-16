"""Countdown Timer — A simple countdown timer app"""

import os
import sqlite3
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

DB_PATH = os.getenv("DB_PATH", "/tmp/timer.db")


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    db = get_db()
    db.execute(
        "CREATE TABLE IF NOT EXISTS timer "
        "(id INTEGER PRIMARY KEY, end_time REAL, duration INTEGER, running INTEGER DEFAULT 0)"
    )
    db.execute(
        "INSERT OR IGNORE INTO timer (id, end_time, duration, running) VALUES (1, 0, 60, 0)"
    )
    db.commit()
    db.close()
    yield


app = FastAPI(title="Countdown Timer", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def _get_timer(db):
    return db.execute("SELECT * FROM timer WHERE id = 1").fetchone()


def _remaining(row) -> int:
    if not row["running"]:
        return max(0, row["duration"])
    remaining = row["end_time"] - time.time()
    return max(0, int(remaining))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    db = get_db()
    row = _get_timer(db)
    db.close()
    remaining = _remaining(row)
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "remaining": remaining, "running": bool(row["running"]), "duration": row["duration"]},
    )


@app.get("/timer/state", response_class=HTMLResponse)
async def timer_state(request: Request):
    db = get_db()
    row = _get_timer(db)
    remaining = _remaining(row)
    # Auto-stop when it reaches zero
    if row["running"] and remaining == 0:
        db.execute("UPDATE timer SET running = 0 WHERE id = 1")
        db.commit()
    db.close()
    return templates.TemplateResponse(
        "partials/timer_display.html",
        {"request": request, "remaining": remaining, "running": bool(row["running"]) and remaining > 0},
    )


@app.post("/timer/start", response_class=HTMLResponse)
async def start_timer(request: Request):
    form = await request.form()
    minutes = int(form.get("minutes", 0))
    seconds = int(form.get("seconds", 0))
    duration = minutes * 60 + seconds
    if duration <= 0:
        duration = 60
    db = get_db()
    end_time = time.time() + duration
    db.execute(
        "UPDATE timer SET end_time = ?, duration = ?, running = 1 WHERE id = 1",
        (end_time, duration),
    )
    db.commit()
    row = _get_timer(db)
    db.close()
    remaining = _remaining(row)
    return templates.TemplateResponse(
        "partials/timer_display.html",
        {"request": request, "remaining": remaining, "running": True},
    )


@app.post("/timer/pause", response_class=HTMLResponse)
async def pause_timer(request: Request):
    db = get_db()
    row = _get_timer(db)
    remaining = _remaining(row)
    db.execute(
        "UPDATE timer SET running = 0, duration = ? WHERE id = 1",
        (remaining,),
    )
    db.commit()
    db.close()
    return templates.TemplateResponse(
        "partials/timer_display.html",
        {"request": request, "remaining": remaining, "running": False},
    )


@app.post("/timer/reset", response_class=HTMLResponse)
async def reset_timer(request: Request):
    db = get_db()
    db.execute("UPDATE timer SET running = 0, duration = 60, end_time = 0 WHERE id = 1")
    db.commit()
    db.close()
    return templates.TemplateResponse(
        "partials/timer_display.html",
        {"request": request, "remaining": 60, "running": False},
    )
