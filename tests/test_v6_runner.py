import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from idradar.history import HistoryStore
from idradar.platforms.base import Result
from idradar.runner import CheckRunner
from test_server import make_app


class Challenge:
    label, mode = "Fake", "login"

    def __init__(self, id="douyin"):
        self.id, self.calls = id, []

    async def check(self, name, handle):
        self.calls.append(name)
        return Result("blocked" if len(self.calls) == 1 else "available")


async def next_verification(stream):
    while True:
        event, data = await asyncio.wait_for(anext(stream), 1)
        if event == "verification":
            return data


async def test_verification_automatically_opens_detects_and_continues(tmp_path):
    checker = Challenge()
    browser = SimpleNamespace(show_window=AsyncMock(), hide_window=AsyncMock(),
                              verification_present=AsyncMock(side_effect=[True, False, True, False, False]))
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), browser=browser,
                         interval=lambda: 0, verification_period=0.001)
    events = [item async for item in runner.stream([{"name": "候选", "handle": "toolman"}], [checker.id])]
    browser.show_window.assert_awaited_once_with(checker.id)
    browser.hide_window.assert_awaited_once_with(checker.id)
    assert browser.verification_present.await_count == 5
    assert checker.calls == ["候选", "候选"]
    assert any(event == "verification" and data["opened"] for event, data in events)
    assert any(event == "verification_resumed" for event, _ in events)
    assert runner.history.list()[0]["stopped"] is False


async def test_two_verifications_queue_and_manual_continue_remains_available(tmp_path):
    calls = []
    async def show(id): calls.append(("show", id))
    async def hide(id): calls.append(("hide", id))
    browser = SimpleNamespace(show_window=show, hide_window=hide, verification_present=AsyncMock(return_value=True))
    checkers = {id: Challenge(id) for id in ("douyin", "xiaohongshu")}
    runner = CheckRunner(checkers, HistoryStore(tmp_path / "history.jsonl"), browser=browser, interval=lambda: 0)
    stream = runner.stream([{"name": "候选", "handle": "toolman"}], list(checkers))
    try:
        first, second = await next_verification(stream), await next_verification(stream)
        assert first["opened"] and not second["opened"] and second["queued"]
        assert calls == [("show", first["platform"])]
        with pytest.raises(ValueError):
            await runner.resume(second["run_id"], second["platform"], second["pause_id"])
        await runner.resume(first["run_id"], first["platform"], first["pause_id"])
        active = await next_verification(stream)
        assert active["platform"] == second["platform"] and active["opened"]
        assert calls == [("show", first["platform"]), ("hide", first["platform"]), ("show", second["platform"])]
        await runner.resume(active["run_id"], active["platform"], active["pause_id"])
        await anext_done(stream)
        assert calls[-1] == ("hide", second["platform"])
        assert all(len(checker.calls) == 2 for checker in checkers.values())
    finally:
        await stream.aclose()


async def anext_done(stream):
    async for event, data in stream:
        if event == "done":
            return data
    raise AssertionError("没有结束事件")


async def test_stop_during_verification_cancels_queue_and_hides_window(tmp_path):
    browser = SimpleNamespace(show_window=AsyncMock(), hide_window=AsyncMock(), verification_present=AsyncMock(return_value=True))
    checkers = {id: Challenge(id) for id in ("douyin", "xiaohongshu")}
    runner = CheckRunner(checkers, HistoryStore(tmp_path / "history.jsonl"), browser=browser, interval=lambda: 0)
    stream = runner.stream([{"name": "候选" + str(i), "handle": "toolman"} for i in range(12)], list(checkers))
    await next_verification(stream)
    await stream.aclose()
    before = {id: list(c.calls) for id, c in checkers.items()}
    await asyncio.sleep(0.01)
    assert {id: c.calls for id, c in checkers.items()} == before
    assert all(len(c.calls) == 1 for c in checkers.values())
    browser.show_window.assert_awaited_once()
    browser.hide_window.assert_awaited_once()
    record = runner.history.list()[0]
    assert record["stopped"] and len(record["results"]) == 24
    assert all(cell["result"]["status"] == "stopped" for cell in record["results"])
    assert not runner.runs and not runner.verification_lock.locked()


async def test_stop_waits_for_window_hide_despite_multiple_cancellations(tmp_path):
    visible = True
    async def hide(id):
        nonlocal visible
        await asyncio.sleep(0.01)
        visible = False
    checker = Challenge()
    browser = SimpleNamespace(show_window=AsyncMock(), hide_window=hide)
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), browser=browser, interval=lambda: 0)
    stream = runner.stream([{"name": "候选", "handle": "toolman"}], [checker.id])
    await next_verification(stream)
    await stream.aclose()
    assert not visible and not runner.runs
    assert runner.history.list()[0]["stopped"]


