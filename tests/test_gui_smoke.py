from fastapi.testclient import TestClient

from web.app import app


def test_web_app_routes_are_registered():
    assert app.title == "YT Anomaly Bot — Standalone GUI"
    paths = {route.path for route in app.routes}
    assert "/api/scan/run" in paths
    assert "/api/proxy/status" in paths
    assert "/api/channels" in paths


def test_standalone_gui_starts_and_serves_core_endpoints():
    with TestClient(app) as client:
        root = client.get("/")
        assert root.status_code == 200
        assert "YT Anomaly Lab" in root.text

        runtime = client.get("/api/runtime")
        assert runtime.status_code == 200
        payload = runtime.json()
        assert payload["scan"]["running"] is False
        assert "proxy" in payload

        stats = client.get("/api/stats/overview")
        assert stats.status_code == 200
        data = stats.json()
        assert "total_channels" in data
        assert "total_videos" in data
