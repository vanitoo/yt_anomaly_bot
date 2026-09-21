"""Standalone FastAPI GUI for YouTube anomaly monitoring."""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncGenerator

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config.settings import get_settings
from bot.integrations.proxy_runtime import get_proxy_manager
from bot.integrations.youtube.client import ChannelNotFoundError, YouTubeAPIError, YouTubeClient
from bot.models.database import get_session_factory
from bot.models.migrations import run_migrations
from bot.models.orm import Channel, Detection, Video
from bot.repositories.channel_repo import ChannelRepository
from bot.services.analysis_runner import AnalysisRunner
from bot.services.channel_service import ChannelService

logger = logging.getLogger(__name__)
TEMPLATE_DIR = Path(__file__).parent / "templates"


class ChannelCreate(BaseModel):
    url: str = Field(min_length=1, max_length=512)


class ChannelPatch(BaseModel):
    is_active: bool


class ScanRuntime:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.running = False
        self.last_started: datetime | None = None
        self.last_finished: datetime | None = None
        self.last_summary: dict | None = None
        self.last_error: str | None = None
        self.auto_task: asyncio.Task | None = None

    def as_dict(self) -> dict:
        cfg = get_settings()
        return {
            "running": self.running,
            "last_started": self.last_started.isoformat() if self.last_started else None,
            "last_finished": self.last_finished.isoformat() if self.last_finished else None,
            "last_summary": self.last_summary,
            "last_error": self.last_error,
            "auto_scan": cfg.web_auto_scan,
            "poll_interval_minutes": cfg.web_poll_interval_minutes,
        }


async def _run_scan(app: FastAPI) -> dict:
    state: ScanRuntime = app.state.scan_runtime
    if state.lock.locked():
        raise RuntimeError("Analysis is already running")

    cfg = get_settings()
    async with state.lock:
        state.running = True
        state.last_started = datetime.now(timezone.utc)
        state.last_error = None
        try:
            async with app.state.session_factory() as session:
                client = YouTubeClient(
                    api_key=cfg.youtube_api_key,
                    cache_ttl_minutes=cfg.youtube_cache_ttl_minutes,
                    proxy_manager=app.state.proxy_manager,
                )
                runner = AnalysisRunner(
                    session=session,
                    youtube_client=client,
                    bot=None,
                    chat_id=None,
                    notify_telegram=False,
                )
                summary = await runner.run()
                await session.commit()
            state.last_summary = summary
            return summary
        except Exception as exc:
            state.last_error = str(exc)
            logger.exception("Standalone GUI analysis failed")
            raise
        finally:
            state.last_finished = datetime.now(timezone.utc)
            state.running = False


