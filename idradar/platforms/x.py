"""X 只查 handle。

不登录时直接请求主页：账号存在返回 200，不存在返回 404（2026-10-26 实测）。
无头浏览器会被 X 拦截，所以这里用普通 HTTP 请求，不走共用浏览器。
"""

from urllib.parse import quote

import httpx

from ..i18n import t
from .base import Checker, Result
from ..rules import check_name
from ..proxy import http_client

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"


def search_url(handle):
    return "https://x.com/" + quote(handle, safe="")


class XChecker(Checker):
    id, label, mode = "x", t('platform.x'), "auto"

    def __init__(self, client=None):
        self.client = client

    async def check(self, name, handle):
        url = search_url(handle) if handle else "https://x.com"
        validation = check_name(self.id, handle)
        if validation["verdict"] == "bad":
            return Result("invalid", search_url=url, note="；".join(validation["reasons"]))
        client = self.client
        try:
            client = client or http_client(url, timeout=20)
            response = await client.get(url, headers={"User-Agent": USER_AGENT})
            if response.status_code == 404:
                return Result("available", search_url=url, note=t('x.available'))
            if response.status_code == 200:
                return Result("taken", [{"name": "@" + handle, "url": url, "extra": "X handle"}], url,
                              t('x.taken'))
            if response.status_code in (403, 429):
                return Result("blocked", search_url=url, note=t('x.blocked'))
            return Result("error", search_url=url, note=t('x.http', status=response.status_code))
        except httpx.HTTPError:
            return Result("error", search_url=url, note=t("connect", platform=self.label, domain="x.com"))
        finally:
            if self.client is None and client is not None:
                await client.aclose()
