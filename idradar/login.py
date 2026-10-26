"""只截取页面上已显示的二维码；取不到则交回普通窗口登录。"""

import asyncio
import base64
import math
import time
from uuid import uuid4

from .i18n import platform_label, t
from .platforms import douyin, xiaohongshu
from .platforms.login_search import visible, wait_for_visible

MODULES = {"douyin": douyin, "xiaohongshu": xiaohongshu}
# 两个平台的二维码都是页面上的 <img>，加载完成后 src 就是 data:image/png（CC 2026-10-26 实测）。
# 要等图片真正加载出来再取，太早取到的是空白占位（用户实测小红书出现过）。
QR_IMAGES = {"xiaohongshu": "img.qrcode-img", "douyin": 'img[aria-label="二维码"]'}
QR_WAIT = 15
QR_LIFETIME = 120


class LoginManager:
    def __init__(self, browser, clock=time.monotonic, qr_wait=QR_WAIT):
        self.browser, self.clock, self.qr_wait = browser, clock, qr_wait
        self.sessions = {}
        self.locks = {}

    async def capture_qr(self, platform, page):
        selector = QR_IMAGES.get(platform)
        if not selector:
            return None
        if platform == "xiaohongshu" and await visible(page, "#login-btn") and not await visible(page, ".login-container"):
            await page.locator("#login-btn").first.click()
        # 按次数等，不用 self.clock：测试会注入不走的假时钟
        for attempt in range(max(1, int(self.qr_wait / 0.3))):
            # 出现验证就不当二维码，交回窗口让用户自己处理。
            if await visible(page, MODULES[platform].BLOCKED_SELECTOR):
                return None
            image = page.locator(selector).first
            if await image.count() and await image.is_visible() and await image.evaluate("img => img.complete && img.naturalWidth > 0"):
                src = await image.get_attribute("src") or ""
                if src.startswith("data:image/"):
                    return src
                # 只取页面上已显示的图片，不下载、不生成、不解码二维码。
                return "data:image/png;base64," + base64.b64encode(await image.screenshot(type="png")).decode("ascii")
            await asyncio.sleep(0.3)
        return None

    def payload(self, platform):
        session = self.sessions.get(platform)
        if not session:
            raise ValueError(t("qr.missing"))
        remaining = max(0, math.ceil(session["deadline"] - self.clock()))
        if session["status"] == "qr" and not remaining:
            session["status"], session["qr_image"], session["note"] = "expired", "", t("qr.expired")
        return {key: value for key, value in session.items() if key != "deadline"} | {
            "expires_in": remaining, "logged_in": self.browser.login_status.get(platform)}

    async def start(self, platform):
        module = MODULES.get(platform)
        if not module:
            raise ValueError(t("qr.unsupported"))
        async with self.locks.setdefault(platform, asyncio.Lock()):
            page = await self.browser.open_login(platform, module.LOGIN_URL, module.LOGGED_IN_SELECTOR, module.LOGIN_COOKIES)
            session = {"session_id": uuid4().hex, "platform": platform, "status": "qr", "qr_image": "",
                       "deadline": self.clock() + QR_LIFETIME, "note": t("qr.scan", platform=platform_label(platform))}
            self.sessions[platform] = session
            if self.browser.login_status.get(platform) is True:
                session["status"], session["note"] = "logged_in", t("qr.success")
                return self.payload(platform)
            try:
                image = await self.capture_qr(platform, page)
            except Exception:
                image = None
            if image:
                session["qr_image"] = image
                session["deadline"] = self.clock() + QR_LIFETIME
            else:
                session["status"] = "fallback"
                session["note"] = t("qr.fallback") + " " + await self.browser.snapshot_note(page, platform)
                await self.browser.show_window(platform)
            return self.payload(platform)

    async def status(self, platform):
        session = self.sessions.get(platform)
        if session is None:
            raise ValueError(t("qr.missing"))
        await self.browser.refresh_login_status()
        if self.sessions.get(platform) is not session:
            raise ValueError(t("qr.missing"))
        if session["status"] in ("qr", "expired") and self.browser.login_status.get(platform) is True:
            session["status"], session["qr_image"], session["note"] = "logged_in", "", t("qr.success")
        return self.payload(platform)

    async def finish_fallback(self, platform):
        await self.status(platform)
        session = self.sessions[platform]
        if self.browser.login_status.get(platform) is not True:
            session["note"] = t("qr.unknown")
            return self.payload(platform)
        await self.browser.hide_window(platform)
        session["status"], session["note"] = "logged_in", t("qr.success")
        return self.payload(platform)

    async def cancel(self, platform):
        async with self.locks.setdefault(platform, asyncio.Lock()):
            session = self.sessions.pop(platform, None)
            if session and session["status"] == "fallback":
                await self.browser.hide_window(platform)

    async def show_window(self, platform):
        if platform not in self.sessions:
            raise ValueError(t("qr.missing"))
        module = MODULES[platform]
        if not self.browser.has_page(platform):
            await self.browser.open_login(platform, module.LOGIN_URL, module.LOGGED_IN_SELECTOR, module.LOGIN_COOKIES)
        await self.browser.show_window(platform)
