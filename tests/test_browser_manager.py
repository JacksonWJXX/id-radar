import base64
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import idradar.browser as browser_module
from idradar.browser import BrowserManager, PageQueryError
from idradar.platforms import bilibili, douyin, xiaohongshu
from idradar.platforms.bilibili import BilibiliChecker
from idradar.platforms.douyin import DouyinChecker
from idradar.platforms.xiaohongshu import XiaohongshuChecker
import idradar.platforms.login_search as login_search
from idradar.probe import capture_page

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==")


class FakeLocator:
    def __init__(self, context=None, selector=""):
        self.context, self.selector = context, selector

    async def count(self):
        return int(self.context is not None and any(part.strip() in self.context.visible_selectors for part in self.selector.split(",")))

    def nth(self, index): return self

    @property
    def first(self): return self

    async def is_visible(self): return bool(await self.count())

    async def bounding_box(self): return {"x": 100, "y": 80, "width": 600, "height": 400}

    async def click(self):
        self.context.clicks.append(self.selector)

    async def get_attribute(self, name):
        return self.context.attributes.get((self.selector, name))

    async def evaluate(self, expression): return True

    async def screenshot(self, **kwargs): return PNG


class FakeCDP:
    def __init__(self, context): self.context = context
    async def send(self, method, params=None):
        self.context.cdp_calls.append((method, params))
        return {"windowId": 1} if method == "Browser.getWindowForTarget" else {}
    async def detach(self): pass


class FakePage:
    def __init__(self, context):
        self.context = context
        self.url = "about:blank"
        self.closed = False
        self.screenshots = []

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True
        if self in self.context.pages:
            self.context.pages.remove(self)
        if not self.context.pages:
            await self.context.close()

    async def goto(self, url, **kwargs):
        self.url = url
        await asyncio.sleep(0)
        if self.context.fail_navigation:
            raise RuntimeError("假页面加载失败")

    def locator(self, selector):
        return FakeLocator(self.context, selector)

    async def content(self):
        return self.context.html

    async def screenshot(self, **kwargs):
        self.screenshots.append(kwargs)
        if "path" in kwargs:
            Path(kwargs["path"]).write_bytes(PNG)
        return PNG

    async def evaluate(self, expression): return {"width": 1920, "height": 1080}

    async def bring_to_front(self): self.context.brought_to_front.append(self)

    async def wait_for_load_state(self, *args, **kwargs):
        pass


class FakeContext:
    def __init__(self):
        self.pages = []
        self.closed = False
        self.handlers = []
        self.html = "<html><body>假页面</body></html>"
        self.fail_navigation = False
        self.session = {}
        self.attributes = {}
        self.visible_selectors, self.clicks, self.cdp_calls, self.brought_to_front = set(), [], [], []

    async def new_cdp_session(self, page): return FakeCDP(self)

    def on(self, event, handler):
        assert event == "close"
        self.handlers.append(handler)

    async def new_page(self):
        if self.closed:
            raise RuntimeError("上下文已关闭")
        page = FakePage(self)
        self.pages.append(page)
        return page

    async def close(self):
        if self.closed:
            return
        self.closed = True
        for page in self.pages:
            page.closed = True
        self.pages = []
        for handler in self.handlers:
            handler(self)

    async def cookies(self, url):
        if self.closed:
            raise RuntimeError("窗口已关闭")
        return self.session.get(url, [])


@pytest.fixture
def managed_browser(tmp_path, monkeypatch):
    contexts = []

    async def launch(*args, **kwargs):
        assert kwargs["headless"] is False
        context = FakeContext()
        contexts.append(context)
        return context

    playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=AsyncMock(side_effect=launch)), stop=AsyncMock())
    monkeypatch.setattr(browser_module, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=playwright)))
    manager = BrowserManager(tmp_path / "profile", tmp_path / "probe")
    return manager, contexts, playwright


async def test_channel_order_visible_without_downloading(tmp_path, monkeypatch):
    context = FakeContext()
    launch = AsyncMock(side_effect=[RuntimeError("没有 Edge"), RuntimeError("没有 Chrome"), context])
    playwright = SimpleNamespace(chromium=SimpleNamespace(launch_persistent_context=launch), stop=AsyncMock())
    monkeypatch.setattr(browser_module, "async_playwright", lambda: SimpleNamespace(start=AsyncMock(return_value=playwright)))
    manager = BrowserManager(tmp_path / "profile", tmp_path / "probe")
    try:
        assert await manager._launch() is context
        assert [call.kwargs["channel"] for call in launch.call_args_list] == ["msedge", "chrome", None]
        assert all(call.kwargs["headless"] is False for call in launch.call_args_list)
    finally:
        await manager.close()


