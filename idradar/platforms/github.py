"""GitHub 只查 handle，不按中文昵称搜索。"""

from urllib.parse import quote

import httpx

from ..i18n import t
from .base import Checker, Result
from ..rules import check_name
from ..proxy import http_client


def valid_handle(handle: str) -> bool:
    return check_name("github", handle)["verdict"] == "ok"


class GitHubChecker(Checker):
    id, label, mode = "github", t('platform.github'), "auto"

    def __init__(self, client=None):
        self.client = client

    async def check(self, name, handle):
        url = "https://github.com/" + quote(handle, safe="") if handle else "https://github.com"
        validation = check_name(self.id, handle)
        if validation["verdict"] == "bad":
            return Result("invalid", search_url=url, note="；".join(validation["reasons"]))
        client = self.client
        try:
            client = client or http_client("https://api.github.com", timeout=20)
            response = await client.get("https://api.github.com/users/" + handle, headers={"Accept": "application/vnd.github+json", "User-Agent": "id-radar/0.1"})
            if response.status_code == 404:
                return Result("available", search_url=url, note=t('github.available'))
            if response.status_code == 200:
                data = response.json()
                return Result("taken", [{"name": data.get("login", handle), "url": url, "extra": "GitHub handle"}], url, t('github.taken'))
            if response.status_code in (403, 429):
                return Result("blocked", search_url=url, note=t('github.blocked'))
            return Result("error", search_url=url, note=t('github.http', status=response.status_code))
        except (httpx.ConnectError, httpx.TimeoutException, httpx.ProxyError):
            return Result("error", search_url=url, note=t("connect", platform=self.label, domain="api.github.com"))
        except (httpx.HTTPError, ValueError, TypeError, AttributeError):
            return Result("error", search_url=url, note=t('github.error'))
        finally:
            if self.client is None and client is not None:
                await client.aclose()
