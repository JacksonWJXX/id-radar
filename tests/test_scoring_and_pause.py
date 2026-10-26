import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from idradar.history import HistoryStore
from idradar.platforms.base import Result
from idradar.runner import CheckRunner, query_interval
from idradar.scoring import rank_rows
from test_recommendation_runner import ScriptChecker
from test_server import make_app


def test_scoring_is_pure_and_ties_follow_original_order():
    rows = [
        {"a": {"status": "available"}, "b": {"status": "taken"}},
        {"a": {"status": "available"}, "b": {"status": "similar"}},
        {"a": {"status": "available"}, "b": {"status": "error"}},
        {"a": {"status": "available"}, "b": {"status": "available"}},
    ]
    assert [item["row"] for item in rank_rows(rows)] == [3, 1, 2, 0]
    assert rows[0]["b"]["status"] == "taken"
    assert rank_rows([]) == []


@pytest.mark.parametrize("id,mode,kind,expected", [("github", "auto", "", (0.3, 0.8)), ("x", "auto", "", (0.3, 0.8)), ("custom_1", "auto", "profile", (0.3, 0.8)), ("bilibili", "auto", "", (1, 2)), ("douyin", "login", "", (1, 2)), ("xiaohongshu", "login", "", (1, 2)), ("weixin_channels", "manual", "", None)])
def test_intervals_by_platform_type(id, mode, kind, expected):
    calls = []
    checker = SimpleNamespace(id=id, mode=mode, kind=kind, custom=id.startswith("custom_"))
    value = query_interval(checker, lambda a, b: calls.append((a, b)) or a)
    assert calls == ([expected] if expected else [])
    assert value == (expected[0] if expected else 0)


async def test_only_top_three_auto_and_all_original_batches_before_variants(tmp_path):
    candidates = [{"name": "名字" + str(i), "handle": "toolman"} for i in range(12)]
    names = {item["name"] for item in candidates}
    checker = ScriptChecker("bilibili", lambda name, handle: "taken" if name in names else "available")
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0)
    events = [item async for item in runner.stream(candidates, [checker.id])]
    assert [name for name, _ in checker.calls[:12]] == [item["name"] for item in candidates]
    assert {data["row"] for event, data in events if event == "recommendation"} == {0, 1, 2}
    assert len(checker.calls) == 15
    ranking = next(data for event, data in events if event == "ranking")
    assert ranking["recommended_rows"] == [0, 1, 2]
    first_variant = next(i for i, (event, _) in enumerate(events) if event == "recommendation")
    assert sum(event == "result" for event, _ in events[:first_variant]) == 12
    progress = [data for event, data in events if event == "progress"]
    assert progress[-1]["completed"] == progress[-1]["total"] == 15
    assert progress[-1]["eta_seconds"] == 0


async def test_three_available_rows_do_not_promote_fourth_conflict_to_auto(tmp_path):
    checker = ScriptChecker("bilibili", lambda name, handle: "taken" if name == "名字3" else "available")
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0)
    candidates = [{"name": "名字" + str(i), "handle": "toolman"} for i in range(4)]
    events = [item async for item in runner.stream(candidates, [checker.id])]
    assert not any(event == "recommendation" for event, _ in events)
    assert len(checker.calls) == 4
    manual = [item async for item in runner.stream([candidates[3]], [checker.id], retry={"original": {checker.id: {"status": "taken"}}, "offset": 0})]
    assert any(event == "recommendation" for event, _ in manual)
    assert len(checker.calls) == 5


class ChallengeChecker:
    id, label, mode = "xiaohongshu", "Xiaohongshu", "login"
    def __init__(self, challenges=1): self.calls, self.challenges = [], challenges
    async def check(self, name, handle):
        self.calls.append(name)
        return Result("blocked" if len(self.calls) <= self.challenges else "available", search_url="https://example.test/")


