"""
Tests for YouTubeClient URL/handle parsing logic.

These tests don't make real HTTP calls — they test only the internal
URL parsing methods which are pure functions.
"""
from __future__ import annotations

import pytest

from bot.integrations.youtube.client import YouTubeClient


@pytest.fixture
def client() -> YouTubeClient:
    # API key doesn't matter — no HTTP calls in these tests
    return YouTubeClient(api_key="FAKE_KEY")


class TestExtractChannelIdFromUrl:
    def test_bare_channel_id(self, client):
        cid = client._extract_channel_id_from_url("UCxxxxxxxxxxxxxxxxxxxxxx")
        assert cid == "UCxxxxxxxxxxxxxxxxxxxxxx"

    def test_channel_url(self, client):
        cid = client._extract_channel_id_from_url(
            "https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx"
        )
        assert cid == "UCxxxxxxxxxxxxxxxxxxxxxx"

    def test_channel_url_with_trailing_slash(self, client):
        cid = client._extract_channel_id_from_url(
            "https://www.youtube.com/channel/UCxxxxxxxxxxxxxxxxxxxxxx/"
        )
        assert cid == "UCxxxxxxxxxxxxxxxxxxxxxx"

    def test_non_channel_url_returns_none(self, client):
        assert client._extract_channel_id_from_url("https://youtube.com/@MrBeast") is None

    def test_random_string_returns_none(self, client):
        assert client._extract_channel_id_from_url("not-a-url") is None


class TestExtractHandle:
    def test_bare_handle_with_at(self, client):
        assert client._extract_handle("@MrBeast") == "MrBeast"

    def test_url_with_handle(self, client):
        assert client._extract_handle("https://youtube.com/@MrBeast") == "MrBeast"

    def test_url_without_handle(self, client):
        assert client._extract_handle("https://youtube.com/channel/UCxxxx") is None

    def test_bare_handle_no_at_returns_none(self, client):
        assert client._extract_handle("MrBeast") is None


class TestExtractUsername:
    def test_user_url(self, client):
        assert client._extract_username("https://youtube.com/user/LinusTechTips") == "LinusTechTips"

    def test_c_url(self, client):
        assert client._extract_username("https://youtube.com/c/TED") == "TED"

    def test_channel_url_returns_none(self, client):
        assert client._extract_username("https://youtube.com/channel/UCxxxx") is None


class TestExtractVideoId:
    def test_watch_url(self, client):
        assert client._extract_video_id("https://www.youtube.com/watch?v=dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_youtu_be_url(self, client):
        assert client._extract_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"

    def test_non_video_url_returns_none(self, client):
        assert client._extract_video_id("https://youtube.com/@MrBeast") is None

    def test_channel_url_returns_none(self, client):
        assert client._extract_video_id("https://youtube.com/channel/UCxxxx") is None


class TestExtractPlaylistId:
    def test_playlist_url(self, client):
        result = client._extract_playlist_id(
            "https://www.youtube.com/playlist?list=PLxxxxxxxxxxxxxxxxxxxxxxxx"
        )
        assert result == "PLxxxxxxxxxxxxxxxxxxxxxxxx"

    def test_watch_url_with_list_param(self, client):
        result = client._extract_playlist_id(
            "https://youtube.com/watch?v=abc&list=PLyyyy"
        )
        assert result == "PLyyyy"

    def test_non_playlist_url_returns_none(self, client):
        assert client._extract_playlist_id("https://youtube.com/@MrBeast") is None


class TestParseDuration:
    def test_full_duration(self, client):
        assert client._parse_duration("PT1H2M3S") == 3723

    def test_minutes_and_seconds(self, client):
        assert client._parse_duration("PT10M30S") == 630

    def test_seconds_only(self, client):
        assert client._parse_duration("PT45S") == 45

    def test_hours_only(self, client):
        assert client._parse_duration("PT2H") == 7200

    def test_empty_string_returns_none(self, client):
        assert client._parse_duration("") is None

    def test_invalid_returns_none(self, client):
        assert client._parse_duration("NOT_A_DURATION") is None

    def test_short_video_under_61s(self, client):
        duration = client._parse_duration("PT58S")
        assert duration is not None and duration < 61

    def test_long_video_over_61s(self, client):
        duration = client._parse_duration("PT5M30S")
        assert duration is not None and duration >= 61
