def test_web_app_imports():
    from web.app import app

    assert app.title == "YT Anomaly Bot — Standalone GUI"
    paths = {route.path for route in app.routes}
    assert "/api/scan/run" in paths
    assert "/api/proxy/status" in paths
    assert "/api/channels" in paths