async def test_stop_cancels_automatic_variants_preserves_finished_cells(tmp_path):
    started, cancelled = asyncio.Event(), asyncio.Event()
    class SlowVariants:
        id, label, mode = "bilibili", "B", "auto"
        def __init__(self): self.calls = []
        async def check(self, name, handle):
            self.calls.append(name)
            if name != "候选":
                started.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return Result("taken")
    checker = SlowVariants()
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0)
    stream = runner.stream([{"name": "候选", "handle": "toolman"}], [checker.id])
    while True:
        event, _ = await anext(stream)
        if event == "recommendation": break
    await asyncio.wait_for(started.wait(), 1)
    await stream.aclose()
    assert cancelled.is_set() and len(checker.calls) == 2
    await asyncio.sleep(0.01)
    assert len(checker.calls) == 2
    record = runner.history.list()[0]
    assert record["stopped"] and record["results"][0]["result"]["status"] == "taken"
    assert not record["recommendations"]["0"]["loading"]


async def test_http_disconnect_closes_runner_before_new_checker_calls(tmp_path, fake_browser):
    import json

    waiting, disconnected, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    class Slow:
        id, label, mode = "bilibili", "B", "auto"
        def __init__(self): self.calls = []
        async def check(self, name, handle):
            self.calls.append(name)
            if len(self.calls) > 1:
                waiting.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cancelled.set()
            return Result("available")
    checker = Slow()
    app = make_app(tmp_path, fake_browser, checkers={checker.id: checker})
    sent_body = False
    body = json.dumps({"candidates": [{"name": str(i), "handle": "toolman"} for i in range(12)], "platforms": [checker.id]}).encode()
    async def receive():
        nonlocal sent_body
        if not sent_body:
            sent_body = True
            return {"type": "http.request", "body": body, "more_body": False}
        await disconnected.wait()
        return {"type": "http.disconnect"}
    async def send(message):
        if b"event: result" in message.get("body", b""):
            await waiting.wait()
            disconnected.set()
    scope = {"type": "http", "asgi": {"version": "3.0", "spec_version": "2.0"}, "method": "POST", "scheme": "http", "path": "/api/check",
             "raw_path": b"/api/check", "query_string": b"lang=en", "root_path": "", "http_version": "1.1",
             "headers": [(b"host", b"testserver"), (b"content-type", b"application/json")], "server": ("testserver", 80), "client": ("127.0.0.1", 1)}
    await asyncio.wait_for(app(scope, receive, send), 2)
    for _ in range(100):
        if not app.state.runner.runs: break
        await asyncio.sleep(0.001)
    assert cancelled.is_set() and checker.calls == ["0", "1"]
    assert not app.state.runner.runs
    record = app.state.runner.history.list()[0]
    assert record["stopped"] and len(record["results"]) == 12
    results = {cell["row"]: cell["result"] for cell in record["results"]}
    assert results[0]["status"] == "available"
    assert results[1]["status"] == "stopped" and results[1]["note"].isascii()


async def test_login_search_retries_unrecognized_page_once():
    from idradar.platforms.douyin import DouyinChecker

    checker = DouyinChecker(browser=None)
    outcomes = [Result("error"), Result("taken"), Result("available")]
    calls = []

    async def once(name):
        calls.append(name)
        return outcomes[len(calls) - 1]

    checker._check_once = once
    assert (await checker.check("名字", "")).status == "taken"
    assert calls == ["名字", "名字"]

    calls.clear(); outcomes[:] = [Result("error"), Result("error"), Result("taken")]
    assert (await checker.check("名字", "")).status == "error"
    assert len(calls) == 2


async def test_login_mid_run_lifts_short_circuit(tmp_path):
    class NeedsLogin:
        id, label, mode = "xiaohongshu", "小红书", "login"

        def __init__(self):
            self.calls = []

        async def check(self, name, handle):
            self.calls.append(name)
            if len(self.calls) == 1:
                browser.login_status["xiaohongshu"] = True  # 第一格返回未登录后，用户扫码登录成功
                return Result("login")
            return Result("available")

    checker = NeedsLogin()
    browser = SimpleNamespace(login_status={"xiaohongshu": False})
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), browser=browser, interval=lambda: 0)
    candidates = [{"name": f"名字{i}", "handle": f"name{i}"} for i in range(3)]
    statuses = {}
    async for event, data in runner.stream(candidates, [checker.id]):
        if event == "result" and not data.get("variant"):
            statuses[data["row"]] = data["result"]["status"]
    assert statuses[0] == "login"
    assert statuses[1] == statuses[2] == "available"
    assert checker.calls[:3] == ["名字0", "名字1", "名字2"]


async def test_xiaohongshu_identity_verify_page_counts_as_verification():
    # 精简自 10-27 实测的“扫码验证身份”页（二维码已去掉）；用真实浏览器确认选择器认得出且可见
    from pathlib import Path

    from playwright.async_api import async_playwright

    from idradar.platforms import xiaohongshu
    from idradar.platforms.login_search import visible

    html = (Path(__file__).parent / "fixtures" / "xiaohongshu" / "identity_verify.html").read_text(encoding="utf-8")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(channel="msedge")
        try:
            page = await browser.new_page()
            await page.set_content(html)
            assert await visible(page, xiaohongshu.BLOCKED_SELECTOR)
            assert not await visible(page, xiaohongshu.LOGIN_SELECTOR)
        finally:
            await browser.close()