async def test_two_login_tabs_and_queries_share_one_context(managed_browser):
    manager, contexts, _ = managed_browser
    try:
        await asyncio.gather(
            manager.open_login("douyin", douyin.LOGIN_URL, douyin.LOGGED_IN_SELECTOR, douyin.LOGIN_COOKIES),
            manager.open_login("xiaohongshu", xiaohongshu.LOGIN_URL, xiaohongshu.LOGGED_IN_SELECTOR, xiaohongshu.LOGIN_COOKIES),
        )
        assert len(contexts) == 1
        assert [page.url for page in contexts[0].pages] == [douyin.LOGIN_URL, xiaohongshu.LOGIN_URL]
        async with manager.page("bilibili") as page:
            assert page.context is contexts[0]
            assert len(contexts[0].pages) == 3
        assert len(contexts[0].pages) == 3
        async with manager.page("bilibili") as again:
            assert again is page
        assert manager.is_open
    finally:
        await manager.close()


async def test_cookie_refresh_and_reopen_after_window_close(managed_browser):
    manager, contexts, _ = managed_browser
    try:
        await manager.open_login("douyin", douyin.LOGIN_URL, douyin.LOGGED_IN_SELECTOR, douyin.LOGIN_COOKIES)
        first = contexts[0]
        first.session[douyin.LOGIN_URL] = [{"name": douyin.LOGIN_COOKIES[0], "value": "test-session"}]
        # 小红书给游客也发 web_session：有这个 Cookie 也不能算登录
        first.session[xiaohongshu.LOGIN_URL] = [{"name": "web_session", "value": "guest-session"}]
        await manager.refresh_login_status()
        assert manager.login_status == {"douyin": True, "xiaohongshu": None}
        await first.close()
        assert not manager.is_open
        assert manager.login_status == {"douyin": True, "xiaohongshu": None}
        async with manager.page("bilibili") as page:
            assert page.context is contexts[1]
        assert len(contexts) == 2 and manager.is_open
        assert contexts[1].pages
    finally:
        await manager.close()


async def test_failed_query_saves_html_and_full_page_png(managed_browser):
    manager, _, _ = managed_browser
    try:
        with pytest.raises(PageQueryError, match="已保存页面快照") as error:
            async with manager.page("bilibili") as page:
                raise RuntimeError("假查询失败")
        html = next(manager.probe_path.glob("bilibili-*.html"))
        png = html.with_suffix(".png")
        assert html.read_text(encoding="utf-8").startswith("<html>")
        assert png.read_bytes() == PNG
        assert page.screenshots[0]["full_page"] is True
        assert str(html.resolve()) in str(error.value) and str(png.resolve()) in str(error.value)
        assert "不会上传" in str(error.value)
    finally:
        await manager.close()


@pytest.mark.parametrize("navigation_failure", [False, True])
async def test_bilibili_errors_include_snapshot_paths(managed_browser, monkeypatch, navigation_failure):
    manager, contexts, _ = managed_browser
    monkeypatch.setattr(bilibili, "wait_for_visible", AsyncMock())
    try:
        async with manager.page() as page:
            context = page.context
            context.fail_navigation = navigation_failure
            context.html = "<div>未知页面结构</div>"
        result = await BilibiliChecker(manager).check("测试名字", "testname")
        assert result.status == "error"
        assert "已保存页面快照" in result.note and "账号信息" in result.note
        assert len(list(manager.probe_path.glob("*.html"))) == 1
        assert len(list(manager.probe_path.glob("*.png"))) == 1
    finally:
        await manager.close()


async def test_probe_uses_open_context_and_writes_two_files(managed_browser):
    manager, contexts, _ = managed_browser
    try:
        await manager.open_login("douyin", douyin.LOGIN_URL, douyin.LOGGED_IN_SELECTOR, douyin.LOGIN_COOKIES)
        html, png = await capture_page(manager, "douyin", "测试名字")
        assert html.exists() and png.exists()
        assert len(contexts) == 1 and len(contexts[0].pages) == 1
    finally:
        await manager.close()


@pytest.mark.parametrize("cls", [DouyinChecker])
async def test_login_platform_unknown_page_saves_snapshot(managed_browser, monkeypatch, cls):
    manager, contexts, _ = managed_browser
    checker = cls(manager)
    monkeypatch.setattr(login_search, "wait_for_visible", AsyncMock())
    try:
        async with manager.page() as page:
            page.context.session[checker.search_url("测试名字")] = [{"name": checker.login_cookies[0], "value": "test-session"}]
        result = await checker.check("测试名字", "testname")
        assert result.status == "error" and "已保存页面快照" in result.note
        # 认不出会重开页面再查一次，两次各存一份快照
        assert len(list(manager.probe_path.glob("*.html"))) == 2
        assert len(list(manager.probe_path.glob("*.png"))) == 2
    finally:
        await manager.close()


async def test_probe_cli_reuses_running_service(monkeypatch, tmp_path, capsys):
    import httpx
    import idradar.probe as probe_module

    original_client = httpx.AsyncClient

    def respond(request):
        assert str(request.url) == "http://127.0.0.1:8765/api/probe/douyin"
        return httpx.Response(200, json={"html": str(tmp_path / "probe.html"), "png": str(tmp_path / "probe.png"), "note": "文件只在本机，不会上传"})

    monkeypatch.setattr(probe_module.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    monkeypatch.setattr(probe_module, "BrowserManager", lambda: (_ for _ in ()).throw(AssertionError("不能再开第二个浏览器")))
    await probe_module.probe("douyin", "测试名字")
    assert "probe.png" in capsys.readouterr().out
