import httpx
import pytest

from idradar.custom_platforms import CustomPlatformStore, validate_site
from idradar.platforms.custom import CustomChecker


def test_store_add_delete_limit_and_reload(tmp_path):
    store = CustomPlatformStore(tmp_path / "custom_platforms.json")
    assert store.list() == []
    for index in range(10):
        store.add(f"网站{index}", "https://example.test/{handle}", "profile")
    records = CustomPlatformStore(store.path).list()
    assert len(records) == 10
    with pytest.raises(ValueError, match="最多添加 10"):
        store.add("第十一个", "https://example.test/{name}", "search")
    store.delete(records[0]["id"])
    assert len(store.list()) == 9
    store.add("新的", "https://example.test/search?q={name}", "search")
    assert len(store.list()) == 10
    with pytest.raises(ValueError, match="不存在"):
        store.delete("custom_missing")


@pytest.mark.parametrize("url", ["https://example.test/", "javascript:{name}", "ftp://example.test/{name}", "https://user:password@example.test/{handle}", "https://example.test/{name}/{other}", "https://example.test/with space/{name}", "https://example.test:bad/{name}"])
def test_invalid_urls(url):
    with pytest.raises(ValueError):
        validate_site("示例", url, "profile")


@pytest.mark.parametrize("label", [" ", "太长" * 7])
def test_label_limits(label):
    with pytest.raises(ValueError):
        validate_site(label, "https://example.test/{name}", "profile")


@pytest.mark.parametrize("code,status", [(404, "available"), (200, "taken"), (403, "manual"), (429, "manual"), (500, "manual")])
async def test_profile_fake_http(code, status):
    seen = []

    def respond(request):
        seen.append(request)
        return httpx.Response(code)

    site = {"id": "custom_test", "label": "示例", "kind": "profile", "url_template": "https://example.test/{handle}?name={name}"}
    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await CustomChecker(site, client).check("中文 名", "any_handle")
    assert result.status == status
    assert str(seen[0].url) == "https://example.test/any_handle?name=%E4%B8%AD%E6%96%87%20%E5%90%8D"


async def test_network_failure_is_error():
    def fail(request):
        raise httpx.ConnectError("假网络错误", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        result = await CustomChecker({"id": "custom_test", "label": "示例", "kind": "profile", "url_template": "https://example.test/{handle}"}, client).check("名字", "abc")
    assert result.status == "error"
    assert result.search_url == "https://example.test/abc"


async def test_search_never_requests_http():
    def forbidden(request):
        raise AssertionError("搜索页不能请求")

    async with httpx.AsyncClient(transport=httpx.MockTransport(forbidden)) as client:
        result = await CustomChecker({"id": "custom_test", "label": "示例", "kind": "search", "url_template": "https://example.test/?q={name}"}, client).check("中文", "")
    assert result.status == "manual"
    assert result.search_url.endswith("q=%E4%B8%AD%E6%96%87")


async def test_profile_follows_redirect_and_uses_ten_seconds():
    requests = []

    def respond(request):
        requests.append(request)
        assert all(value == 10 for value in request.extensions["timeout"].values())
        return httpx.Response(302, headers={"Location": "/final"}) if request.url.path == "/start" else httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        checker = CustomChecker({"id": "custom_test", "label": "示例", "kind": "profile", "url_template": "https://example.test/start?name={name}"}, client)
        assert (await checker.check("名字", "handle")).status == "taken"
    assert len(requests) == 2
