"""登录平台的共同流程；只识别页面，不处理验证码。"""

import asyncio
import time

from ..i18n import t, translate_text
from .base import Checker, Result, match_results


async def visible(page, selector: str) -> bool:
    locator = page.locator(selector)
    for index in range(await locator.count()):
        if await locator.nth(index).is_visible():
            return True
    return False


async def has_login_cookie(context, url, names) -> bool:
    # 页面选择器会随改版失效，登录后才下发的会话 Cookie 更稳
    if not names:
        return False
    try:
        return any(cookie["name"] in names and cookie.get("value") for cookie in await context.cookies(url))
    except Exception:
        return False


async def wait_for_visible(page, selectors, timeout=8):
    deadline = time.monotonic() + timeout
    while True:
        for selector in selectors:
            if await visible(page, selector):
                return
        if time.monotonic() >= deadline:
            return
        await asyncio.sleep(0.2)


async def detect_login(page, url, positive_selector, login_selector, cookies=()):
    if await visible(page, login_selector):
        return False
    if await visible(page, positive_selector) or await has_login_cookie(page.context, url, cookies):
        return True
    return None


class LoginSearchChecker(Checker):
    mode = "login"
    note = ""
    login_cookies = ()

    def __init__(self, browser):
        self.browser = browser

    def classify(self, name, accounts, *, blocked=False, login=False, empty=False, authenticated=False):
        url = self.search_url(name)
        if blocked:
            return Result("blocked", search_url=url, note=t('search.blocked', platform=self.label, note=self.note))
        if login:
            return Result("login", search_url=url, note=t('search.login', note=self.note))
        if not authenticated:
            return Result("login", search_url=url, note=t('search.auth', note=self.note))
        if accounts:
            return match_results(name, accounts, url, translate_text(self.note) + " " + t("search.result"))
        if empty and authenticated:
            return Result("available", search_url=url, note=translate_text(self.note) + " " + t("search.empty"))
        return Result("error", search_url=url, note=t('search.unknown', note=self.note))

    async def prepare(self, page):
        """页面打开后、识别前的平台专属操作（如切到“用户”标签）；默认不做。"""

    async def check(self, name, handle):
        # 抖音过完验证后的第一次搜索会盖一个“登录后即可搜索”框（实际已登录），认不出时重开页面再查一次
        result = await self._check_once(name)
        if result.status == "error":
            result = await self._check_once(name)
        return result

    async def _check_once(self, name):
        url = self.search_url(name)
        try:
            async with self.browser.page(self.id) as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                if await visible(page, self.blocked_selector):
                    return self.classify(name, [], blocked=True)
                await self.prepare(page)
                await wait_for_visible(page, (self.blocked_selector, self.login_selector, self.card_selector, self.empty_selector))
                blocked = await visible(page, self.blocked_selector)
                if blocked:
                    return self.classify(name, [], blocked=True)
                login = await visible(page, self.login_selector)
                if login:
                    self.browser.login_status[self.id] = False
                    return self.classify(name, [], login=True)
                state = await detect_login(page, url, self.logged_in_selector, self.login_selector, self.login_cookies)
                authenticated = state is True
                accounts = []
                cards = page.locator(self.card_selector)
                for index in range(min(await cards.count(), 100)):
                    card = cards.nth(index)
                    if not await card.is_visible():
                        continue
                    names = card.locator(self.name_selector)
                    if not await names.count():
                        continue
                    nickname = (await names.first.inner_text()).strip()
                    links = card.locator(self.link_selector)
                    # 卡片自己就是链接时（抖音），直接取它的 href
                    href = await links.first.get_attribute("href") if await links.count() else (await card.get_attribute("href") or "")
                    from urllib.parse import urljoin

                    if nickname:
                        accounts.append({"name": nickname, "url": urljoin(url, href or ""), "extra": ""})
                self.browser.login_status[self.id] = state
                result = self.classify(name, accounts, authenticated=authenticated, empty=await visible(page, self.empty_selector))
                return await self.browser.record_error(page, self.id, result)
        except Exception as error:
            from ..browser import PageQueryError

            note = t('search.error', platform=self.label, note=self.note)
            return Result("error", search_url=url, note=note + (" " + str(error) if isinstance(error, PageQueryError) else ""))
