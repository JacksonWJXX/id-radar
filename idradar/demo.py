"""录屏演示隔离：不构造真实浏览器或查重器，不访问或写入用户历史。"""

from .i18n import t
from .platforms.base import Checker, Result

SAMPLES = {
    "zh": "```text\n造轮子百回 | wheelmaker\nAI包工头 | albertwu\n沈小艾在发呆 | aidreaming\n```",
    "en": "```text\nWheel Maker | wheelmaker\nAlex Builds | albertwu\nQuiet Dreamer | aidreaming\n```",
}


class DemoHistory:
    def append(self, record):
        pass

    def list(self):
        return []


class DemoBrowser:
    is_open = False
    login_status = {}

    async def close(self):
        pass


class DemoSites:
    """演示中的增删只放内存，不读用户文件。"""
    def __init__(self):
        self.records = []

    def list(self):
        return list(self.records)

    def add(self, label, url_template, kind):
        from uuid import uuid4
        from .custom_platforms import validate_site
        if len(self.records) >= 10:
            raise ValueError(t("site.limit"))
        site = {"id": "custom_" + uuid4().hex, **validate_site(label, url_template, kind)}
        self.records.append(site)
        return site

    def delete(self, id):
        remaining = [site for site in self.records if site["id"] != id]
        if len(remaining) == len(self.records):
            raise ValueError(t("site.missing"))
        self.records = remaining


class DemoChecker(Checker):
    def __init__(self, id, label, mode, site=None):
        self.id, self.label, self.mode = id, label, mode
        self.custom = site is not None
        self.kind = site["kind"] if site else ""
        self.url_template = site["url_template"] if site else ""

    async def check(self, name, handle):
        status = "manual" if self.mode == "manual" else "available"
        if self.id == "github" and handle == "albertwu":
            status = "taken"
        elif (self.id == "x" and handle in ("aidreaming", "albertwu")) or (self.id == "bilibili" and (handle == "aidreaming" or name in ("AI包工头", "Alex Builds"))):
            status = "similar"
        return Result(status, [{"name": "sample_account", "url": "https://example.test/profile", "extra": t("demo.extra")}] if status in ("taken", "similar") else [],
                      "https://example.test/search", t("demo.note"))


def demo_checkers():
    from .i18n import platform_label
    return {id: DemoChecker(id, platform_label(id), "manual" if id == "weixin_channels" else "auto")
            for id in ("bilibili", "github", "douyin", "xiaohongshu", "x", "weixin_channels")}
