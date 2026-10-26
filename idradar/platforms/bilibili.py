"""B 站搜索页面解析；不把未知页面误判为空结果。"""

from html.parser import HTMLParser
from urllib.parse import quote, urljoin

from ..i18n import t
from .base import Checker, Result, match_results
from .login_search import visible, wait_for_visible

CARD_SELECTOR = ".b-user-info-card"
NAME_SELECTOR = "h2 a[title]"
EMPTY_TEXT = "寂寞如雪"
BLOCKED_SELECTOR = ".geetest_panel, .geetest_holder, .bili-captcha, [class*='captcha']"


def search_url(name: str) -> str:
    return "https://search.bilibili.com/upuser?keyword=" + quote(name)


class AccountParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack = []
        self.accounts = []
        self.cards = 0
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        card = "b-user-info-card" in attrs.get("class", "").split()
        if card:
            self.cards += 1
        if tag == "a" and attrs.get("title") and any(item[1] for item in self.stack) and any(item[0] == "h2" for item in self.stack):
            self.accounts.append({"name": attrs["title"], "url": urljoin("https://search.bilibili.com", attrs.get("href", "")), "extra": ""})
        if tag not in {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}:
            self.stack.append((tag, card))

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, -1, -1):
            if self.stack[i][0] == tag:
                del self.stack[i:]
                break

    def handle_data(self, data):
        if not any(tag in ("script", "style") for tag, _ in self.stack):
            self.text.append(data)


def parse_html(html: str, name: str, blocked=False) -> Result:
    url = search_url(name)
    if blocked:
        return Result("blocked", search_url=url, note=t('bili.blocked'))
    parser = AccountParser()
    parser.feed(html)
    text = "".join(parser.text)
    if any(word in text for word in ("请完成验证", "安全验证", "访问过于频繁", "滑动验证")):
        return Result("blocked", search_url=url, note=t('bili.blocked'))
    if parser.accounts:
        result = match_results(name, parser.accounts, url, t('bili.search'))
        if result.status == "available":
            # B 站对几乎任何词都会返回模糊相关的账号，不能据此判“相近”；列出来仅供参考。
            related = [{**a, "extra": t('bili.related')} for a in parser.accounts[:3]]
            return Result("available", related, url, t('bili.available'))
        return result
    if EMPTY_TEXT in text:
        return Result("available", search_url=url, note=t('search.empty'))
    return Result("error", search_url=url, note=t('bili.unknown'))


class BilibiliChecker(Checker):
    id, label, mode = "bilibili", t('platform.bilibili'), "auto"

    def __init__(self, browser):
        self.browser = browser

    async def check(self, name, handle):
        url = search_url(name)
        try:
            async with self.browser.page(self.id) as page:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await wait_for_visible(page, (BLOCKED_SELECTOR, ":text('安全验证')", CARD_SELECTOR, f":text('{EMPTY_TEXT}')"))
                blocked = await visible(page, BLOCKED_SELECTOR)
                result = parse_html(await page.content(), name, blocked)
                return await self.browser.record_error(page, self.id, result)
        except Exception as error:
            from ..browser import PageQueryError

            note = t('bili.error')
            return Result("error", search_url=url, note=note + ("。" + str(error) if isinstance(error, PageQueryError) else ""))
