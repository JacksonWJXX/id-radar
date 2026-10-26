"""有界面的屏幕外专用窗口，每个平台复用一个固定标签页。"""

import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
import re
from urllib.parse import urlsplit
from uuid import uuid4

from playwright.async_api import async_playwright


from .i18n import t

class PageQueryError(RuntimeError):
    """查询页面失败，附上本机快照说明。"""


class BrowserManager:
    def __init__(self, profile_path=None, probe_path=None):
        from .platforms import douyin, xiaohongshu

        self.profile_path = Path(profile_path) if profile_path else Path.home() / ".idradar" / "browser-profile"
        self.probe_path = Path(probe_path) if probe_path else Path(__file__).resolve().parents[1] / "probe"
        self.login_status = {"douyin": None, "xiaohongshu": None}
        self._targets = {module_id: (module.LOGIN_URL, module.LOGGED_IN_SELECTOR, module.LOGIN_COOKIES, module.LOGIN_SELECTOR)
                         for module_id, module in (("douyin", douyin), ("xiaohongshu", xiaohongshu))}
        self._playwright = None
        self._context = None
        self._lock = asyncio.Lock()
        self._status_task = None
        self._startup_pages = []
        self._pages = {}
        self._page_locks = {}
        self.window_visible = False

    async def _launch(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        self.profile_path.mkdir(parents=True, exist_ok=True)
        for channel in ("msedge", "chrome", None):
            try:
                return await self._playwright.chromium.launch_persistent_context(
                    str(self.profile_path), channel=channel, headless=False,
                    args=["--window-position=-32000,-32000", "--window-size=1280,900"],
                    viewport={"width": 1280, "height": 900}, locale="zh-CN",
                )
            except Exception:
                continue
        raise ValueError(t('browser.launch'))

    async def _ensure_locked(self):
        if self._context is not None:
            return self._context
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
            await asyncio.gather(self._status_task, return_exceptions=True)
        context = await self._launch()
        self._context = context
        self._pages.clear()
        self.window_visible = False
        self._startup_pages = list(context.pages)
        closed = asyncio.Event()

        def on_close(*args):
            closed.set()
            if self._context is context:
                self._context = None
                self._pages.clear()
                self.window_visible = False

        context.on("close", on_close)
        self._status_task = asyncio.create_task(self._watch_status(context, closed))
        return context

    async def _new_page(self, platform="probe"):
        async with self._lock:
            for attempt in range(2):
                context = await self._ensure_locked()
                try:
                    cached = self._pages.get(platform)
                    if cached is not None and not cached.is_closed():
                        return cached
                    page = await context.new_page()
                    self._pages[platform] = page
                    # 第一个业务标签页建好后，才关闭本次启动自带的空白页。
                    for blank in self._startup_pages:
                        if not blank.is_closed() and blank.url == "about:blank":
                            await blank.close()
                    self._startup_pages = []
                    return page
                except Exception:
                    try:
                        await context.close()
                    except Exception:
                        pass
                    if self._context is context:
                        self._context = None
                    if attempt:
                        raise ValueError(t('browser.tab')) from None

    @asynccontextmanager
    async def page(self, platform=None):
        async with self._page_locks.setdefault(platform, asyncio.Lock()):
            page = await self._new_page(platform or "probe")
            try:
                yield page
            except Exception:
                if platform:
                    raise PageQueryError(await self.snapshot_note(page, platform)) from None
                raise

    async def show_window(self, platform):
        page = await self._new_page(platform)
        session = await page.context.new_cdp_session(page)
        try:
            info = await session.send("Browser.getWindowForTarget")
            screen = await page.evaluate("({width: screen.availWidth, height: screen.availHeight})")
            width, height = min(1280, screen["width"]), min(900, screen["height"])
            await session.send("Browser.setWindowBounds", {"windowId": info["windowId"], "bounds": {"windowState": "normal"}})
            await session.send("Browser.setWindowBounds", {"windowId": info["windowId"], "bounds": {
                "left": max(0, (screen["width"] - width) // 2), "top": max(0, (screen["height"] - height) // 2), "width": width, "height": height}})
            await page.bring_to_front()
            self.window_visible = True
        finally:
            await session.detach()

    def has_page(self, platform):
        page = self._pages.get(platform)
        return self._context is not None and page is not None and not page.is_closed()

    async def verification_present(self, platform):
        """只读取固定标签页上已有的验证标记，不点击、不刷新页面。"""
        from .platforms import bilibili, douyin, xiaohongshu
        from .platforms.login_search import visible

        if not self.has_page(platform):
            return None
        page = self._pages[platform]
        if not page.url.startswith("https://"):
            return None
        module = {"bilibili": bilibili, "douyin": douyin, "xiaohongshu": xiaohongshu}.get(platform)
        if module is None:
            return None
        if await visible(page, module.BLOCKED_SELECTOR):
            return True
        if platform == "bilibili":
            return bilibili.parse_html(await page.content(), "").status == "blocked"
        return False

    async def hide_window(self, platform):
        if self._context is None:
            self.window_visible = False
            return
        page = self._pages.get(platform)
        if page is None or page.is_closed():
            page = next((item for item in self._context.pages if not item.is_closed()), None)
        if page is None:
            return
        session = await self._context.new_cdp_session(page)
        try:
            info = await session.send("Browser.getWindowForTarget")
            await session.send("Browser.setWindowBounds", {"windowId": info["windowId"], "bounds": {"windowState": "normal"}})
            await session.send("Browser.setWindowBounds", {"windowId": info["windowId"], "bounds": {"left": -32000, "top": -32000}})
            self.window_visible = False
        finally:
            await session.detach()

    async def open_login(self, platform, url, logged_in_selector, login_cookies=()):
        from .platforms import douyin, xiaohongshu
        module = {"douyin": douyin, "xiaohongshu": xiaohongshu}[platform]
        async with self._page_locks.setdefault(platform, asyncio.Lock()):
            self._targets[platform] = (url, logged_in_selector, login_cookies, module.LOGIN_SELECTOR)
            page = await self._new_page(platform)
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                note = await self.snapshot_note(page, platform)
                raise ValueError(t('browser.login') + note) from None
            await self.refresh_login_status()
            return page

    async def refresh_login_status(self, context=None):
        from .platforms.login_search import detect_login, has_login_cookie

        context = context or self._context
        if context is None:
            return
        for platform, (url, selector, cookies, login_selector) in tuple(self._targets.items()):
            state = True if await has_login_cookie(context, url, cookies) else None
            seen_page = False
            for page in context.pages:
                try:
                    if urlsplit(page.url).hostname == urlsplit(url).hostname:
                        seen_page = True
                        observed = await detect_login(page, url, selector, login_selector, cookies)
                        if observed is not None:
                            state = observed
                except Exception:
                    continue
            # 没有可判断的 Cookie、也没开着该平台页面时无从判断，保留上次查询得到的状态
            if not cookies and not seen_page:
                continue
            if self._context is context:
                self.login_status[platform] = state

    async def _watch_status(self, context, closed):
        while not closed.is_set() and self._context is context:
            try:
                await self.refresh_login_status(context)
            except Exception:
                pass
            try:
                await asyncio.wait_for(closed.wait(), timeout=2)
            except TimeoutError:
                pass

    async def save_snapshot(self, page, platform):
        self.probe_path.mkdir(parents=True, exist_ok=True)
        prefix = re.sub(r"[^a-zA-Z0-9_-]", "_", platform)
        stem = f"{prefix}-{datetime.now():%Y%m%d-%H%M%S-%f}-{uuid4().hex[:6]}"
        html = (self.probe_path / (stem + ".html")).resolve()
        png = (self.probe_path / (stem + ".png")).resolve()

        async def save_html():
            html.write_text(await page.content(), encoding="utf-8")

        results = await asyncio.gather(save_html(), page.screenshot(path=str(png), full_page=True, timeout=10000), return_exceptions=True)
        if any(isinstance(result, BaseException) for result in results):
            raise OSError(t('snapshot.incomplete'))
        return html, png

    async def snapshot_note(self, page, platform):
        try:
            html, png = await self.save_snapshot(page, platform)
            return t('snapshot.saved', html=html, png=png)
        except Exception:
            return t('snapshot.failed', path=self.probe_path.resolve())

    async def record_error(self, page, platform, result):
        if result.status == "error":
            result.note += " " + await self.snapshot_note(page, platform)
        return result

    @property
    def is_open(self):
        return self._context is not None

    async def close(self):
        if self._status_task and not self._status_task.done():
            self._status_task.cancel()
            await asyncio.gather(self._status_task, return_exceptions=True)
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None
