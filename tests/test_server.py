import asyncio
import json

import httpx
import pytest

from idradar.parse_names import NAMING_PROMPT
from idradar.custom_platforms import CustomPlatformStore
from idradar.history import HistoryStore
from idradar.platforms.base import Checker, Result
from idradar.runner import CheckRunner
from idradar.server import create_app


class FakeChecker(Checker):
    def __init__(self, platform="bilibili", status="available"):
        self.id, self.label = platform, platform
        self.calls = []
        self.running = 0
        self.peak = 0
        self.status = status

    async def check(self, name, handle):
        self.running += 1
        self.peak = max(self.peak, self.running)
        self.calls.append(name)
        await asyncio.sleep(0)
        self.running -= 1
        return Result(self.status, search_url="https://example.test", note="假查重器")


def make_app(tmp_path, fake_browser, **kwargs):
    return create_app(history_store=HistoryStore(tmp_path / "history.jsonl"), custom_store=CustomPlatformStore(tmp_path / "custom_platforms.json"), browser=fake_browser, runner_options={"interval": lambda: 0}, **kwargs)


async def test_index_prompt_and_parse(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.get("/")
        assert response.status_code == 200
        assert 'data-i18n="step1"' in response.text
        assert 'rows="6"' in response.text
        assert 'id="open-settings"' not in response.text
        assert (await client.get("/api/prompt")).json()["prompt"] == NAMING_PROMPT
        parsed = await client.post("/api/parse-names", json={"text": "百号工具人 | baihao\n造轮子百回\n百号工具人 | other"})
        assert [candidate["name"] for candidate in parsed.json()["candidates"]] == ["百号工具人", "造轮子百回"]
        assert (await client.post("/api/parse-names", json={"text": ""})).json() == {"candidates": [], "updates": [], "count": 0, "added": 0, "updated": 0}
        repeated = await client.post("/api/parse-names", json={"text": "ＡＩ包工头 | other\nSTRASSE | other", "existing": ["ai 包工头", "Straße"]})
        assert repeated.json()["candidates"] == [] and repeated.json()["count"] == 2
        assert repeated.json()["updated"] == 2


async def test_sse_cells_serial_and_history(tmp_path, fake_browser):
    checkers = {id: FakeChecker(id) for id in ("bilibili", "github")}
    app = make_app(tmp_path, fake_browser, checkers=checkers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": [{"name": "百号工具人", "handle": "a"}, {"name": "造轮子百回", "handle": "b"}], "platforms": list(checkers)})
        assert response.headers["content-type"].startswith("text/event-stream")
        chunks = response.text.strip().split("\n\n")
        cells = [json.loads(chunk.split("data: ")[1]) for chunk in chunks if chunk.startswith("event: result")]
        assert len(cells) == 4
        assert {(cell["row"], cell["platform"]) for cell in cells} == {(row, platform) for row in range(2) for platform in checkers}
        assert all(cell["result"]["status"] == "available" for cell in cells)
        for checker in checkers.values():
            assert checker.calls == ["百号工具人", "造轮子百回"]
            assert checker.peak == 1
        assert chunks[-1].startswith("event: done")
        records = (await client.get("/api/history")).json()["history"]
        assert len(records) == 1 and len(records[0]["results"]) == 4


async def test_blocked_stops_remaining_and_interval(tmp_path):
    checker = FakeChecker(status="blocked")
    delays = []

    async def sleep(delay):
        delays.append(delay)

    runner = CheckRunner({"bilibili": checker}, HistoryStore(tmp_path / "history.jsonl"), sleep=sleep, interval=lambda: 3)
    events = [event async for event in runner.stream([{"name": str(i), "handle": str(i)} for i in range(3)], ["bilibili"])]
    assert checker.calls == ["0"]
    assert not delays
    assert len([event for event, data in events if event == "result"]) == 3


async def test_spacing_and_serial_across_requests(tmp_path):
    checker = FakeChecker()
    delays = []

    async def sleep(delay):
        delays.append(delay)
        await asyncio.sleep(0)

    runner = CheckRunner({"bilibili": checker}, HistoryStore(tmp_path / "history.jsonl"), sleep=sleep, interval=lambda: 3)

    async def batch(prefix):
        return [event async for event in runner.stream([{"name": prefix + str(i), "handle": str(i)} for i in range(2)], ["bilibili"])]

    await asyncio.gather(batch("A"), batch("B"))
    assert checker.peak == 1
    assert checker.calls in (["A0", "A1", "B0", "B1"], ["B0", "B1", "A0", "A1"])
    assert len(delays) == 3
    assert all(2 <= delay <= 4 for delay in delays)


async def test_stream_yields_before_batch_finishes_and_cancels(tmp_path):
    waiting = asyncio.Event()
    cancelled = asyncio.Event()

    class SlowChecker(FakeChecker):
        async def check(self, name, handle):
            if name == "第二个":
                waiting.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return Result("available")

    path = tmp_path / "history.jsonl"
    runner = CheckRunner({"bilibili": SlowChecker()}, HistoryStore(path), interval=lambda: 0)
    stream = runner.stream([{"name": name, "handle": "test"} for name in ("第一个", "第二个")], ["bilibili"])
    assert (await anext(stream))[0] == "start"
    event, cell = await asyncio.wait_for(anext(stream), 1)
    assert event == "result" and cell["row"] == 0
    await asyncio.wait_for(waiting.wait(), 1)
    await stream.aclose()
    assert cancelled.is_set()
    record = runner.history.list()[0]
    assert record["stopped"] is True
    assert [cell["result"]["status"] for cell in record["results"]] == ["available", "stopped"]


@pytest.mark.parametrize("candidates,platforms", [([{"name": "a"}] * 11, ["bilibili"]), ([{"name": "a"}, {"name": "Ａ"}], ["bilibili"]), ([{"name": "a"}], ["unknown"]), ([{"name": "a"}], ["bilibili", "bilibili"]), ([{"name": " "}], ["bilibili"]), ([], ["bilibili"])])
async def test_invalid_batches(tmp_path, fake_browser, candidates, platforms):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": candidates, "platforms": platforms})
        assert response.status_code in (400, 422)


async def test_cross_origin_rejected(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        assert (await client.get("/api/prompt", headers={"Origin": "https://other.test"})).status_code == 403
        assert (await client.get("/api/prompt", headers={"Host": "other.test"})).status_code == 403


def test_history_corrupt_line(tmp_path):
    path = tmp_path / "history.jsonl"
    record = {"id": "first", "created_at": "2026-10-26T00:00:00Z", "candidates": [], "platforms": [], "results": []}
    path.write_text(json.dumps(record) + '\n损坏的一行\n{"id":"incomplete"}\n', encoding="utf-8")
    store = HistoryStore(path)
    store.append({**record, "id": "second"})
    assert [record["id"] for record in store.list()] == ["second", "first"]


async def test_invalid_cells_never_call_checker(tmp_path, fake_browser):
    checkers = {id: FakeChecker(id) for id in ("github", "weixin_channels")}
    app = make_app(tmp_path, fake_browser, checkers=checkers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": [{"name": "汉" * 16, "handle": "中文"}, {"name": "视频工具", "handle": "valid-user"}], "platforms": list(checkers)})
        cells = [json.loads(chunk.split("data: ")[1]) for chunk in response.text.strip().split("\n\n") if chunk.startswith("event: result")]
        assert len(cells) == 4
        assert all(cell["result"]["status"] == "invalid" for cell in cells if cell["row"] == 0)
        assert all(checker.calls == ["视频工具"] for checker in checkers.values())


@pytest.mark.parametrize("platform", ["douyin", "xiaohongshu", "x"])
async def test_login_short_circuit_one_request_no_delay(tmp_path, platform):
    checker = FakeChecker(platform, status="login")
    delays = []

    async def sleep(delay):
        delays.append(delay)

    runner = CheckRunner({platform: checker}, HistoryStore(tmp_path / "history.jsonl"), sleep=sleep)
    events = [event async for event in runner.stream([{"name": name, "handle": "tool_user"} for name in ("第一个名字", "第二个名字", "第三个名字")], [platform])]
    assert checker.calls == ["第一个名字"]
    assert not delays
    cells = [data for event, data in events if event == "result"]
    assert len(cells) == 3 and all(cell["result"]["status"] == "login" for cell in cells)
    assert all(cell["result"]["note"] == "该平台未登录，本格未查询" for cell in cells[1:])


async def test_rule_and_variants_endpoints(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        platforms = (await client.get("/api/platforms")).json()["platforms"]
        ids = [platform["id"] for platform in platforms]
        assert ids.index("x") == ids.index("xiaohongshu") + 1
        rules = (await client.get("/api/rules")).json()["platforms"]
        assert len(rules) == 6
        assert rules["weixin_channels"]["unique"]["confidence"] == "user_tested"
        assert (await client.get("/api/rules/source")).status_code == 200
        response = await client.post("/api/rules/check", json={"candidates": [{"name": "中文显示名", "handle": "valid-user"}], "platforms": ["github", "x"]})
        assert response.json()["validations"][0]["github"]["verdict"] == "ok"
        assert response.json()["validations"][0]["x"]["verdict"] == "bad"
        result = await client.post("/api/variants", json={"candidate": {"name": "百号工具人", "handle": "toolman"}, "original": {"github": {"status": "taken"}, "x": {"status": "available"}}, "platforms": ["github", "x"]})
        assert result.status_code == 200
        assert [item["group"] for item in result.json()["variants"]] == ["words", "numbers", "words", "numbers"]
        assert all(item["name"] == "百号工具人" for item in result.json()["variants"])


async def test_six_platform_batch(tmp_path, fake_browser):
    ids = ["bilibili", "github", "douyin", "xiaohongshu", "x", "weixin_channels"]
    checkers = {id: FakeChecker(id) for id in ids}
    app = make_app(tmp_path, fake_browser, checkers=checkers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": [{"name": "工具创作者", "handle": "tooluser"}], "platforms": ids})
        assert response.status_code == 200
        assert response.text.count("event: result") == 6
        assert all(checker.calls == ["工具创作者"] for checker in checkers.values())


async def test_x_needs_no_login(tmp_path, fake_browser):
    # X 改为不登录的 HTTP 查询，不再开登录窗口
    from unittest.mock import AsyncMock

    fake_browser.open_login = AsyncMock(return_value=None)
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        assert (await client.post("/api/login/x", json={})).status_code == 400
        fake_browser.open_login.assert_not_awaited()


async def test_missing_handle_is_invalid_without_checker_call(tmp_path, fake_browser):
    checkers = {id: FakeChecker(id) for id in ("github", "x")}
    app = make_app(tmp_path, fake_browser, checkers=checkers)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": [{"name": "名字甲", "handle": ""}, {"name": "名字乙", "handle": "goodname"}], "platforms": list(checkers)})
        cells = [json.loads(chunk.split("data: ")[1]) for chunk in response.text.strip().split("\n\n") if chunk.startswith("event: result")]
        assert all(cell["result"]["status"] == "invalid" and cell["result"]["note"] == "未填英文 handle" for cell in cells if cell["row"] == 0)
        assert all(checker.calls == ["名字乙"] for checker in checkers.values())


async def test_handle_update_and_repair_prompt(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/parse-names", json={"text": "AI包工头 | albertwu\n新名字 | carolwu", "existing": [{"name": "AI包工头", "handle": ""}]})
        assert response.json()["added"] == 1 and response.json()["updated"] == 1
        assert response.json()["updates"] == [{"index": 0, "handle": "albertwu"}]
        checks = await client.post("/api/rules/check", json={"candidates": [{"name": "名字甲", "handle": ""}, {"name": "名字乙", "handle": "bad-handle"}, {"name": "名字丙", "handle": "carolwu"}], "platforms": ["github", "x"]})
        assert checks.json()["handle_names"] == ["名字甲", "名字乙"]
        assert checks.json()["handle_prompt"].endswith("\n名字甲\n名字乙")


async def test_login_and_check_are_not_mutually_exclusive(tmp_path, fake_browser):
    from unittest.mock import AsyncMock

    fake_browser.is_open = True
    fake_browser.open_login = AsyncMock(return_value=None)
    fake_browser.snapshot_note = AsyncMock(return_value="测试快照")
    fake_browser.show_window = AsyncMock()
    checker = FakeChecker()
    app = make_app(tmp_path, fake_browser, checkers={"bilibili": checker})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        responses = await asyncio.gather(client.post("/api/login/douyin", json={}), client.post("/api/login/xiaohongshu", json={}), client.post("/api/check", json={"candidates": [{"name": "测试名字", "handle": "testname"}], "platforms": ["bilibili"]}))
        assert all(response.status_code == 200 for response in responses)
        assert fake_browser.open_login.await_count == 2
        assert checker.calls == ["测试名字"]
        assert (await client.get("/api/platforms")).json()["browser_open"] is True


async def test_custom_sites_api_and_sse(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        assert (await client.post("/api/custom-platforms", json={"label": "错误", "url_template": "https://example.test/", "kind": "profile"})).status_code == 400
        profile = (await client.post("/api/custom-platforms", json={"label": "示例主页", "url_template": "https://example.test/{handle}", "kind": "profile"})).json()["site"]
        search = (await client.post("/api/custom-platforms", json={"label": "示例搜索", "url_template": "https://example.test/?q={name}", "kind": "search"})).json()["site"]
        assert len((await client.get("/api/platforms")).json()["platforms"]) == 8
        rules = (await client.get("/api/rules")).json()["platforms"]
        assert rules[profile["id"]]["notes"] == ["自定义网站，规则未知"]
        checks = (await client.post("/api/rules/check", json={"candidates": [{"name": "名字", "handle": "不按内置格式"}], "platforms": [profile["id"], search["id"]]})).json()
        assert all(result["verdict"] == "unknown" for result in checks["validations"][0].values())
        seen = []

        def respond(request):
            seen.append(request)
            return httpx.Response(404)

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as fake_http:
            app.state.runner.checkers[profile["id"]].client = fake_http
            response = await client.post("/api/check", json={"candidates": [{"name": "名字", "handle": "不按内置格式"}], "platforms": [profile["id"], search["id"]]})
        assert response.status_code == 200 and len(seen) == 1
        cells = [json.loads(chunk.split("data: ")[1]) for chunk in response.text.strip().split("\n\n") if chunk.startswith("event: result")]
        assert {cell["platform"]: cell["result"]["status"] for cell in cells} == {profile["id"]: "available", search["id"]: "manual"}
        assert (await client.delete("/api/custom-platforms/" + profile["id"])).status_code == 200
        assert len((await client.get("/api/custom-platforms")).json()["sites"]) == 1
        record = (await client.get("/api/history")).json()["history"][0]
        assert record["platform_details"][profile["id"]]["label"] == "示例主页"


async def test_delete_custom_site_during_active_batch(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    started, release = asyncio.Event(), asyncio.Event()

    async def respond(request):
        started.set()
        await release.wait()
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        site = (await client.post("/api/custom-platforms", json={"label": "示例主页", "url_template": "https://example.test/{handle}", "kind": "profile"})).json()["site"]
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as fake_http:
            app.state.runner.checkers[site["id"]].client = fake_http
            pending = asyncio.create_task(client.post("/api/check", json={"candidates": [{"name": "名字", "handle": "testname"}], "platforms": [site["id"]]}))
            await asyncio.wait_for(started.wait(), 1)
            assert (await client.delete("/api/custom-platforms/" + site["id"])).status_code == 200
            release.set()
            result = await asyncio.wait_for(pending, 1)
            assert "event: done" in result.text
