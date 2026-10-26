"""本机 Edge + 假平台验证方案 A、平台管理、自动分批与 ID 方案卡。"""

import asyncio
import base64
import math
import os
from pathlib import Path
import socket
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
from playwright.async_api import async_playwright
import uvicorn
from fastapi.responses import JSONResponse

from idradar.parse_names import HANDLE_PROMPT, NAMING_PROMPT
from idradar.custom_platforms import CustomPlatformStore
from idradar.history import HistoryStore
from idradar.platforms.base import Checker, Result
from idradar.platforms.weixin_channels import WeixinChannelsChecker
from idradar.server import create_app
from idradar.i18n import platform_label, t
from idradar.prompts import NAMING_PROMPT_EN

ARTIFACTS = Path(__file__).resolve().parents[1] / ".test-artifacts" / "ui"


class FakeChecker(Checker):
    def __init__(self, id, label, mode):
        self.id, self.label, self.mode = id, label, mode
        self.calls = []
        self.challenge_done = False

    async def check(self, name, handle):
        await asyncio.sleep(0.3 if name.startswith("停止样本") else 0.02)
        self.calls.append((name, handle))
        status = "available"
        if self.id == "xiaohongshu" and name == "验证样本" and not self.challenge_done:
            self.challenge_done = True
            return Result("blocked", note=t("search.blocked", platform=self.label, note=""))
        if self.id == "bilibili" and name == "AI包工头":
            status = "taken"
        if (self.id == "bilibili" and name in {"备选" + str(i) for i in range(5)}) or (self.id == "github" and handle in {"candidate" + str(i) for i in range(5)}):
            status = "taken"
        elif self.id == "github" and (handle == "albertwu" or (name.startswith("AI包工头") and not handle[-1:].isdigit())):
            status = "taken"
        return Result(status, [{"name": "Ai包工头", "url": "https://example.test/account", "extra": "离线样本"}] if status == "taken" else [],
                      "https://example.test/search", t("demo.note"))


class FakeBrowser:
    is_open = False
    def __init__(self):
        self.login_status = {"douyin": None, "xiaohongshu": None}
        self.window_visible = False
        self.verifying = set()
    async def show_window(self, platform): self.window_visible = True
    async def hide_window(self, platform): self.window_visible = False
    async def verification_present(self, platform): return platform in self.verifying
    async def close(self): pass


class FakeLoginManager:
    def __init__(self, browser):
        self.browser, self.sessions, self.versions, self.completed = browser, {}, {}, set()
        image = (ARTIFACTS.parents[1] / "tests" / "fixtures" / "qr_mock.svg").read_bytes()
        self.image = "data:image/svg+xml;base64," + base64.b64encode(image).decode("ascii")
    def payload(self, platform):
        session = self.sessions[platform]
        remaining = max(0, math.ceil(session["deadline"] - time.monotonic()))
        status = "logged_in" if platform in self.completed else "qr" if remaining else "expired"
        if status == "logged_in": self.browser.login_status[platform] = True
        return {"session_id": session["session_id"], "platform": platform, "status": status, "qr_image": self.image if status == "qr" else "", "expires_in": remaining,
                "logged_in": self.browser.login_status[platform], "note": t("qr.success") if status == "logged_in" else t("qr.scan", platform=platform_label(platform))}
    async def start(self, platform):
        version = self.versions[platform] = self.versions.get(platform, 0) + 1
        self.completed.discard(platform)
        self.sessions[platform] = {"session_id": str(version), "deadline": time.monotonic() + (4 if version == 1 else 120)}
        return self.payload(platform)
    async def status(self, platform): return self.payload(platform)
    async def finish_fallback(self, platform): return self.payload(platform)
    async def cancel(self, platform): self.sessions.pop(platform, None)


async def poll(predicate, message, attempts=150):
    # CSP 禁止动态代码求值；所有等待都用普通轮询。
    for _ in range(attempts):
        if await predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError(message)


