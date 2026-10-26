"""自定义网站的个人主页请求或手动搜索链接。"""

from urllib.parse import quote, urlsplit

import httpx

from ..i18n import t
from .base import Checker, Result
from ..proxy import http_client


class CustomChecker(Checker):
    custom = True

    def __init__(self, site, client=None):
        self.id, self.label = site["id"], site["label"]
        self.kind, self.url_template = site["kind"], site["url_template"]
        self.mode = "auto" if self.kind == "profile" else "manual"
        self.client = client

    def url(self, name, handle):
        return self.url_template.replace("{name}", quote(name, safe="")).replace("{handle}", quote(handle, safe=""))

    async def check(self, name, handle):
        url = self.url(name, handle)
        if self.kind == "search":
            return Result("manual", search_url=url, note=t('custom.search'))
        client = self.client
        try:
            client = client or http_client(url, timeout=10)
            response = await client.get(url, timeout=10, follow_redirects=True)
            if response.status_code == 404:
                return Result("available", search_url=url, note=t('custom.available'))
            if response.status_code == 200:
                return Result("taken", [{"name": handle or name, "url": url, "extra": t('custom.extra')}], url, t('custom.taken'))
            return Result("manual", search_url=url, note=t('custom.http', status=response.status_code))
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ProxyError):
            return Result("error", search_url=url, note=t("connect", platform=self.label, domain=urlsplit(url).hostname or ""))
        except (httpx.HTTPError, ValueError):
            return Result("manual", search_url=url, note=t('custom.error'))
        finally:
            if self.client is None and client is not None:
                await client.aclose()
