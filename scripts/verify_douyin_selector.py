"""用精简样本检查抖音用户卡片选择器（需要本机 Edge）：python -X utf8 scripts/verify_douyin_selector.py"""

import asyncio
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from playwright.async_api import async_playwright

from idradar.platforms import douyin

FIXTURE = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "douyin" / "user_search_two_cards.html"


async def main():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge")
        page = await browser.new_page()
        await page.set_content(FIXTURE.read_text(encoding="utf-8"))
        cards = page.locator(douyin.CARD_SELECTOR)
        names = [(await cards.nth(i).locator(douyin.NAME_SELECTOR).first.inner_text()).strip() for i in range(await cards.count())]
        hrefs = [await cards.nth(i).get_attribute("href") for i in range(await cards.count())]
        await browser.close()
    assert names == ["样本甲", "样本乙【简介里的括号"], names
    assert all("/user/FAKE_SEC_UID_" in href for href in hrefs), hrefs
    print("抖音卡片选择器正常：", names)


asyncio.run(main())