async def enabled(page, selector):
    async def ready():
        button = page.locator(selector)
        return await button.is_enabled() and (selector != "#start-check" or await button.get_attribute("aria-busy") != "true")
    await poll(ready, selector + " 一直不可用")


async def clipboard(page):
    return (await page.evaluate("navigator.clipboard.readText()")).replace("\r\n", "\n")


async def run_checks(page, context, url, sites, checkers):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    await page.goto(url)
    await enabled(page, "#copy-prompt")
    assert await page.locator("#naming-prompt").input_value() == NAMING_PROMPT
    await page.locator("#copy-prompt").click()
    assert await clipboard(page) == NAMING_PROMPT
    await page.locator("#names-input").fill("造轮子百回 | zaolunzi\nAI包工头 | albertwu")
    await page.locator("#parse-names").click()
    await page.locator(".candidate").nth(1).wait_for()
    assert await page.locator(".candidate-checkbox:checked").count() == 2
    handle = page.get_by_role("textbox", name="AI包工头 的英文 handle", exact=True)
    await handle.fill("")
    await page.locator("#handle-help").wait_for(state="visible")
    assert await handle.get_attribute("placeholder") == "缺 handle，点击填写"
    await page.locator("#copy-handle-prompt").click()
    assert await clipboard(page) == HANDLE_PROMPT + "\nAI包工头"
    await page.locator("#names-input").fill("AI包工头 | albertwu")
    await page.locator("#parse-names").click()
    await page.get_by_text("识别到 1 个名字：新增 0 个，更新 handle 1 个", exact=True).wait_for()
    await enabled(page, "#parse-names")

    await page.get_by_role("button", name="移除平台 小红书", exact=True).click()
    assert await page.locator("#remove-dialog").is_visible()
    assert await page.locator("#platforms").get_by_role("button", name="小红书", exact=True).count() == 1
    assert await page.locator('.remove-platform[aria-label="移除平台 小红书"] svg').count() == 1
    await page.screenshot(path=str(ARTIFACTS / "remove-confirm.png"), full_page=True)
    await page.locator("#cancel-remove").click()
    await page.get_by_role("button", name="移除平台 小红书", exact=True).click()
    await page.locator("#confirm-remove").click()
    await page.locator("#platforms").get_by_role("button", name="小红书", exact=True).wait_for(state="detached")
    assert "xiaohongshu" in await page.evaluate("localStorage.getItem('idradar.hidden.zh')")
    await page.locator("#restore-platforms").get_by_role("button", name="小红书", exact=True).click()

    # 添加两种网站，核对间距、规则和搜索页直链。
    for label, template, kind in (("示例主页", url + "/preview/{handle}", "profile"), ("示例搜索", "https://example.test/?q={name}", "search")):
        await page.get_by_role("button", name="+ 添加网站", exact=True).click()
        await page.locator("#site-label").fill(label)
        await page.locator("#site-url").fill(template)
        await page.locator(f'input[name="kind"][value="{kind}"]').check()
        await page.locator("#save-site").click()
        await page.locator("#custom-site-form").wait_for(state="hidden")
    custom_ids = [site["id"] for site in sites.list()]
    await page.locator("#open-rules").click()
    await page.locator(".rules-table tbody tr").nth(7).wait_for()
    assert "自定义网站，规则未知" in await page.locator("#rules-content").inner_text()
    await page.locator("#close-rules").click()
    await page.locator("#start-check").click()
    await enabled(page, "#start-check")
    assert await page.locator(f'td[data-cell="0:{custom_ids[0]}"] .available').count() == 1
    assert await page.locator(f'td[data-cell="0:{custom_ids[1]}"] a').get_attribute("target") == "_blank"
    await page.screenshot(path=str(ARTIFACTS / "custom-sites.png"), full_page=True)
    delete = page.get_by_role("button", name="删除网站 示例主页", exact=True)
    await delete.click()
    assert "这个网站的设置会被删除" in await page.locator("#remove-dialog").inner_text()
    assert len(sites.list()) == 2
    await page.locator("#cancel-remove").click()
    for label in ("示例主页", "示例搜索"):
        await page.get_by_role("button", name=f"删除网站 {label}", exact=True).click()
        await page.locator("#confirm-remove").click()
        await page.locator("#platforms").get_by_role("button", name=label, exact=True).wait_for(state="detached")
    assert sites.list() == []

    # 只选 B站、GitHub、X，使统一推荐能够被假平台确认。
    for label in ("抖音", "小红书", "视频号"):
        button = page.locator("#platforms").get_by_role("button", name=label, exact=True)
        if await button.get_attribute("aria-pressed") == "true":
            await button.click()
    await page.locator("#start-check").click()
    await enabled(page, "#start-check")
    panel = page.locator('.recommendation-row[data-row="1"]')
    await panel.locator(".adopt-unified").wait_for()
    assert await panel.locator(".adopt-partial").is_enabled() and await panel.locator(".adopt-unified").is_enabled()
    assert "已自动查了 2 个变体" in await panel.inner_text()
    assert await page.locator(".find-variants, .variant-panel").count() == 0
    await page.screenshot(path=str(ARTIFACTS / "recommendations-desktop.png"), full_page=True)
    await page.screenshot(path=str(ARTIFACTS / "desktop.png"), full_page=True)

    await panel.locator(".adopt-partial").click()
    assert await page.locator('.result-row[data-row="1"] .final-use').count() == 3
    assert "AI包工头本人" in await page.locator("#id-plan").inner_text()
    await page.locator(".copy-plan").click()
    assert await clipboard(page) == "B站：AI包工头本人\nGitHub：albertwu001\nX：albertwu"
    assert await page.locator('#id-plan a[href="https://github.com/settings/admin"]').count() == 1
    await page.locator(".undo-adoption").click()
    await panel.locator(".adopt-unified").click()
    await page.locator(".copy-plan").click()
    assert await clipboard(page) == "B站：AI包工头001\nGitHub：albertwu001\nX：albertwu001"
    await page.locator("#copy-markdown").click()
    assert "最终用名" in await clipboard(page) and "AI包工头001" in await clipboard(page)
    async with page.expect_download() as download_info:
        await page.locator("#export-csv").click()
    await (await download_info.value).save_as(str(ARTIFACTS / "export.csv"))
    assert "最终用名" in (ARTIFACTS / "export.csv").read_text(encoding="utf-8-sig")
    await page.locator(".undo-adoption").click()
    await panel.locator(".more-variants").click()
    await enabled(page, "#start-check")
    assert "AI包工头Lab" in await panel.inner_text()
    await panel.get_by_role("button", name="复制给 AI 想同音变体的提示词", exact=True).click()
    assert await clipboard(page) == "帮我给AI包工头想 5 个同音字或中英混写的变体，每行一个，格式：名字 | handle"

    for width in (320, 375, 390, 768, 1440):
        await page.set_viewport_size({"width": width, "height": 900})
        assert await page.evaluate("document.documentElement.scrollWidth === innerWidth"), width
        if width == 390:
            columns = await panel.locator(".recommendation-cards").evaluate("node => getComputedStyle(node).gridTemplateColumns.split(' ').length")
            assert columns == 1
            await page.screenshot(path=str(ARTIFACTS / "recommendations-mobile.png"), full_page=True)
            await page.screenshot(path=str(ARTIFACTS / "mobile.png"), full_page=True)

    # 同一页面切换语言，保留候选、格子、推荐以及已采用的方案。
    await page.locator("#lang-en").click()
    await page.get_by_role("button", name="Copy prompt", exact=True).wait_for()
    async def english_prompt_ready():
        return await page.locator("#naming-prompt").input_value() == NAMING_PROMPT_EN
    await poll(english_prompt_ready, "英文提示词未更新")
    assert await page.locator("html").get_attribute("lang") == "en"
    assert await page.locator(".candidate").count() == 2
    assert await page.locator(".result-row").count() == 2
    assert await page.locator("#platforms .platform-option > .pill").all_text_contents() == ["GitHub", "X"]
    await panel.locator(".adopt-partial").click()
    assert "My ID plan" in await page.locator("#id-plan").inner_text()
    await page.locator(".copy-plan").click()
    assert (await clipboard(page)).startswith("Bilibili: ")
    await page.locator("#lang-zh").click()
    assert "我的 ID 方案" in await page.locator("#id-plan").inner_text()
    assert await page.locator(".final-use").count() == 3
    await page.locator("#lang-en").click()
    await page.locator(".undo-adoption").click()
    await page.locator("#open-rules").click()
    await page.get_by_text("Research notes", exact=True).wait_for()
    assert "Must be unique" in await page.locator("#rules-content").inner_text()
    await page.locator("#close-rules").click()
    await page.set_viewport_size({"width": 1440, "height": 1000})
    await page.screenshot(path=str(ARTIFACTS / "desktop-en.png"), full_page=True)
    await page.set_viewport_size({"width": 390, "height": 900})
    assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
    assert await panel.locator(".recommendation-cards").evaluate("node => getComputedStyle(node).gridTemplateColumns.split(' ').length") == 1
    await page.screenshot(path=str(ARTIFACTS / "mobile-en.png"), full_page=True)
    await page.locator("#lang-zh").click()
    await page.get_by_role("button", name="复制提示词", exact=True).wait_for()
    assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
    await page.screenshot(path=str(ARTIFACTS / "mobile-zh.png"), full_page=True)
    await page.set_viewport_size({"width": 1440, "height": 1000})
    await page.screenshot(path=str(ARTIFACTS / "desktop-zh.png"), full_page=True)
    # “就用它”只复制名字；名字旁的复制按钮同样复制
    await page.locator('.result-row[data-row="0"] .choose-original').click()
    assert await clipboard(page) == "造轮子百回"
    assert await page.locator('.result-row[data-row="0"] .choose-original').inner_text() == "已复制 ✓"
    await page.get_by_role("button", name="复制 handle " + await page.locator('.result-row[data-row="0"] .handle').inner_text(), exact=True).click()
    assert await clipboard(page) == await page.locator('.result-row[data-row="0"] .handle').inner_text()

    # 识别十二个默认只勾前十个，手动全选后第二批自动衔接。
    await page.locator("#select-none").click()
    await page.locator("#names-input").fill("\n".join(f"候选{i} | tool{i:03}" for i in range(12)))
    await page.locator("#parse-names").click()
    await page.get_by_text("识别到 12 个名字，已勾选前 10 个", exact=True).wait_for()
    assert await page.locator(".candidate-checkbox:checked").count() == 10
    await page.locator("#select-all").click()
    # 原先两张卡也被全选，手动取消，剩十二个。
    for name in ("造轮子百回", "AI包工头"):
        await page.get_by_role("checkbox", name="选择 " + name, exact=True).uncheck()
    assert await page.locator("#start-check").inner_text() == "先查前 10 个（剩 2 个下一批）"
    # SSE 流结束后浏览器拿不到响应体；改用下面的结果行数和每个平台的调用次数证明两批都查完了。
    await page.locator("#start-check").click()
    await enabled(page, "#start-check")
    assert await page.locator(".result-row").count() == 12
    assert await page.locator("#check-progress").inner_text() == "已完成 36/36 格"
    assert all(sum(name.startswith("候选") for name, _ in checker.calls) == 12 for checker in checkers.values() if isinstance(checker, FakeChecker) and checker.id in ("bilibili", "github", "x"))

    # 至少留下一个标签；重新加载后隐藏列表仍生效。
    for label in ("B站", "抖音", "小红书", "视频号", "X"):
        await page.get_by_role("button", name="移除平台 " + label, exact=True).click()
        await page.locator("#confirm-remove").click()
    assert await page.locator(".remove-platform").count() == 0
    await page.reload()
    await page.locator("#platforms").get_by_role("button", name="GitHub", exact=True).wait_for()
    assert await page.locator(".platform-option").count() == 1
    await page.locator("#history-menu summary").click()
    await page.locator(".history-item").first.click()
    assert await page.locator(".result-row").count() == 12
    assert not errors, errors
    print("中英即时切换、状态保留、英文默认平台、方案 A、分批、确认卡、方案卡及手机布局已验证。")
    print(f"截图与 CSV：{ARTIFACTS}")


