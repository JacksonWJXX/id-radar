import httpx
import pytest

from idradar.platforms import x


def fake_client(status):
    def handler(request):
        assert request.url == httpx.URL("https://x.com/tool_user")
        return httpx.Response(status, text="<html></html>")
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize("status,expected", [(200, "taken"), (404, "available"), (429, "blocked"), (403, "blocked"), (500, "error")])
async def test_x_status_codes(status, expected):
    async with fake_client(status) as client:
        result = await x.XChecker(client).check("中文显示名", "tool_user")
    assert result.status == expected
    if expected == "taken":
        assert result.matches[0]["name"] == "@tool_user"
        assert "封禁" in result.note


async def test_x_network_error():
    def handler(request):
        raise httpx.ConnectError("断网")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await x.XChecker(client).check("显示名", "tool_user")).status == "error"


@pytest.mark.parametrize("handle", ["bad-handle", "", "a_very_long_handle_123"])
async def test_x_invalid_handle_never_requests(handle):
    def handler(request):
        raise AssertionError("不合规则的 handle 不能发请求")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert (await x.XChecker(client).check("显示名", handle)).status == "invalid"


def test_x_is_auto_mode():
    assert x.XChecker.mode == "auto"
