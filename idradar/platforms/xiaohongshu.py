"""小红书：2026-10-26 用真实登录页实测过选择器（用户标签 .user-list-item）；昵称允许重名。"""

from urllib.parse import quote

from ..i18n import t
from .login_search import LoginSearchChecker

CARD_SELECTOR = '.user-item, .user-list-item'
NAME_SELECTOR = '.user-name, .name'
LINK_SELECTOR = 'a[href*="/user/profile/"]'
LOGIN_SELECTOR = '#login-btn, .login-container, .login-modal, :text-is("登录后查看搜索结果")'
LOGGED_IN_SELECTOR = 'li.user.side-bar-component a[href*="/user/profile/"]'
# CC 10-27 实测：搜索会跳到 /website-login/captcha“扫码验证身份”页（要用小红书 App 扫码），原来被误判成未登录
BLOCKED_SELECTOR = '#captcha, .captcha-container, #captcha-div, :text("请完成验证"), :text("安全验证"), :text("扫码验证身份")'
EMPTY_SELECTOR = '.search-empty, .empty-container, :text("没有找到相关结果")'
# 小红书给未登录访客也发 web_session，不能用 Cookie 判断登录；只认侧栏“我”的个人主页入口
LOGIN_COOKIES = ()
USER_TAB_SELECTOR = "#user.channel"
LOGIN_URL = "https://www.xiaohongshu.com/"
NOTE = t('xhs.note')


def search_url(name):
    # 直接用小红书跳转后的最终地址，少跳几次
    return "https://www.xiaohongshu.com/search_result/?keyword=" + quote(name) + "&type=51"


class XiaohongshuChecker(LoginSearchChecker):
    id, label, note = "xiaohongshu", t('platform.xiaohongshu'), NOTE
    search_url = staticmethod(search_url)
    card_selector, name_selector, link_selector = CARD_SELECTOR, NAME_SELECTOR, LINK_SELECTOR
    login_selector, logged_in_selector = LOGIN_SELECTOR, LOGGED_IN_SELECTOR
    login_cookies = LOGIN_COOKIES
    blocked_selector, empty_selector = BLOCKED_SELECTOR, EMPTY_SELECTOR

    async def prepare(self, page):
        # 搜索页默认是“全部”（笔记），要切到“用户”标签才有用户卡片。CC 10-26 实测三个坑：
        # 1. 页面打开后会自己连跳几次地址，跳完前点的标签会被重置回“全部”，所以先等地址稳定；
        # 2. 页面内 JS 触发的点击小红书不认，要用真实鼠标点击；
        # 3. 同时查多个平台时小红书在后台标签页，普通点击会等页面“稳定”而超时，所以用 force 直接点。
        # 点完要看到“用户”标签 active、用户卡片或空结果出来，并且 1 秒后仍是这样，才算切好；否则重点，最多 4 次。
        import asyncio

        from .login_search import visible, wait_for_visible

        await wait_for_visible(page, (USER_TAB_SELECTOR, self.login_selector, self.blocked_selector), timeout=8)
        last_url, stable = page.url, 0
        for _ in range(20):
            await asyncio.sleep(0.3)
            stable = stable + 1 if page.url == last_url else 0
            last_url = page.url
            if stable >= 3:
                break

        async def switched():
            return bool(await page.locator(USER_TAB_SELECTOR + ".active").count()) and (
                await visible(page, self.card_selector) or await visible(page, self.empty_selector))

        for _ in range(4):
            if await visible(page, self.blocked_selector):
                return
            if not await page.locator(USER_TAB_SELECTOR).count() or await visible(page, self.login_selector):
                return
            if not await page.locator(USER_TAB_SELECTOR + ".active").count():
                try:
                    await page.locator(USER_TAB_SELECTOR).first.click(timeout=3000, force=True)
                except Exception:
                    await asyncio.sleep(0.5)
                    continue
            await wait_for_visible(page, (self.card_selector, self.empty_selector), timeout=4)
            if await switched():
                await asyncio.sleep(1)
                if await switched():
                    return