async def until(predicate, seconds=5):
    # 点击后接口是异步的，轮询等状态变过来
    for _ in range(int(seconds * 10)):
        if predicate():
            return
        await asyncio.sleep(0.1)
    raise AssertionError("等待超时")


async def run_v5_checks(page, context, url, browser_state, checkers):
    for label in ("B站", "抖音", "小红书", "视频号", "X"):
        restore = page.locator("#restore-platforms").get_by_role("button", name=label, exact=True)
        if await restore.count(): await restore.click()
    for label in ("抖音", "小红书", "视频号"):
        button = page.locator("#platforms").get_by_role("button", name=label, exact=True)
        if await button.get_attribute("aria-pressed") == "true": await button.click()
    await page.locator("#select-none").click()
    await page.locator("#names-input").fill("\n".join(f"备选{i} | candidate{i}" for i in range(5)))
    await page.locator("#parse-names").click()
    await enabled(page, "#parse-names")
    await page.locator("#start-check").click()
    await enabled(page, "#start-check")
    assert await page.locator(".recommendation-row").count() == 3
    assert await page.locator(".recommended-badge").count() == 3
    assert await page.locator(".find-available").count() == 2
    assert await page.locator("#matrix .status .platform-icon img").count() == 15
    assert await page.locator("#platforms .platform-icon img").count() == 6
    assert await page.locator("#matrix th").first.evaluate("node => getComputedStyle(node).position") == "sticky"
    before = await page.locator("#matrix th").first.bounding_box()
    await page.locator("#matrix-scroll").evaluate("node => {node.scrollTop = 120}")
    after = await page.locator("#matrix th").first.bounding_box()
    assert abs(before["y"] - after["y"]) <= 1
    await page.locator("#matrix-scroll").evaluate("node => {node.scrollTop = 0}")
    await page.screenshot(path=str(ARTIFACTS / "v5-desktop-zh.png"), full_page=True)
    await page.locator('.result-row[data-row="3"] .find-available').click()
    await enabled(page, "#start-check")
    assert await page.locator(".recommendation-row").count() == 4
    assert await page.locator("#progress-bar").evaluate("node => node.value === node.max")

    # 假平台只在这个名字第一次请求时给验证，继续后同一格变可用。
    await page.locator("#select-none").click()
    await page.locator("#names-input").fill("验证样本 | verifyname")
    await page.locator("#parse-names").click()
    await enabled(page, "#parse-names")
    for label in ("B站", "GitHub", "X", "抖音", "小红书", "视频号"):
        button = page.locator("#platforms").get_by_role("button", name=label, exact=True)
        selected = await button.get_attribute("aria-pressed") == "true"
        if selected != (label == "小红书"): await button.click()
    browser_state.verifying.add("xiaohongshu")
    await page.locator("#start-check").click()
    await page.locator(".verification-card").wait_for()
    await until(lambda: browser_state.window_visible)
    # 验证窗口弹出时顶部也闪烁提示
    await page.locator("#verify-notice").wait_for(state="visible")
    assert "小红书要验证" in await page.locator("#verify-notice").inner_text()
    assert await page.locator("#verify-notice .login-pulse").evaluate("node => getComputedStyle(node).animationIterationCount") == "3"
    await page.screenshot(path=str(ARTIFACTS / "v5-verification.png"), full_page=True)
    browser_state.verifying.discard("xiaohongshu")
    await enabled(page, "#start-check")
    await until(lambda: not browser_state.window_visible)
    assert sum(name == "验证样本" for name, _ in checkers["xiaohongshu"].calls) == 2
    assert await page.locator(".verification-card").count() == 0
    await page.locator("#verify-notice").wait_for(state="hidden")

    # 二维码来自本机假图片；短倒计时后过期，刷新后用本机测试接口模拟扫码成功。
    group = page.locator("#platforms").get_by_role("button", name="小红书", exact=True).locator("..")
    await group.locator(".login-button").click()
    await page.locator(".qr-image").wait_for()
    assert not browser_state.window_visible
    await page.screenshot(path=str(ARTIFACTS / "v5-qr-zh.png"), full_page=True)
    await page.get_by_text("二维码过期了", exact=True).wait_for()
    await page.locator(".qr-refresh").click()
    await page.locator(".qr-image").wait_for()
    await context.request.post(url + "/preview/login/xiaohongshu/complete")
    await page.locator(".login-success").wait_for()
    await page.locator(".login-card").wait_for(state="detached")
    assert "已登录" in await group.inner_text()

    await context.request.post(url + "/preview/login/xiaohongshu/reset")
    await page.locator("#lang-en").click()
    await page.locator("#restore-platforms").get_by_role("button", name="Xiaohongshu (RED)", exact=True).click()
    group = page.locator("#platforms").get_by_role("button", name="Xiaohongshu (RED)", exact=True).locator("..")
    await group.locator(".login-button").click()
    await page.locator(".qr-image").wait_for()
    assert "Scan with the Xiaohongshu (RED) app" in await page.locator(".login-card").inner_text()
    await page.screenshot(path=str(ARTIFACTS / "v5-desktop-en.png"), full_page=True)
    for lang in ("en", "zh"):
        if lang == "zh": await page.locator("#lang-zh").click()
        await page.set_viewport_size({"width": 390, "height": 900})
        assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
        await page.screenshot(path=str(ARTIFACTS / f"v5-mobile-{lang}.png"), full_page=True)
    await page.locator(".qr-close").click()
    print("第五版确认、平台图标、吸顶、前三推荐、手动找变体、扫码过期/刷新/成功、验证继续和中英手机布局已验证。")


