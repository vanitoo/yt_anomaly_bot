"""YouTube Data API v3 client with ProxyManager-aware failover."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional
from urllib.parse import parse_qs, urlparse

import aiohttp

from bot.integrations.proxy_manager import ProxyManager, mask_proxy_url

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"
SHORTS_DURATION_THRESHOLD_SECONDS = 61
CACHE_DB_PATH = Path("data/youtube_cache.db")


@dataclass
class ChannelInfo:
    youtube_channel_id: str
    title: str
    uploads_playlist_id: str


@dataclass
class VideoInfo:
    youtube_video_id: str
    title: str
    published_at: datetime
    view_count: int
    like_count: Optional[int]
    duration_seconds: Optional[int]
    is_short: bool
    thumbnail_url: Optional[str]
    video_url: str


class YouTubeAPIError(Exception):
    """Raised when the YouTube API returns an error or quota is exceeded."""


class ChannelNotFoundError(YouTubeAPIError):
    """Raised when a channel cannot be resolved from the given URL/handle."""


class YouTubeClient:
    """Async YouTube Data API v3 client with cache and proxy failover."""

    def __init__(
        self,
        api_key: str,
        timeout: float = 30.0,
        cache_enabled: bool = True,
        cache_ttl_minutes: int = 15,
        proxy_manager: ProxyManager | None = None,
    ) -> None:
        self._api_key = api_key
        self._timeout = float(timeout)
        self._cache_enabled = cache_enabled
        self._cache_ttl_minutes = max(0, int(cache_ttl_minutes))
        self._proxy_manager = proxy_manager
        self._init_cache_db()

    def _init_cache_db(self) -> None:
        if not self._cache_enabled:
            return
        CACHE_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        with self._get_db_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS api_cache (
                    cache_key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    timestamp INTEGER NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON api_cache(timestamp)")
            conn.commit()

    @contextmanager
    def _get_db_connection(self):
        conn = sqlite3.connect(CACHE_DB_PATH, timeout=10)
        try:
            yield conn
        finally:
            conn.close()

    def _get_cache_key(self, endpoint: str, params: dict) -> str:
        key_data = f"{endpoint}:{json.dumps(params, sort_keys=True)}"
        return hashlib.sha256(key_data.encode()).hexdigest()

    def _is_cache_valid(self, timestamp: int) -> bool:
        if self._cache_ttl_minutes <= 0:
            return False
        age = datetime.now(timezone.utc) - datetime.fromtimestamp(timestamp, timezone.utc)
        return age.total_seconds() < self._cache_ttl_minutes * 60

    def _get_from_cache(self, cache_key: str) -> Optional[dict]:
        if not self._cache_enabled:
            return None
        try:
            with self._get_db_connection() as conn:
                row = conn.execute(
                    "SELECT response, timestamp FROM api_cache WHERE cache_key = ?",
                    (cache_key,),
                ).fetchone()
                if row and self._is_cache_valid(row[1]):
                    return json.loads(row[0])
                if row:
                    conn.execute("DELETE FROM api_cache WHERE cache_key = ?", (cache_key,))
                    conn.commit()
        except Exception as exc:
            logger.warning("Cache read error: %s", exc)
        return None

    def _save_to_cache(self, cache_key: str, response: dict) -> None:
        if not self._cache_enabled:
            return
        try:
            with self._get_db_connection() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_cache (cache_key, response, timestamp) VALUES (?, ?, ?)",
                    (cache_key, json.dumps(response), int(datetime.now(timezone.utc).timestamp())),
                )
                conn.commit()
        except Exception as exc:
            logger.warning("Cache write error: %s", exc)

    async def close(self) -> None:
        """Kept for backwards compatibility; sessions are request-scoped."""
        return None

    def clear_expired_cache(self) -> int:
        if not self._cache_enabled:
            return 0
        cutoff_timestamp = int(
            (datetime.now(timezone.utc) - timedelta(minutes=self._cache_ttl_minutes)).timestamp()
        )
        try:
            with self._get_db_connection() as conn:
                cursor = conn.execute("DELETE FROM api_cache WHERE timestamp < ?", (cutoff_timestamp,))
                conn.commit()
                return cursor.rowcount
        except Exception as exc:
            logger.warning("Cache cleanup error: %s", exc)
            return 0

    async def resolve_channel(self, url_or_handle: str) -> ChannelInfo:
        video_id = self._extract_video_id(url_or_handle)
        if video_id:
            return await self._fetch_channel_from_video(video_id)

        playlist_id = self._extract_playlist_id(url_or_handle)
        if playlist_id:
            return await self._fetch_channel_from_playlist(playlist_id)

        channel_id = self._extract_channel_id_from_url(url_or_handle)
        if channel_id:
            return await self._fetch_channel_by_id(channel_id)

        handle = self._extract_handle(url_or_handle)
        if handle:
            return await self._fetch_channel_by_handle(handle)

        username = self._extract_username(url_or_handle)
        if username:
            return await self._fetch_channel_by_username(username)

        raise ChannelNotFoundError(
            f"Cannot resolve channel from: {url_or_handle!r}. "
            "Please provide a valid YouTube channel URL or @handle."
        )

    def _extract_channel_id_from_url(self, url: str) -> Optional[str]:
        if re.match(r"^UC[\w-]{22}$", url.strip()):
            return url.strip()
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        if "channel" in path_parts:
            idx = path_parts.index("channel")
            if idx + 1 < len(path_parts):
                return path_parts[idx + 1]
        return None

    def _extract_handle(self, url: str) -> Optional[str]:
        if url.strip().startswith("@"):
            return url.strip().lstrip("@")
        parsed = urlparse(url)
        for part in [p for p in parsed.path.split("/") if p]:
            if part.startswith("@"):
                return part.lstrip("@")
        return None

    def _extract_username(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        for keyword in ("user", "c"):
            if keyword in path_parts:
                idx = path_parts.index(keyword)
                if idx + 1 < len(path_parts):
                    return path_parts[idx + 1]
        return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        if parsed.netloc in ("youtu.be", "www.youtu.be"):
            parts = [p for p in parsed.path.split("/") if p]
            return parts[0] if parts else None
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        return None

    def _extract_playlist_id(self, url: str) -> Optional[str]:
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "list" in qs:
                return qs["list"][0]
        return None

    async def _fetch_channel_from_video(self, video_id: str) -> ChannelInfo:
        data = await self._get("videos", params={"part": "snippet", "id": video_id})
        items = data.get("items", [])
        if not items:
            raise ChannelNotFoundError(f"Video not found: {video_id!r}")
        return await self._fetch_channel_by_id(items[0]["snippet"]["channelId"])

    async def _fetch_channel_from_playlist(self, playlist_id: str) -> ChannelInfo:
        data = await self._get("playlists", params={"part": "snippet", "id": playlist_id})
        items = data.get("items", [])
        if not items:
            raise ChannelNotFoundError(f"Playlist not found: {playlist_id!r}")
        return await self._fetch_channel_by_id(items[0]["snippet"]["channelId"])

    async def _fetch_channel_by_id(self, channel_id: str) -> ChannelInfo:
        data = await self._get(
            "channels", params={"part": "snippet,contentDetails", "id": channel_id}
        )
        return self._parse_channel_response(data, lookup=channel_id)

    async def _fetch_channel_by_handle(self, handle: str) -> ChannelInfo:
        data = await self._get(
            "channels", params={"part": "snippet,contentDetails", "forHandle": handle}
        )
        return self._parse_channel_response(data, lookup=f"@{handle}")

    async def _fetch_channel_by_username(self, username: str) -> ChannelInfo:
        data = await self._get(
            "channels", params={"part": "snippet,contentDetails", "forUsername": username}
        )
        return self._parse_channel_response(data, lookup=username)

    def _parse_channel_response(self, data: dict, lookup: str) -> ChannelInfo:
        items = data.get("items", [])
        if not items:
            raise ChannelNotFoundError(f"Channel not found: {lookup!r}")
        item = items[0]
        return ChannelInfo(
            youtube_channel_id=item["id"],
            title=item["snippet"]["title"],
            uploads_playlist_id=item["contentDetails"]["relatedPlaylists"]["uploads"],
        )

    async def get_channel_videos(
        self, channel_info: ChannelInfo, max_results: int = 200
    ) -> List[VideoInfo]:
        video_ids = await self._get_playlist_video_ids(
            channel_info.uploads_playlist_id, max_results
        )
        if not video_ids:
            logger.warning("No videos found for channel: %s", channel_info.title)
            return []
        return await self._get_videos_details(video_ids)

    async def _get_playlist_video_ids(self, playlist_id: str, max_results: int) -> List[str]:
        video_ids: List[str] = []
        next_page_token: Optional[str] = None
        while len(video_ids) < max_results:
            params: dict = {
                "part": "contentDetails,snippet",
                "playlistId": playlist_id,
                "maxResults": min(50, max_results - len(video_ids)),
            }
            if next_page_token:
                params["pageToken"] = next_page_token
            data = await self._get("playlistItems", params=params)
            for item in data.get("items", []):
                video_ids.append(item["contentDetails"]["videoId"])
            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break
        return video_ids

    async def _get_videos_details(self, video_ids: List[str]) -> List[VideoInfo]:
        results: List[VideoInfo] = []
        for i in range(0, len(video_ids), 50):
            chunk = video_ids[i : i + 50]
            data = await self._get(
                "videos",
                params={
                    "part": "snippet,statistics,contentDetails",
                    "id": ",".join(chunk),
                },
            )
            for item in data.get("items", []):
                video = self._parse_video_item(item)
                if video:
                    results.append(video)
        return results

    def _parse_video_item(self, item: dict) -> Optional[VideoInfo]:
        try:
            vid_id = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})
            published_at = datetime.fromisoformat(
                snippet.get("publishedAt", "").replace("Z", "+00:00")
            )
            view_count = int(stats.get("viewCount", 0))
            like_count_raw = stats.get("likeCount")
            like_count = int(like_count_raw) if like_count_raw is not None else None
            duration_seconds = self._parse_duration(content.get("duration", ""))
            is_short = (
                duration_seconds is not None
                and duration_seconds < SHORTS_DURATION_THRESHOLD_SECONDS
            )
            thumbnails = snippet.get("thumbnails", {})
            thumbnail_url = (
                thumbnails.get("maxres", {}).get("url")
                or thumbnails.get("high", {}).get("url")
                or thumbnails.get("medium", {}).get("url")
                or thumbnails.get("default", {}).get("url")
            )
            return VideoInfo(
                youtube_video_id=vid_id,
                title=snippet.get("title", ""),
                published_at=published_at,
                view_count=view_count,
                like_count=like_count,
                duration_seconds=duration_seconds,
                is_short=is_short,
                thumbnail_url=thumbnail_url,
                video_url=f"https://www.youtube.com/watch?v={vid_id}",
            )
        except Exception as exc:
            logger.warning("Failed to parse video item %s: %s", item.get("id"), exc)
            return None

    @staticmethod
    def _parse_duration(duration: str) -> Optional[int]:
        if not duration:
            return None
        match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration)
        if not match:
            return None
        return (
            int(match.group(1) or 0) * 3600
            + int(match.group(2) or 0) * 60
            + int(match.group(3) or 0)
        )

    async def _get(self, endpoint: str, params: dict) -> dict:
        cache_key = self._get_cache_key(endpoint, params)
        cached = self._get_from_cache(cache_key)
        if cached is not None:
            self._track_cache(hit=True)
            return cached
        self._track_cache(hit=False)

        request_params = dict(params)
        request_params["key"] = self._api_key
        url = f"{YOUTUBE_API_BASE}/{endpoint}"

        manager = self._proxy_manager
        max_attempts = 1
        if manager and manager.has_proxies:
            max_attempts = max(1, len(manager.proxies))

        tried: set[str | None] = set()
        last_error: Exception | None = None

        for _ in range(max_attempts):
            proxy = manager.get_proxy() if manager else None
            if manager and manager.has_proxies and proxy is None:
                last_error = YouTubeAPIError("No available proxy for YouTube API request")
                break
            if proxy in tried and proxy is not None:
                proxy = manager.next_proxy() if manager else None
            if proxy in tried:
                break
            tried.add(proxy)

            try:
                result = await self._request_json(url, request_params, proxy)
                self._track_api(endpoint, success=True)
                self._save_to_cache(cache_key, result)
                return result
            except ChannelNotFoundError:
                self._track_api(endpoint, success=False)
                raise
            except YouTubeAPIError as exc:
                last_error = exc
                if not getattr(exc, "proxy_failure", False):
                    self._track_api(endpoint, success=False)
                    raise
                self._track_api(endpoint, success=False)
                if manager and proxy:
                    manager.mark_proxy_failed(proxy)
                    logger.warning(
                        "YouTube request through %s failed; trying next proxy: %s",
                        mask_proxy_url(proxy),
                        exc,
                    )
                    continue
                raise

        if last_error:
            raise last_error
        raise YouTubeAPIError("No available proxy for YouTube API request")

    async def _request_json(self, url: str, params: dict, proxy: str | None) -> dict:
        timeout = aiohttp.ClientTimeout(total=self._timeout)
        protocol = proxy.split("://", 1)[0].lower() if proxy and "://" in proxy else ""

        try:
            if proxy and protocol == "socks5":
                try:
                    import aiohttp_socks
                except ImportError as exc:
                    err = YouTubeAPIError("SOCKS5 proxy requires aiohttp-socks")
                    err.proxy_failure = True  # type: ignore[attr-defined]
                    raise err from exc
                connector = aiohttp_socks.ProxyConnector.from_url(proxy)
                async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                    async with session.get(url, params=params) as response:
                        return await self._decode_response(response)

            async with aiohttp.ClientSession(timeout=timeout) as session:
                kwargs = {"proxy": proxy} if proxy else {}
                async with session.get(url, params=params, **kwargs) as response:
                    return await self._decode_response(response)
        except (aiohttp.ClientError, TimeoutError) as exc:
            err = YouTubeAPIError(f"YouTube API network error: {exc}")
            err.proxy_failure = bool(proxy)  # type: ignore[attr-defined]
            raise err from exc

    async def _decode_response(self, response: aiohttp.ClientResponse) -> dict:
        text = await response.text()
        try:
            body = json.loads(text) if text else {}
        except json.JSONDecodeError:
            body = {}

        if response.status == 403:
            errors = body.get("error", {}).get("errors", [{}])
            reason = errors[0].get("reason", "unknown")
            if reason == "quotaExceeded":
                raise YouTubeAPIError("YouTube API quota exceeded. Try again tomorrow.")
            raise YouTubeAPIError(f"YouTube API 403 forbidden: {reason}")

        if response.status == 404:
            raise ChannelNotFoundError("Resource not found (404)")

        if response.status in {407, 429, 500, 502, 503, 504}:
            err = YouTubeAPIError(f"YouTube API/proxy HTTP {response.status}: {text[:200]}")
            err.proxy_failure = response.status in {407, 502, 503, 504}  # type: ignore[attr-defined]
            raise err

        if response.status >= 400:
            raise YouTubeAPIError(f"YouTube API error {response.status}: {text[:200]}")
        return body

    @staticmethod
    def _track_cache(hit: bool) -> None:
        try:
            from bot.services.metrics import track_cache_hit, track_cache_miss

            (track_cache_hit if hit else track_cache_miss)()
        except ImportError:
            pass

    @staticmethod
    def _track_api(endpoint: str, success: bool) -> None:
        try:
            from bot.services.metrics import track_api_request

            track_api_request(endpoint, success=success)
        except ImportError:
            pass
