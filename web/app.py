"""
Web panel for YouTube Anomaly Bot.

FastAPI application exposing:
  - REST API endpoints (JSON) for the dashboard
  - Static HTML dashboard served at /

Run standalone:
    uvicorn web.app:app --host 0.0.0.0 --port 8000 --reload

Or mount on an existing app. Reads the same .env / DATABASE_URL as the bot.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.settings import get_settings
from bot.models.database import get_session_factory
from bot.models.orm import Channel, Detection, Video

# ---------------------------------------------------------------------------
# App lifecycle
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = get_settings()
    factory = get_session_factory(cfg.database_url)
    app.state.session_factory = factory
    yield


app = FastAPI(
    title="YT Anomaly Bot — Web Panel",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Serve static files (dashboard HTML)
STATIC_DIR = Path(__file__).parent / "static"
TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# DB dependency
# ---------------------------------------------------------------------------

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    factory = app.state.session_factory
    async with factory() as session:
        yield session


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def root():
    """Serve the main dashboard HTML."""
    html_path = TEMPLATE_DIR / "dashboard.html"
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/api/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)) -> dict:
    """High-level summary numbers for the dashboard header."""
    total_channels = (await db.execute(select(func.count(Channel.id)))).scalar_one()
    active_channels = (
        await db.execute(select(func.count(Channel.id)).where(Channel.is_active.is_(True)))
    ).scalar_one()
    total_videos = (await db.execute(select(func.count(Video.id)))).scalar_one()
    total_detections = (await db.execute(select(func.count(Detection.id)))).scalar_one()
    sent_detections = (
        await db.execute(
            select(func.count(Detection.id)).where(Detection.sent_to_chat.is_(True))
        )
    ).scalar_one()

    # Best anomaly ever recorded
    best = (
        await db.execute(
            select(Detection.anomaly_ratio).order_by(desc(Detection.anomaly_ratio)).limit(1)
        )
    ).scalar_one_or_none()

    # Last check time = latest detection
    last_detected = (
        await db.execute(
            select(Detection.detected_at).order_by(desc(Detection.detected_at)).limit(1)
        )
    ).scalar_one_or_none()

    return {
        "total_channels": total_channels,
        "active_channels": active_channels,
        "total_videos": total_videos,
        "total_detections": total_detections,
        "sent_detections": sent_detections,
        "best_ratio": round(best, 2) if best else None,
        "last_check": last_detected.isoformat() if last_detected else None,
    }


@app.get("/api/detections")
async def list_detections(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    channel_id: int | None = Query(None),
    days: int = Query(90, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Paginated list of anomaly detections with joined video + channel info.
    """
    since = datetime.now(timezone.utc) - timedelta(days=days)

    q = (
        select(Detection, Video, Channel)
        .join(Video, Detection.video_id == Video.id)
        .join(Channel, Detection.channel_id == Channel.id)
        .where(Detection.detected_at >= since)
        .where(Detection.sent_to_chat.is_(True))
    )
    if channel_id:
        q = q.where(Detection.channel_id == channel_id)

    count_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(count_q)).scalar_one()

    rows = (
        await db.execute(
            q.order_by(desc(Detection.detected_at)).limit(limit).offset(offset)
        )
    ).all()

    items = []
    for det, vid, ch in rows:
        items.append(
            {
                "id": det.id,
                "detected_at": det.detected_at.isoformat(),
                "channel_title": ch.channel_title,
                "channel_id": ch.id,
                "video_title": vid.title,
                "video_url": vid.video_url,
                "thumbnail_url": vid.thumbnail_url,
                "published_at": vid.published_at.isoformat(),
                "view_count": vid.view_count,
                "baseline_value": round(det.baseline_value),
                "anomaly_ratio": round(det.anomaly_ratio, 2),
                "anomaly_percent": round(det.anomaly_percent),
                "baseline_method": det.baseline_method,
                "status": det.status,
            }
        )

    return {"total": total, "items": items}


