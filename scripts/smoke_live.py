"""仅由用户主动运行的联网冒烟，不属于 pytest。"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from idradar.browser import BrowserManager
from idradar.platforms.bilibili import BilibiliChecker
from idradar.platforms.github import GitHubChecker
from idradar.runner import CheckRunner
from idradar.parse_names import make_handle


class NoHistory:
    def append(self, record):
        pass


async def smoke(name, handle):
    browser = BrowserManager()
    try:
        runner = CheckRunner({"bilibili": BilibiliChecker(browser), "github": GitHubChecker()}, NoHistory())
        async for event, cell in runner.stream([{"name": name, "handle": handle or make_handle(name)}], ["bilibili", "github"]):
            if event == "result":
                result = cell["result"]
                print(f"{cell['platform']}: {result['status']} — {result['note']}")
                print(result["search_url"])
    finally:
        await browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="真实访问 B 站和 GitHub，仅查一个名字，不调用大模型")
    parser.add_argument("name", nargs="?", default="AI包工头")
    parser.add_argument("--handle", default="", help="GitHub handle，留空则使用拼音")
    args = parser.parse_args()
    asyncio.run(smoke(args.name, args.handle))
