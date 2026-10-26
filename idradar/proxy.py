"""HTTP 查询显式使用环境变量或 Windows 系统代理，并尊重绕过列表。"""

import os
from urllib.parse import urlsplit
import urllib.request

import httpx

WINDOWS = os.name == "nt"


def system_proxies():
    environment = urllib.request.getproxies_environment()
    system = urllib.request.getproxies() if WINDOWS else {}
    return {**system, **environment}


def proxy_for(url):
    proxies = system_proxies()
    parsed = urlsplit(url)
    if parsed.hostname in ("127.0.0.1", "localhost", "::1") or urllib.request.proxy_bypass_environment(parsed.hostname or "", proxies):
        return None
    value = proxies.get(parsed.scheme) or proxies.get("all")
    return (value if "://" in value else "http://" + value) if value else None


def http_client(url, *, timeout):
    try:
        return httpx.AsyncClient(proxy=proxy_for(url), trust_env=False, timeout=timeout, follow_redirects=True)
    except (ValueError, ImportError) as error:
        raise httpx.ProxyError("The configured proxy could not be initialized.") from error