async def run_v6_checks(browser, url, browser_state, checkers):
    context = await browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    await context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url + "/") else route.abort())
    page = await context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    try:
        browser_state.login_status = {"douyin": None, "xiaohongshu": None}
        await page.goto(url)
        await page.locator("#login-notice").wait_for(state="visible")
        assert await page.locator(".login-pulse").evaluate("node => getComputedStyle(node).animationIterationCount") == "3"
        assert await page.locator(".notice-login").count() == 2
        await page.emulate_media(reduced_motion="reduce")
        assert await page.locator(".login-pulse").evaluate("node => getComputedStyle(node).animationName") == "none"
        await page.emulate_media(reduced_motion="no-preference")
        await page.screenshot(path=str(ARTIFACTS / "v6-login-notice-zh.png"), full_page=True)
        await page.locator(".notice-skip").click()
        await page.locator("#login-notice").wait_for(state="hidden")

        await page.locator("#names-input").fill("\n".join(f"停止样本{i} | stopname{i}" for i in range(12)))
        await page.locator("#parse-names").click()
        await enabled(page, "#parse-names")
        await page.locator("#select-all").click()
        # 先停一次，以十二行证明后续批次不会继续排请求。
        for label in ("B站", "GitHub", "X", "抖音", "小红书", "视频号"):
            button = page.locator("#platforms").get_by_role("button", name=label, exact=True)
            selected = await button.get_attribute("aria-pressed") == "true"
            if selected != (label in ("抖音", "GitHub")): await button.click()
        await page.locator("#start-check").click()
        await page.get_by_role("button", name="停止查重", exact=True).wait_for()
        await page.locator("#login-notice").wait_for(state="visible")
        await poll(lambda: page.locator("#matrix .status.available").count(), "没有完成第一个格子")
        await page.locator("#start-check").click()
        await enabled(page, "#start-check")
        await page.locator("#matrix .status.stopped").first.wait_for()
        await until(lambda: not browser_state.window_visible)
        async def stopped_history():
            data = await (await context.request.get(url + "/api/history")).json()
            return bool(data["history"] and data["history"][0].get("stopped"))
        await poll(stopped_history, "停止历史未保存")
        calls = sum(len(c.calls) for c in checkers.values() if isinstance(c, FakeChecker))
        await asyncio.sleep(0.5)
        assert calls == sum(len(c.calls) for c in checkers.values() if isinstance(c, FakeChecker))
        await page.screenshot(path=str(ARTIFACTS / "v6-stopped-zh.png"), full_page=True)
        await page.locator("#start-check").click()
        await enabled(page, "#start-check")
        assert await page.locator("#matrix .status.stopped").count() == 0
        assert await page.locator("#matrix .status.available").count() == 24

        # 提示条的登录按钮直接打开现有扫码流程，成功后实时移除对应平台。
        await page.locator(".notice-login").click()
        await page.locator(".qr-image").wait_for()
        await context.request.post(url + "/preview/login/douyin/complete")
        await page.locator(".login-success").wait_for()
        await page.locator("#login-notice").wait_for(state="hidden")
        await page.locator(".login-card").wait_for(state="detached")

        await page.locator("#lang-en").click()
        await page.locator("#login-notice").wait_for(state="hidden")
        await page.locator("#restore-platforms").get_by_role("button", name="Xiaohongshu (RED)", exact=True).click()
        await page.locator("#login-notice").wait_for(state="visible")
        assert "not signed in" in await page.locator("#login-notice").inner_text()
        await page.screenshot(path=str(ARTIFACTS / "v6-desktop-en.png"), full_page=True)
        await page.locator("#select-none").click()
        await page.locator("#names-input").fill("验证样本 | verifyname")
        await page.locator("#parse-names").click()
        await enabled(page, "#parse-names")
        for label in ("GitHub", "X"):
            button = page.locator("#platforms").get_by_role("button", name=label, exact=True)
            if await button.get_attribute("aria-pressed") == "true": await button.click()
        checkers["xiaohongshu"].challenge_done = False
        browser_state.verifying.add("xiaohongshu")
        await page.locator("#start-check").click()
        await until(lambda: browser_state.window_visible)
        await page.locator(".verification-card").wait_for()
        assert "will continue automatically" in await page.locator(".verification-card").inner_text()
        assert "needs verification" in await page.locator("#verify-notice").inner_text()
        await page.screenshot(path=str(ARTIFACTS / "v6-verification-en.png"), full_page=True)
        browser_state.verifying.discard("xiaohongshu")
        await until(lambda: not browser_state.window_visible)
        await enabled(page, "#start-check")
        assert await page.locator("#matrix .status.available").count() == 1
        for lang in ("en", "zh"):
            if lang == "zh": await page.locator("#lang-zh").click()
            await page.set_viewport_size({"width": 390, "height": 900})
            assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
            await page.screenshot(path=str(ARTIFACTS / f"v6-mobile-{lang}.png"), full_page=True)
        assert not errors, errors
        print("第六版：停止/重查、停止历史、提示条/减弱动画/扫码更新、中英手机布局已验证。")
    finally:
        await context.close()


