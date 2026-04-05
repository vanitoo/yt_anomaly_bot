"""
YouTube Data API v3 client.

Handles channel resolution, video listing, and statistics fetching.
Designed to support future fallback layers (yt-dlp, scraping, etc.).
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import List, Optional
from urllib.parse import urlparse, parse_qs

import httpx

logger = logging.getLogger(__name__)

YOUTUBE_API_BASE = "https://www.googleapis.com/youtube/v3"

# Shorts are typically <= 60 seconds, but YouTube API doesn't expose an is_short flag directly.
# We use duration as a heuristic.
SHORTS_DURATION_THRESHOLD_SECONDS = 61


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
    """
    Async YouTube Data API v3 client.

    All methods raise YouTubeAPIError on non-recoverable API errors.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._http = httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Channel resolution
    # ------------------------------------------------------------------

    async def resolve_channel(self, url_or_handle: str) -> ChannelInfo:
        """
        Resolve a YouTube channel from various URL formats or handles.

        Supported formats:
          - https://youtube.com/channel/UC...
          - https://youtube.com/@handle
          - https://youtube.com/user/username
          - https://youtube.com/c/custom
          - https://youtube.com/watch?v=VIDEO_ID   (extracts channel from video)
          - https://youtube.com/playlist?list=PL.. (extracts channel from playlist)
          - @handle (bare)
          - UCxxxxxxx (bare channel ID)
        """
        # Try video URL first — extract channel ID from video snippet
        video_id = self._extract_video_id(url_or_handle)
        if video_id:
            return await self._fetch_channel_from_video(video_id)

        # Try playlist URL — extract channel from first video
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
        """Extract bare UC... channel ID from URL or raw string."""
        # Raw channel ID
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
        """Extract @handle from URL or bare @handle string."""
        if url.strip().startswith("@"):
            return url.strip().lstrip("@")
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        for part in path_parts:
            if part.startswith("@"):
                return part.lstrip("@")
        return None

    def _extract_username(self, url: str) -> Optional[str]:
        """Extract /user/username or /c/custom from URL."""
        parsed = urlparse(url)
        path_parts = [p for p in parsed.path.split("/") if p]
        for keyword in ("user", "c"):
            if keyword in path_parts:
                idx = path_parts.index(keyword)
                if idx + 1 < len(path_parts):
                    return path_parts[idx + 1]
        return None

    def _extract_video_id(self, url: str) -> Optional[str]:
        """Extract video ID from youtube.com/watch?v=... or youtu.be/... URLs."""
        parsed = urlparse(url)
        if parsed.netloc in ("youtu.be",):
            parts = [p for p in parsed.path.split("/") if p]
            return parts[0] if parts else None
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return qs["v"][0]
        return None

    def _extract_playlist_id(self, url: str) -> Optional[str]:
        """Extract playlist ID from youtube.com/playlist?list=... URLs."""
        parsed = urlparse(url)
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "list" in qs:
                return qs["list"][0]
        return None

    async def _fetch_channel_from_video(self, video_id: str) -> ChannelInfo:
        """Resolve channel by fetching a video's snippet and getting its channelId."""
        data = await self._get(
            "videos",
            params={"part": "snippet", "id": video_id},
        )
        items = data.get("items", [])
        if not items:
            raise ChannelNotFoundError(f"Video not found: {video_id!r}")
        channel_id = items[0]["snippet"]["channelId"]
        return await self._fetch_channel_by_id(channel_id)

    async def _fetch_channel_from_playlist(self, playlist_id: str) -> ChannelInfo:
        """Resolve channel from a playlist's channelId."""
        data = await self._get(
            "playlists",
            params={"part": "snippet", "id": playlist_id},
        )
        items = data.get("items", [])
        if not items:
            raise ChannelNotFoundError(f"Playlist not found: {playlist_id!r}")
        channel_id = items[0]["snippet"]["channelId"]
        return await self._fetch_channel_by_id(channel_id)

    async def _fetch_channel_by_id(self, channel_id: str) -> ChannelInfo:
        data = await self._get(
            "channels",
            params={"part": "snippet,contentDetails", "id": channel_id},
        )
        return self._parse_channel_response(data, lookup=channel_id)

    async def _fetch_channel_by_handle(self, handle: str) -> ChannelInfo:
        data = await self._get(
            "channels",
            params={"part": "snippet,contentDetails", "forHandle": handle},
        )
        return self._parse_channel_response(data, lookup=f"@{handle}")

    async def _fetch_channel_by_username(self, username: str) -> ChannelInfo:
        data = await self._get(
            "channels",
            params={"part": "snippet,contentDetails", "forUsername": username},
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

    # ------------------------------------------------------------------
    # Video listing
    # ------------------------------------------------------------------

    async def get_channel_videos(
        self,
        channel_info: ChannelInfo,
        max_results: int = 200,
    ) -> List[VideoInfo]:
        """
        Fetch recent videos from a channel's uploads playlist.

        Returns videos enriched with statistics and duration.
        YouTube API doesn't support date filtering on playlistItems,
        so we fetch up to max_results and filter in the caller.
        """
        video_ids = await self._get_playlist_video_ids(
            channel_info.uploads_playlist_id, max_results
        )
        if not video_ids:
            logger.warning("No videos found for channel: %s", channel_info.title)
            return []

        return await self._get_videos_details(video_ids)

    async def _get_playlist_video_ids(
        self, playlist_id: str, max_results: int
    ) -> List[str]:
        """Paginate through a playlist and collect video IDs."""
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
                vid_id = item["contentDetails"]["videoId"]
                video_ids.append(vid_id)

            next_page_token = data.get("nextPageToken")
            if not next_page_token:
                break

        return video_ids

    async def _get_videos_details(self, video_ids: List[str]) -> List[VideoInfo]:
        """Batch-fetch video details (statistics + contentDetails) in chunks of 50."""
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
        """Parse a videos.list API item into VideoInfo."""
        try:
            vid_id = item["id"]
            snippet = item.get("snippet", {})
            stats = item.get("statistics", {})
            content = item.get("contentDetails", {})

            title = snippet.get("title", "")
            published_raw = snippet.get("publishedAt", "")
            published_at = datetime.fromisoformat(
                published_raw.replace("Z", "+00:00")
            )

            view_count = int(stats.get("viewCount", 0))
            like_count_raw = stats.get("likeCount")
            like_count = int(like_count_raw) if like_count_raw else None

            duration_str = content.get("duration", "")
            duration_seconds = self._parse_duration(duration_str)
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
                title=title,
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
        """Parse ISO 8601 duration (PT1H2M3S) to total seconds."""
        if not duration:
            return None
        pattern = r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?"
        m = re.match(pattern, duration)
        if not m:
            return None
        hours = int(m.group(1) or 0)
        minutes = int(m.group(2) or 0)
        seconds = int(m.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    # ------------------------------------------------------------------
    # Low-level HTTP
    # ------------------------------------------------------------------

    async def _get(self, endpoint: str, params: dict) -> dict:
        params["key"] = self._api_key
        url = f"{YOUTUBE_API_BASE}/{endpoint}"
        try:
            response = await self._http.get(url, params=params)
        except httpx.TimeoutException as exc:
            raise YouTubeAPIError(f"YouTube API timeout: {exc}") from exc
        except httpx.RequestError as exc:
            raise YouTubeAPIError(f"YouTube API request error: {exc}") from exc

        if response.status_code == 403:
            body = response.json()
            errors = body.get("error", {}).get("errors", [{}])
            reason = errors[0].get("reason", "unknown")
            if reason == "quotaExceeded":
                raise YouTubeAPIError("YouTube API quota exceeded. Try again tomorrow.")
            raise YouTubeAPIError(f"YouTube API 403 forbidden: {reason}")

        if response.status_code == 404:
            raise ChannelNotFoundError("Resource not found (404)")

        if not response.is_success:
            raise YouTubeAPIError(
                f"YouTube API error {response.status_code}: {response.text[:200]}"
            )

        return response.json()