async def _auto_scan_loop(app: FastAPI) -> None:
    cfg = get_settings()
    if cfg.web_scan_on_start:
        try:
            await _run_scan(app)
        except Exception:
            logger.exception("Initial GUI scan failed")

    interval = max(1, cfg.web_poll_interval_minutes) * 60
    while True:
        try:
            await asyncio.sleep(interval)
            await _run_scan(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Automatic GUI scan failed")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    cfg = get_settings()
    await asyncio.to_thread(run_migrations, cfg.database_url)
    app.state.session_factory = get_session_factory(cfg.database_url)
    app.state.scan_runtime = ScanRuntime()
    app.state.proxy_manager = get_proxy_manager()

    proxy = app.state.proxy_manager
    if proxy.has_proxies:
        await proxy.check_all()
        await proxy.start_healthcheck_loop()

    if cfg.web_auto_scan:
        app.state.scan_runtime.auto_task = asyncio.create_task(
            _auto_scan_loop(app), name="web-auto-scan"
        )

    yield

    if app.state.scan_runtime.auto_task:
        app.state.scan_runtime.auto_task.cancel()
        try:
            await app.state.scan_runtime.auto_task
        except asyncio.CancelledError:
            pass
    await proxy.stop_healthcheck_loop()


app = FastAPI(
    title="YT Anomaly Bot — Standalone GUI",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url=None,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _yt_client() -> YouTubeClient:
    cfg = get_settings()
    return YouTubeClient(
        api_key=cfg.youtube_api_key,
        cache_ttl_minutes=cfg.youtube_cache_ttl_minutes,
        proxy_manager=app.state.proxy_manager,
    )


@app.get("/", response_class=HTMLResponse)
async def root() -> HTMLResponse:
    return HTMLResponse((TEMPLATE_DIR / "dashboard.html").read_text(encoding="utf-8"))


@app.get("/api/runtime")
async def runtime_status() -> dict:
    return {
        "scan": app.state.scan_runtime.as_dict(),
        "proxy": app.state.proxy_manager.get_status(),
    }


@app.post("/api/scan/run")
async def run_scan_now() -> dict:
    if app.state.scan_runtime.lock.locked():
        raise HTTPException(status_code=409, detail="Analysis is already running")
    try:
        summary = await _run_scan(app)
        return {"ok": True, "summary": summary}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/proxy/status")
async def proxy_status() -> dict:
    return app.state.proxy_manager.get_status()


@app.post("/api/proxy/check")
async def proxy_check() -> dict:
    manager = app.state.proxy_manager
    results = await manager.check_all()
    return {"results": results, "status": manager.get_status()}


@app.get("/api/stats/overview")
async def stats_overview(db: AsyncSession = Depends(get_db)) -> dict:
    total_channels = (await db.execute(select(func.count(Channel.id)))).scalar_one()
    active_channels = (
        await db.execute(select(func.count(Channel.id)).where(Channel.is_active.is_(True)))
    ).scalar_one()
    total_videos = (await db.execute(select(func.count(Video.id)))).scalar_one()
    total_detections = (await db.execute(select(func.count(Detection.id)))).scalar_one()
    best = (
        await db.execute(select(func.max(Detection.anomaly_ratio)))
    ).scalar_one_or_none()
    state = app.state.scan_runtime
    return {
        "total_channels": total_channels,
        "active_channels": active_channels,
        "total_videos": total_videos,
        "total_detections": total_detections,
        "best_ratio": round(best, 2) if best else None,
        "last_check": state.last_finished.isoformat() if state.last_finished else None,
    }


@app.get("/api/channels")
async def list_channels(db: AsyncSession = Depends(get_db)) -> list[dict]:
    channels = (await db.execute(select(Channel).order_by(Channel.channel_title))).scalars().all()
    result: list[dict] = []
    for ch in channels:
        video_count = (
            await db.execute(select(func.count(Video.id)).where(Video.channel_id == ch.id))
        ).scalar_one()
        detection_count = (
            await db.execute(select(func.count(Detection.id)).where(Detection.channel_id == ch.id))
        ).scalar_one()
        best_ratio = (
            await db.execute(select(func.max(Detection.anomaly_ratio)).where(Detection.channel_id == ch.id))
        ).scalar_one_or_none()
        result.append(
            {
                "id": ch.id,
                "youtube_channel_id": ch.youtube_channel_id,
                "title": ch.channel_title,
                "input_url": ch.input_url,
                "is_active": ch.is_active,
                "video_count": video_count,
                "detection_count": detection_count,
                "best_ratio": round(best_ratio, 2) if best_ratio else None,
            }
        )
    return result


@app.post("/api/channels")
async def add_channel(payload: ChannelCreate, db: AsyncSession = Depends(get_db)) -> dict:
    try:
        service = ChannelService(db, _yt_client())
        channel, created = await service.add_channel(payload.url.strip())
        return {
            "created": created,
            "channel": {
                "id": channel.id,
                "youtube_channel_id": channel.youtube_channel_id,
                "title": channel.channel_title,
                "is_active": channel.is_active,
            },
        }
    except ChannelNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except YouTubeAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.patch("/api/channels/{channel_id}")
async def patch_channel(
    channel_id: int,
    payload: ChannelPatch,
    db: AsyncSession = Depends(get_db),
) -> dict:
    repo = ChannelRepository(db)
    channel = await repo.get_by_id(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    await repo.set_active(channel.youtube_channel_id, payload.is_active)
    return {"ok": True, "is_active": payload.is_active}


@app.delete("/api/channels/{channel_id}")
async def delete_channel(channel_id: int, db: AsyncSession = Depends(get_db)) -> dict:
    repo = ChannelRepository(db)
    channel = await repo.get_by_id(channel_id)
    if channel is None:
        raise HTTPException(status_code=404, detail="Channel not found")
    await repo.delete(channel.youtube_channel_id)
    return {"ok": True}


@app.get("/api/videos")
async def list_videos(
    channel_id: int | None = Query(None),
    days: int = Query(90, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        select(Video, Channel)
        .join(Channel, Video.channel_id == Channel.id)
        .where(Video.published_at >= since)
    )
    if channel_id:
        q = q.where(Video.channel_id == channel_id)
    rows = (
        await db.execute(q.order_by(desc(Video.published_at)).limit(limit))
    ).all()
    return [
        {
            "id": video.id,
            "channel_id": channel.id,
            "channel": channel.channel_title,
            "title": video.title,
            "published_at": video.published_at.isoformat(),
            "view_count": video.view_count,
            "like_count": video.like_count,
            "duration_seconds": video.duration_seconds,
            "is_short": video.is_short,
            "thumbnail_url": video.thumbnail_url,
            "video_url": video.video_url,
        }
        for video, channel in rows
    ]


@app.get("/api/detections")
async def list_detections(
    channel_id: int | None = Query(None),
    days: int = Query(365, ge=1, le=3650),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    q = (
        select(Detection, Video, Channel)
        .join(Video, Detection.video_id == Video.id)
        .join(Channel, Detection.channel_id == Channel.id)
        .where(Detection.detected_at >= since)
    )
    if channel_id:
        q = q.where(Detection.channel_id == channel_id)
    rows = (
        await db.execute(q.order_by(desc(Detection.detected_at)).limit(limit))
    ).all()
    return [
        {
            "id": det.id,
            "detected_at": det.detected_at.isoformat(),
            "channel": ch.channel_title,
            "channel_id": ch.id,
            "video_title": vid.title,
            "video_url": vid.video_url,
            "thumbnail_url": vid.thumbnail_url,
            "published_at": vid.published_at.isoformat(),
            "view_count_at_detection": det.view_count_at_detection,
            "baseline_value": round(det.baseline_value),
            "anomaly_ratio": round(det.anomaly_ratio, 2),
            "anomaly_percent": round(det.anomaly_percent),
            "baseline_method": det.baseline_method,
            "status": det.status,
        }
        for det, vid, ch in rows
    ]


@app.get("/api/charts/anomalies_over_time")
async def anomalies_over_time(
    days: int = Query(90, ge=7, le=3650),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    since = datetime.now(timezone.utc) - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                func.date(Detection.detected_at).label("day"),
                func.count(Detection.id).label("count"),
                func.avg(Detection.anomaly_ratio).label("avg_ratio"),
            )
            .where(Detection.detected_at >= since)
            .group_by(func.date(Detection.detected_at))
            .order_by("day")
        )
    ).all()
    return [
        {"day": str(r.day), "count": r.count, "avg_ratio": round(r.avg_ratio or 0, 2)}
        for r in rows
    ]