async def run_demo_checks(browser):
    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(create_app(demo=True), host="127.0.0.1", port=port, log_level="warning", access_log=False))
    task = asyncio.create_task(server.serve())
    context = None
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        context = await browser.new_context(viewport={"width": 1440, "height": 1000}, locale="en-US")
        await context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url + "/") else route.abort())
        page = await context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        await page.goto(url)
        await page.get_by_role("button", name="Paste sample reply", exact=True).wait_for()
        await page.locator(".platform-option").nth(1).wait_for()
        assert await page.locator("#demo-badge").inner_text() == "Demo"
        assert await page.locator("#platforms .platform-option > .pill").all_text_contents() == ["GitHub", "X"]
        for lang in ("en", "zh"):
            if lang == "zh":
                await page.locator("#lang-zh").click()
                await page.get_by_role("button", name="粘贴示例回复", exact=True).wait_for()
            await enabled(page, "#copy-prompt")
            await page.locator("#paste-sample").click()
            assert await page.locator("#names-input").input_value()
            await page.locator("#parse-names").click()
            await enabled(page, "#parse-names")
            await page.locator("#start-check").click()
            await enabled(page, "#start-check")
            for status in ("taken", "similar", "available"):
                assert await page.locator("#matrix .status." + status).count() > 0
            assert await page.locator(".recommendation-row").count() > 0
            await page.set_viewport_size({"width": 390, "height": 900})
            assert await page.evaluate("document.documentElement.scrollWidth === innerWidth")
            await page.screenshot(path=str(ARTIFACTS / f"demo-{lang}-mobile.png"), full_page=True)
            await page.set_viewport_size({"width": 1440, "height": 1000})
            await page.screenshot(path=str(ARTIFACTS / f"demo-{lang}-desktop.png"), full_page=True)
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(url + "/api/history?lang=en")).json() == {"history": []}
        assert not errors, errors
        print("演示模式中英样本、占用/相近/可用状态、推荐行、手机布局和空历史已验证。")
    finally:
        if context:
            await context.close()
        server.should_exit = True
        await task