@app.get("/api/channels")
async def list_channels(db: AsyncSession = Depends(get_db)) -> list[dict]:
    """List all channels with their anomaly counts and latest stats."""
    channels = (
        await db.execute(select(Channel).order_by(Channel.channel_title))
    ).scalars().all()

    result = []
    for ch in channels:
        detection_count = (
            await db.execute(
                select(func.count(Detection.id))
                .where(Detection.channel_id == ch.id)
                .where(Detection.sent_to_chat.is_(True))
            )
        ).scalar_one()

        video_count = (
            await db.execute(
                select(func.count(Video.id)).where(Video.channel_id == ch.id)
            )
        ).scalar_one()

        best_ratio = (
            await db.execute(
                select(func.max(Detection.anomaly_ratio)).where(
                    Detection.channel_id == ch.id
                )
            )
        ).scalar_one_or_none()

        last_detection = (
            await db.execute(
                select(Detection.detected_at)
                .where(Detection.channel_id == ch.id)
                .where(Detection.sent_to_chat.is_(True))
                .order_by(desc(Detection.detected_at))
                .limit(1)
            )
        ).scalar_one_or_none()

        result.append(
            {
                "id": ch.id,
                "youtube_channel_id": ch.youtube_channel_id,
                "title": ch.channel_title,
                "is_active": ch.is_active,
                "input_url": ch.input_url,
                "created_at": ch.created_at.isoformat(),
                "video_count": video_count,
                "detection_count": detection_count,
                "best_ratio": round(best_ratio, 2) if best_ratio else None,
                "last_detection": last_detection.isoformat() if last_detection else None,
            }
        )

    return result


@app.get("/api/charts/anomalies_over_time")
async def anomalies_over_time(
    days: int = Query(90, ge=7, le=365),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Daily anomaly counts for the timeline chart."""
    since = datetime.now(timezone.utc) - timedelta(days=days)

    rows = (
        await db.execute(
            select(
                func.date(Detection.detected_at).label("day"),
                func.count(Detection.id).label("count"),
                func.avg(Detection.anomaly_ratio).label("avg_ratio"),
            )
            .where(Detection.detected_at >= since)
            .where(Detection.sent_to_chat.is_(True))
            .group_by(func.date(Detection.detected_at))
            .order_by("day")
        )
    ).all()

    return [
        {"day": str(r.day), "count": r.count, "avg_ratio": round(r.avg_ratio, 2)}
        for r in rows
    ]


@app.get("/api/charts/ratio_distribution")
async def ratio_distribution(
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Ratio distribution bucketed for histogram."""
    rows = (
        await db.execute(
            select(Detection.anomaly_ratio)
            .where(Detection.sent_to_chat.is_(True))
        )
    ).scalars().all()

    buckets: dict[str, int] = {}
    boundaries = [1.8, 2.0, 2.5, 3.0, 4.0, 5.0, 7.5, 10.0, float("inf")]
    labels = ["1.8–2x", "2–2.5x", "2.5–3x", "3–4x", "4–5x", "5–7.5x", "7.5–10x", "10x+"]
    counts = [0] * len(labels)

    for ratio in rows:
        for i, boundary in enumerate(boundaries[1:]):
            if ratio < boundary:
                counts[i] += 1
                break

    return [{"label": lbl, "count": cnt} for lbl, cnt in zip(labels, counts)]


@app.get("/api/charts/top_channels")
async def top_channels(
    limit: int = Query(10, ge=3, le=20),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Top channels by anomaly count."""
    rows = (
        await db.execute(
            select(
                Channel.channel_title,
                func.count(Detection.id).label("detections"),
                func.avg(Detection.anomaly_ratio).label("avg_ratio"),
                func.max(Detection.anomaly_ratio).label("max_ratio"),
            )
            .join(Detection, Channel.id == Detection.channel_id)
            .where(Detection.sent_to_chat.is_(True))
            .group_by(Channel.id, Channel.channel_title)
            .order_by(desc("detections"))
            .limit(limit)
        )
    ).all()

    return [
        {
            "channel": r.channel_title,
            "detections": r.detections,
            "avg_ratio": round(r.avg_ratio, 2),
            "max_ratio": round(r.max_ratio, 2),
        }
        for r in rows
    ]
