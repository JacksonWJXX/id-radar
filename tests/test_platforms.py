from pathlib import Path

import httpx
import pytest

from idradar.platforms.bilibili import BilibiliChecker, parse_html
from idradar.platforms.douyin import DouyinChecker
from idradar.platforms.github import GitHubChecker
from idradar.platforms.weixin_channels import WeixinChannelsChecker
from idradar.platforms.xiaohongshu import XiaohongshuChecker

FIXTURES = Path(__file__).parent / "fixtures" / "bilibili"


@pytest.mark.parametrize("file,name,status", [("taken_exact", "AI包工头", "taken"), ("similar_only", "百号工具人", "available"), ("none", "造轮子百回", "available")])
def test_bilibili_real_fixtures(file, name, status):
    result = parse_html((FIXTURES / (file + ".html")).read_text(encoding="utf-8"), name)
    assert result.status == status
    if status == "taken":
        assert any(item["name"] == "Ai包工头" for item in result.matches)
    if file == "similar_only":
        # 只有模糊相关的“工具人三百九十九号”，不算相近，但要列出来供参考
        assert [m["extra"] for m in result.matches] == ["相关（非同名）"]


def test_bilibili_unknown_and_verification():
    assert parse_html("<p>未知结构</p>", "百号工具人").status == "error"
    assert parse_html("<p>安全验证</p>", "百号工具人").status == "blocked"
    assert parse_html("<p>寂寞如雪</p>", "百号工具人", blocked=True).status == "blocked"
    assert parse_html('<script>寂寞如雪</script>', "百号工具人").status == "error"


@pytest.mark.parametrize("code,expected", [(200, "taken"), (404, "available"), (403, "blocked"), (429, "blocked"), (500, "error")])
async def test_github_fake_http(code, expected):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(code, json={"login": "test-handle"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await GitHubChecker(client).check("百号工具人", "test-handle")
    assert result.status == expected
    assert str(requests[0].url) == "https://api.github.com/users/test-handle"


@pytest.mark.parametrize("handle", ["", "中文", "a_b", "-abc", "abc-", "a--b", "a" * 40, "x/y", "a b"])
async def test_github_invalid_handle_no_http(handle):
    assert (await GitHubChecker().check("昵称", handle)).status == "invalid"


@pytest.mark.parametrize("handle", ["a", "a" * 39, "good-handle", "123"])
async def test_github_valid_handle(handle):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as client:
        assert (await GitHubChecker(client).check("昵称", handle)).status == "available"


@pytest.mark.parametrize("cls", [DouyinChecker, XiaohongshuChecker])
def test_login_and_blocked_priority(cls, fake_browser):
    checker = cls(fake_browser)
    assert checker.classify("百号工具人", [], login=True).status == "login"
    assert checker.classify("百号工具人", [], blocked=True, login=True).status == "blocked"
    assert checker.classify("百号工具人", [], authenticated=True).status == "error"
    assert checker.classify("百号工具人", [], empty=True, authenticated=True).status == "available"
    assert checker.classify("百号工具人", [], empty=True).status == "login"
    accounts = [{"name": "百号工具人", "url": "https://example.test", "extra": ""}]
    assert checker.classify("百号工具人", accounts).status == "login"
    assert checker.classify("百号工具人", accounts, authenticated=True).status == "taken"
    if cls == XiaohongshuChecker:
        assert "小红书昵称唯一性资料待实测" in checker.classify("百号工具人", [], login=True).note


async def test_weixin_manual():
    result = await WeixinChannelsChecker().check("百号工具人", "test")
    assert result.status == "manual"
    assert result.note == "视频号名字不能重名。在微信 → 发现 → 视频号 → 右上角搜索，或创建、改名时直接试填，提示‘已被占用’就是有人用了"
