import pytest

from bot.integrations.proxy_manager import ProxyManager
from bot.integrations.youtube.client import YouTubeAPIError, YouTubeClient


@pytest.mark.asyncio
async def test_youtube_api_fails_over_to_next_proxy(monkeypatch):
    primary = "http://proxy-primary:3128"
    backup = "http://proxy-backup:3128"
    manager = ProxyManager([primary, backup], mode="failover")
    client = YouTubeClient(
        api_key="test",
        cache_enabled=False,
        proxy_manager=manager,
    )
    calls = []

    async def fake_request(url, params, proxy):
        calls.append(proxy)
        if proxy == primary:
            exc = YouTubeAPIError("primary unavailable")
            exc.proxy_failure = True
            raise exc
        return {"items": [{"id": "ok"}]}

    monkeypatch.setattr(client, "_request_json", fake_request)

    result = await client._get("videos", {"part": "snippet"})

    assert result["items"][0]["id"] == "ok"
    assert calls == [primary, backup]
    assert 0 in manager.failed_proxies
    assert manager.current_proxy == backup


@pytest.mark.asyncio
async def test_youtube_does_not_fall_back_direct_when_configured_proxies_fail(monkeypatch):
    proxies = ["http://proxy-a:3128", "http://proxy-b:3128"]
    manager = ProxyManager(proxies, mode="failover")
    client = YouTubeClient(
        api_key="test",
        cache_enabled=False,
        proxy_manager=manager,
    )
    calls = []

    async def always_fail(url, params, proxy):
        calls.append(proxy)
        exc = YouTubeAPIError("proxy unavailable")
        exc.proxy_failure = True
        raise exc

    monkeypatch.setattr(client, "_request_json", always_fail)

    with pytest.raises(YouTubeAPIError):
        await client._get("videos", {"part": "snippet"})

    assert calls == proxies
    assert None not in calls
    assert manager.failed_proxies == {0, 1}
