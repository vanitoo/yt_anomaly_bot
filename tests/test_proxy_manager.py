from bot.integrations.proxy_manager import ProxyManager, ProxyMode, mask_proxy_url


def test_parse_proxy_env_and_mask_password():
    manager = ProxyManager.from_env_string(
        "http://user:secret@proxy1:3128;socks5://proxy2:1080\nhttps://proxy3:8443",
        mode="failover",
    )
    assert manager.mode == ProxyMode.FAILOVER
    assert len(manager.proxies) == 3
    assert mask_proxy_url(manager.proxies[0]) == "http://user:***@proxy1:3128"


def test_failover_switches_after_failure():
    manager = ProxyManager(
        ["http://proxy1:3128", "http://proxy2:3128"],
        mode="failover",
    )
    assert manager.get_proxy() == "http://proxy1:3128"
    manager.mark_proxy_failed("http://proxy1:3128")
    assert manager.get_proxy() == "http://proxy2:3128"


def test_no_proxy_forces_off_mode():
    manager = ProxyManager([], mode="failover")
    assert manager.mode == ProxyMode.OFF
    assert manager.get_proxy() is None
