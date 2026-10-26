import asyncio

from idradar.platforms import douyin, xiaohongshu
from idradar.platforms.login_search import detect_login
from test_browser_manager import managed_browser


async def test_offscreen_launch_fixed_pages_and_window_controls(managed_browser):
    manager, contexts, playwright = managed_browser
    try:
        first = await manager.open_login("douyin", douyin.LOGIN_URL, douyin.LOGGED_IN_SELECTOR, douyin.LOGIN_COOKIES)
        async with manager.page("douyin") as page:
            assert page is first
            await page.goto(douyin.search_url("名字甲"))
        async with manager.page("douyin") as again:
            assert again is first and not again.is_closed()
        context = contexts[0]
        assert len(context.pages) == 1 and not context.cdp_calls
        options = playwright.chromium.launch_persistent_context.call_args.kwargs
        assert options["headless"] is False
        assert "--window-position=-32000,-32000" in options["args"]
        assert not any("AutomationControlled" in arg for arg in options["args"])
        await manager.show_window("douyin")
        assert manager.window_visible and context.brought_to_front == [first]
        bounds = [params["bounds"] for method, params in context.cdp_calls if method == "Browser.setWindowBounds"]
        assert bounds[-1]["left"] == 320 and bounds[-1]["top"] == 90
        await manager.hide_window("douyin")
        assert not manager.window_visible
        assert context.cdp_calls[-1][1]["bounds"] == {"left": -32000, "top": -32000}
    finally:
        await manager.close()


async def test_same_platform_page_lock_and_reopen(managed_browser):
    manager, contexts, _ = managed_browser
    active, peak, pages = 0, 0, []
    async def query():
        nonlocal active, peak
        async with manager.page("bilibili") as page:
            active += 1; peak = max(peak, active); pages.append(page)
            await asyncio.sleep(0)
            active -= 1
    try:
        await asyncio.gather(query(), query())
        assert peak == 1 and pages[0] is pages[1]
        await contexts[0].close()
        await query()
        assert len(contexts) == 2 and pages[-1] is not pages[0]
    finally:
        await manager.close()


async def test_login_states_require_evidence_and_keep_cc_cookie_fix(managed_browser):
    manager, contexts, _ = managed_browser
    try:
        await manager.open_login("xiaohongshu", xiaohongshu.LOGIN_URL, xiaohongshu.LOGGED_IN_SELECTOR, xiaohongshu.LOGIN_COOKIES)
        context = contexts[0]
        context.session[xiaohongshu.LOGIN_URL] = [{"name": "web_session", "value": "guest"}]
        await manager.refresh_login_status()
        assert manager.login_status["xiaohongshu"] is None
        context.visible_selectors.add(xiaohongshu.LOGGED_IN_SELECTOR)
        await manager.refresh_login_status()
        assert manager.login_status["xiaohongshu"] is True
        context.visible_selectors.add("#login-btn")
        await manager.refresh_login_status()
        assert manager.login_status["xiaohongshu"] is False
        context.visible_selectors.clear()
        await manager.refresh_login_status()
        assert manager.login_status["xiaohongshu"] is None
        # 没有该平台页面、又没有可靠 Cookie 规则时，保留 CC 指定的上次状态。
        manager.login_status["xiaohongshu"] = True
        manager._pages["xiaohongshu"].url = "about:blank"
        await manager.refresh_login_status()
        assert manager.login_status["xiaohongshu"] is True
        assert xiaohongshu.LOGIN_COOKIES == ()
        assert xiaohongshu.USER_TAB_SELECTOR == "#user.channel"
    finally:
        await manager.close()


async def test_verification_detection_reads_existing_tab_only(managed_browser):
    manager, contexts, _ = managed_browser
    try:
        assert await manager.verification_present("douyin") is None
        assert not contexts
        async with manager.page("douyin") as page:
            await page.goto(douyin.search_url("候选"))
        context = contexts[0]
        context.visible_selectors.add(douyin.BLOCKED_SELECTOR.split(",")[0].strip())
        assert await manager.verification_present("douyin") is True
        context.visible_selectors.clear()
        assert await manager.verification_present("douyin") is False
        assert len(context.pages) == 1 and not context.cdp_calls
        page.url = "about:blank"
        assert await manager.verification_present("douyin") is None
        await context.close()
        assert await manager.verification_present("douyin") is None
    finally:
        await manager.close()
