import asyncio

import httpx
import pytest

from idradar.history import HistoryStore
from idradar.platforms.base import Checker, Result
from idradar.runner import CheckRunner
from test_server import make_app


PAIR = {"name": "工具人", "handle": "toolman"}


class ScriptChecker(Checker):
    def __init__(self, id, answer):
        self.id, self.label, self.answer = id, id, answer
        self.calls, self.active, self.peak = [], 0, 0

    async def check(self, name, handle):
        self.active += 1
        self.peak = max(self.peak, self.active)
        self.calls.append((name, handle))
        await asyncio.sleep(0)
        self.active -= 1
        return Result(self.answer(name, handle))


def runner_for(tmp_path, checkers, **kwargs):
    return CheckRunner({c.id: c for c in checkers}, HistoryStore(tmp_path / "history.jsonl"), interval=lambda: 0, **kwargs)


def last_panel(events):
    return [data for kind, data in events if kind == "recommendation"][-1]


async def test_auto_checks_all_selected_platforms_and_stops_at_first_unified(tmp_path):
    first = ScriptChecker("bilibili", lambda name, handle: "taken" if name == PAIR["name"] else "available")
    second = ScriptChecker("github", lambda name, handle: "available")
    runner = runner_for(tmp_path, [first, second])
    events = [item async for item in runner.stream([PAIR], ["bilibili", "github"])]
    panel = last_panel(events)
    assert panel["checked"] == 1 and not panel["loading"]
    assert panel["choices"]["partial"]["ready"] and panel["choices"]["unified"]["ready"]
    assert first.calls == second.calls == [("工具人", "toolman"), ("工具人本人", "toolman")]
    assert all(checker.peak == 1 for checker in (first, second))
    assert len([data for kind, data in events if kind == "result"]) == 2
    record = runner.history.list()[0]
    assert record["recommendations"]["0"]["checked"] == 1


@pytest.mark.parametrize("status", ["available", "manual", "login", "invalid", "error", "blocked"])
async def test_non_conflict_status_never_generates_variants(tmp_path, status):
    checker = ScriptChecker("bilibili", lambda name, handle: status)
    events = [item async for item in runner_for(tmp_path, [checker]).stream([PAIR], ["bilibili"])]
    assert not any(kind == "recommendation" for kind, _ in events)
    assert len(checker.calls) == 1


@pytest.mark.parametrize("status", ["taken", "similar"])
async def test_max_four_and_next_batch_uses_new_pairs(tmp_path, status):
    checker = ScriptChecker("bilibili", lambda name, handle: status)
    runner = runner_for(tmp_path, [checker])
    events = [item async for item in runner.stream([PAIR], ["bilibili"])]
    assert last_panel(events)["checked"] == 4
    assert len(checker.calls) == 5
    assert not last_panel(events)["choices"]["partial"]["ready"]
    more = [item async for item in runner.stream([PAIR], ["bilibili"], retry={"original": {"bilibili": {"status": status}}, "offset": 4})]
    assert last_panel(more)["checked"] == 4 and last_panel(more)["next_offset"] == 8
    assert len(set(checker.calls)) == 9
    assert len(runner.history.list()) == 1  # 重试不把变体另存成候选批次。


async def test_blocked_variant_stops_other_variants_after_all_original_batches(tmp_path):
    checker = ScriptChecker("bilibili", lambda name, handle: "blocked" if name.endswith("本人") else "taken")
    candidates = [{"name": "工具人" + str(i), "handle": "toolman"} for i in range(12)]
    events = [item async for item in runner_for(tmp_path, [checker]).stream(candidates, ["bilibili"])]
    assert sum(name.endswith("本人") for name, _ in checker.calls) == 1
    assert [name for name, _ in checker.calls[:12]] == [candidate["name"] for candidate in candidates]
    assert any(kind == "batch" for kind, _ in events)
    assert events[-1][1]["blocked"]
    assert len([data for kind, data in events if kind == "result"]) == 12
    assert all(not data["loading"] for kind, data in events if kind == "recommendation" and data["blocked"])


async def test_twelve_rows_advance_to_second_batch_with_rate_limits(tmp_path):
    checker = ScriptChecker("bilibili", lambda name, handle: "available")
    delays = []

    async def sleep(delay):
        delays.append(delay)

    runner = CheckRunner({checker.id: checker}, HistoryStore(tmp_path / "history.jsonl"), sleep=sleep, interval=lambda: 3)
    candidates = [{"name": "名字" + str(i), "handle": "toolman"} for i in range(12)]
    events = [item async for item in runner.stream(candidates, [checker.id])]
    assert [name for name, _ in checker.calls] == [c["name"] for c in candidates]
    assert [data for kind, data in events if kind == "batch"] == [{"number": 2, "total": 2}]
    assert len(delays) == 11 and all(2 <= delay <= 4 for delay in delays)
    assert checker.peak == 1


async def test_blocked_first_batch_stops_every_platform_and_later_batches(tmp_path):
    checkers = [ScriptChecker("bilibili", lambda name, handle: "blocked"), ScriptChecker("github", lambda name, handle: "available")]
    candidates = [{"name": "名字" + str(i), "handle": "toolman"} for i in range(12)]
    events = [item async for item in runner_for(tmp_path, checkers).stream(candidates, [c.id for c in checkers])]
    assert len(checkers[0].calls) == 1 and len(checkers[1].calls) <= 1
    assert not any(kind == "batch" for kind, _ in events)
    cells = [data for kind, data in events if kind == "result"]
    assert len(cells) == 24 and all(data["result"]["status"] == "blocked" for data in cells if data["row"] >= 10)


async def test_twelve_rows_api_and_more_variants_endpoint(tmp_path, fake_browser):
    checker = ScriptChecker("bilibili", lambda name, handle: "available" if name.startswith("名字") else "taken")
    app = make_app(tmp_path, fake_browser, checkers={checker.id: checker})
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        response = await client.post("/api/check", json={"candidates": [{"name": "名字" + str(i), "handle": "toolman"} for i in range(12)], "platforms": [checker.id]})
        assert response.status_code == 200 and response.text.count("event: result") == 12 and '"number": 2' in response.text
        response = await client.post("/api/variants/check", json={"candidate": PAIR, "platforms": [checker.id], "original": {checker.id: {"status": "taken"}}, "offset": 4})
        assert response.status_code == 200 and '"next_offset": 8' in response.text
        assert '"checked": 4' in response.text and "event: done" in response.text


async def test_retry_cannot_ignore_original_block(tmp_path):
    checker = ScriptChecker("bilibili", lambda name, handle: "available")
    events = [item async for item in runner_for(tmp_path, [checker]).stream([PAIR], [checker.id], retry={"original": {checker.id: {"status": "blocked"}}, "offset": 0})]
    assert not checker.calls and events[-1][1]["blocked"]