async def test_verification_waits_for_user_and_retries_same_cell(tmp_path):
    browser = SimpleNamespace(show_window=AsyncMock(), hide_window=AsyncMock())
    checker = ChallengeChecker()
    other = ScriptChecker("x", lambda name, handle: "available")
    runner = CheckRunner({checker.id: checker, other.id: other}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0, browser=browser)
    candidates = [{"name": name, "handle": "toolman"} for name in ("名字甲", "名字乙")]
    stream = runner.stream(candidates, [checker.id, other.id])
    events = []
    try:
        while True:
            event, data = await asyncio.wait_for(anext(stream), 1)
            events.append((event, data))
            if event == "verification": break
        assert checker.calls == ["名字甲"]
        browser.show_window.assert_awaited_once_with(checker.id)
        browser.hide_window.assert_not_called()
        for _ in range(20):
            if len(other.calls) == 2: break
            await asyncio.sleep(0)
        assert len(other.calls) == 2  # 同时暂停的平台之外仍可查询。
        with pytest.raises(ValueError): await runner.resume(data["run_id"], checker.id, "stale")
        browser.show_window.assert_awaited_once_with(checker.id)
        await runner.resume(data["run_id"], checker.id, data["pause_id"])
        browser.hide_window.assert_awaited_once_with(checker.id)
        events += [item async for item in stream]
        assert checker.calls == ["名字甲", "名字甲", "名字乙"]
        assert events[-1][0] == "done" and not events[-1][1]["blocked"]
        assert all(data["result"]["status"] == "available" for event, data in events if event == "result")
        assert not runner.runs
    finally:
        await stream.aclose()


async def test_pause_is_cancelled_on_sse_disconnect(tmp_path):
    checker = ChallengeChecker()
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0,
                         browser=SimpleNamespace(show_window=AsyncMock(), hide_window=AsyncMock()))
    stream = runner.stream([{"name": "名字", "handle": "toolman"}], [checker.id])
    while (await anext(stream))[0] != "verification": pass
    await stream.aclose()
    assert checker.calls == ["名字"] and not runner.runs
    assert runner.history.list()[0]["stopped"] is True
    assert runner.history.list()[0]["results"][0]["result"]["status"] == "stopped"
    runner.browser.hide_window.assert_awaited_once_with(checker.id)


async def test_unsolved_verification_pauses_again_with_new_token(tmp_path):
    checker = ChallengeChecker(challenges=2)
    browser = SimpleNamespace(show_window=AsyncMock(), hide_window=AsyncMock())
    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0, browser=browser)
    stream = runner.stream([{"name": "名字", "handle": "toolman"}], [checker.id])
    previous = None
    try:
        for attempt in range(2):
            while True:
                event, pause = await anext(stream)
                if event == "verification": break
            assert len(checker.calls) == attempt + 1
            if previous:
                assert pause["pause_id"] != previous["pause_id"]
                with pytest.raises(ValueError): await runner.resume(pause["run_id"], checker.id, previous["pause_id"])
            await runner.resume(pause["run_id"], checker.id, pause["pause_id"])
            previous = pause
        events = [item async for item in stream]
        assert events[-1][0] == "done" and len(checker.calls) == 3
        assert browser.show_window.await_count == browser.hide_window.await_count == 2
    finally:
        await stream.aclose()


async def test_pause_endpoints_and_login_does_not_navigate_paused_page(tmp_path, fake_browser):
    checker = ChallengeChecker()
    fake_browser.show_window, fake_browser.hide_window, fake_browser.open_login = AsyncMock(), AsyncMock(), AsyncMock()
    app = make_app(tmp_path, fake_browser, checkers={checker.id: checker})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        pending = asyncio.create_task(client.post("/api/check", json={"candidates": [{"name": "名字", "handle": "toolman"}], "platforms": [checker.id]}))
        try:
            for _ in range(100):
                runs = app.state.runner.runs
                if runs and next(iter(runs.values()))["pauses"]: break
                await asyncio.sleep(0)
            run_id, run = next(iter(runs.items()))
            pause = run["pauses"][checker.id]
            assert (await client.post("/api/login/xiaohongshu", json={})).status_code == 409
            fake_browser.open_login.assert_not_called()
            base = f"/api/check/{run_id}/{checker.id}"
            assert (await client.post(base + "/show", json={"pause_id": pause["pause_id"]})).status_code == 200
            assert (await client.post(base + "/continue", json={"pause_id": pause["pause_id"]})).status_code == 200
            response = await asyncio.wait_for(pending, 1)
            assert "event: verification" in response.text and "event: done" in response.text
            assert (await client.post(base + "/continue?lang=en", json={"pause_id": pause["pause_id"]})).status_code == 409
        finally:
            if not pending.done(): pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
