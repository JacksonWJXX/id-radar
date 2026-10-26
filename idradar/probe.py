"""由用户主动运行的抓页工具，不尝试登录或绕过验证。"""

import argparse
import asyncio
import httpx

from .browser import BrowserManager
from .platforms import bilibili, douyin, xiaohongshu


async def capture_page(browser, platform, name):
    module = {"bilibili": bilibili, "douyin": douyin, "xiaohongshu": xiaohongshu}[platform]
    async with browser.page(platform) as page:
        await page.goto(module.search_url(name), wait_until="domcontentloaded", timeout=30000)
        try:
            await page.wait_for_load_state("networkidle", timeout=8000)
        except Exception:
            pass
        return await browser.save_snapshot(page, platform)


async def probe(platform, name):
    # 已运行的工具拥有持久化目录，优先让它在同一窗口抓页，避免目录被两个进程占用。
    async with httpx.AsyncClient(timeout=httpx.Timeout(45, connect=1), trust_env=False) as client:
        try:
            response = await client.post(f"http://127.0.0.1:8765/api/probe/{platform}", json={"name": name})
        except httpx.ConnectError:
            response = None
    if response is not None:
        if response.is_error:
            raise ValueError("本机服务抓页失败，请检查专用浏览器与网络")
        data = response.json()
        print(f"已保存 {data['html']} 和 {data['png']}。{data['note']}")
        return
    browser = BrowserManager()
    try:
        html, png = await capture_page(browser, platform, name)
        print(f"已保存 {html} 和 {png}。文件可能包含你的账号信息，只在本机，不会上传。")
    finally:
        await browser.close()


def main():
    parser = argparse.ArgumentParser(description="抓取已登录浏览器的搜索页，用于调整选择器")
    parser.add_argument("platform", choices=["bilibili", "douyin", "xiaohongshu"])
    parser.add_argument("name", help="要搜索的昵称")
    args = parser.parse_args()
    try:
        asyncio.run(probe(args.platform, args.name))
    except Exception:
        raise SystemExit("抓页失败，请确认专用浏览器可用并检查网络；工具运行时会复用它的窗口") from None


if __name__ == "__main__":
    main()
