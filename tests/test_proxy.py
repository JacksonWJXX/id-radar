import httpx
import os
import pytest

from idradar import proxy
from idradar.i18n import LANG
from idradar.platforms.github import GitHubChecker
from idradar.platforms.x import XChecker
from idradar.platforms.custom import CustomChecker


def test_reads_real_environment_keys_with_monkeypatch(monkeypatch):
    for key in list(os.environ):
        if key.lower().endswith("_proxy"):
            monkeypatch.delenv(key)
    monkeypatch.setenv("HTTPS_PROXY", "http://environment.test:8118")
    monkeypatch.setenv("NO_PROXY", "bypass.test")
    monkeypatch.setattr(proxy.urllib.request, "getproxies", lambda: {"https": "http://system.test:7890"})
    assert proxy.proxy_for("https://x.com/name") == "http://environment.test:8118"
    assert proxy.proxy_for("https://bypass.test/name") is None


def test_environment_proxy_takes_priority(monkeypatch):
    monkeypatch.setattr(proxy.urllib.request, "getproxies_environment", lambda: {"https": "http://environment.test:7890", "no": "bypass.test"})
    monkeypatch.setattr(proxy.urllib.request, "getproxies", lambda: {"https": "http://system.test:7890"})
    assert proxy.proxy_for("https://x.com/name") == "http://environment.test:7890"
    assert proxy.proxy_for("https://bypass.test/name") is None
    assert proxy.proxy_for("http://127.0.0.1/profile") is None


def test_windows_getproxies_and_bare_host(monkeypatch):
    monkeypatch.setattr(proxy, "WINDOWS", True)
    monkeypatch.setattr(proxy.urllib.request, "getproxies_environment", lambda: {})
    calls = []
    monkeypatch.setattr(proxy.urllib.request, "getproxies", lambda: calls.append(True) or {"https": "127.0.0.1:7890"})
    assert proxy.proxy_for("https://x.com/name") == "http://127.0.0.1:7890"
    assert calls == [True]


def test_httpx_receives_explicit_proxy(monkeypatch):
    monkeypatch.setattr(proxy, "proxy_for", lambda url: "http://proxy.test:7890")
    monkeypatch.setattr(proxy.httpx, "AsyncClient", lambda **kwargs: kwargs)
    assert proxy.http_client("https://github.com", timeout=20) == {"proxy": "http://proxy.test:7890", "trust_env": False, "timeout": 20, "follow_redirects": True}


@pytest.mark.parametrize("platform", ["github", "x", "custom"])
async def test_bad_proxy_initialization_also_gets_friendly_note(monkeypatch, platform):
    from idradar.platforms import github, x, custom
    module = {"github": github, "x": x, "custom": custom}[platform]
    def fail(*args, **kwargs):
        raise httpx.ProxyError("invalid proxy")
    monkeypatch.setattr(module, "http_client", fail)
    checker = GitHubChecker() if platform == "github" else XChecker() if platform == "x" else CustomChecker({"id": "custom_test", "label": "Example", "kind": "profile", "url_template": "https://example.test/{handle}"})
    result = await checker.check("Name", "toolman")
    assert result.status == "error" and "代理" in result.note


@pytest.mark.parametrize("lang", ["zh", "en"])
@pytest.mark.parametrize("platform,domain", [("github", "api.github.com"), ("x", "x.com"), ("custom", "example.test")])
async def test_connection_failures_explain_proxy(lang, platform, domain):
    def fail(request):
        raise httpx.ConnectError("offline", request=request)
    token = LANG.set(lang)
    try:
        async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
            checker = GitHubChecker(client) if platform == "github" else XChecker(client) if platform == "x" else CustomChecker({"id": "custom_test", "label": "Example", "kind": "profile", "url_template": "https://example.test/{handle}"}, client)
            result = await checker.check("Name", "toolman")
        assert result.status == "error" and domain in result.note
        assert ("代理" if lang == "zh" else "proxy") in result.note
    finally:
        LANG.reset(token)