async def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    temp = ARTIFACTS / "browser-temp"
    temp.mkdir(exist_ok=True)
    os.environ["TEMP"] = os.environ["TMP"] = str(temp)
    history = HistoryStore(ARTIFACTS / "history.jsonl")
    history.path.unlink(missing_ok=True)
    sites = CustomPlatformStore(ARTIFACTS / "custom_platforms.json")
    sites.path.unlink(missing_ok=True)

    fake_browser = FakeBrowser()
    fake_logins = FakeLoginManager(fake_browser)
    checkers = {c.id: c for c in [FakeChecker("bilibili", "B站", "auto"), FakeChecker("github", "GitHub", "auto"), FakeChecker("douyin", "抖音", "login"), FakeChecker("xiaohongshu", "小红书", "login"), FakeChecker("x", "X", "auto"), WeixinChannelsChecker()]}
    app = create_app(history_store=history, browser=fake_browser, checkers=checkers, custom_store=sites, login_manager=fake_logins, runner_options={"interval": lambda: 0})

    @app.post("/preview/login/{platform}/{action}")
    async def preview_login(platform: str, action: str):
        if action == "complete":
            fake_logins.completed.add(platform)
        else:
            fake_logins.completed.discard(platform)
            fake_browser.login_status[platform] = None
        return {"ok": True}

    @app.get("/preview/{handle}")
    async def preview(handle: str):
        return JSONResponse({"handle": handle}, status_code=404)

    with socket.socket() as port_probe:
        port_probe.bind(("127.0.0.1", 0))
        port = port_probe.getsockname()[1]
    url = f"http://127.0.0.1:{port}"
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning", access_log=False))
    task = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            if task.done():
                await task
            await asyncio.sleep(0.05)
        async with httpx.AsyncClient(trust_env=False) as client:
            assert (await client.get(url + "/")).status_code == 200
            assert (await client.get(url + "/api/prompt")).json()["prompt"] == NAMING_PROMPT
        print(f"本机 HTTP 与提示词正常：{url}", flush=True)
        if "--serve-only" in sys.argv:
            await task
            return
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(channel="msedge", headless=True)
            try:
                context = await browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
                await context.grant_permissions(["clipboard-read", "clipboard-write"])
                await context.route("**/*", lambda route: route.continue_() if route.request.url.startswith(url + "/") else route.abort())
                await run_checks(await context.new_page(), context, url, sites, checkers)
                await run_v5_checks(context.pages[0], context, url, fake_browser, checkers)
                await context.close()
                await run_v6_checks(browser, url, fake_browser, checkers)
                await run_demo_checks(browser)
            finally:
                await browser.close()
    finally:
        server.should_exit = True
        await task


if __name__ == "__main__":
    asyncio.run(main())
