"""原名优先、前三自动推荐；验证只检测并等待用户处理。"""

import asyncio
from contextlib import AsyncExitStack
from datetime import datetime, timezone
import math
import random
import time
from uuid import uuid4

from .i18n import t
from .platforms.base import Result
from .rules import check_candidate
from .scoring import rank_rows
from .variants import conflict_platforms, generate_variants, recommendations

BROWSER_PLATFORMS = {"bilibili", "douyin", "xiaohongshu"}


def query_interval(checker, uniform=None):
    uniform = uniform or random.uniform
    if checker.mode == "manual":
        return 0
    if checker.id in ("github", "x") or (getattr(checker, "custom", False) and getattr(checker, "kind", "") == "profile"):
        return uniform(0.3, 0.8)
    return uniform(1, 2)


class CheckRunner:
    def __init__(self, checkers, history, sleep=asyncio.sleep, interval=None, browser=None, verification_period=1):
        self.checkers, self.history, self.sleep = checkers, history, sleep
        self.interval, self.browser = interval, browser
        self.locks, self.last_finished, self.costs, self.runs = {}, {}, {}, {}
        self.verification_lock = asyncio.Lock()
        self.verification_period = verification_period

    def paused(self, platform):
        return any(platform in run["pauses"] for run in self.runs.values())

    def _pause(self, run_id, platform, pause_id):
        pause = self.runs.get(run_id, {}).get("pauses", {}).get(platform)
        if not pause or pause["pause_id"] != pause_id or pause.get("resuming"):
            raise ValueError(t("verification.missing"))
        return pause

    async def show_verification(self, run_id, platform, pause_id):
        pause = self._pause(run_id, platform, pause_id)
        if not pause["opened"]:
            raise ValueError(t("verification.queued"))
        await self.browser.show_window(platform)
        pause["opened"] = True
        return {"pause_id": pause_id, "opened": True}

    async def resume(self, run_id, platform, pause_id):
        pause = self._pause(run_id, platform, pause_id)
        async with pause["action_lock"]:
            if not pause["opened"] or pause.get("resuming"):
                raise ValueError(t("verification.queued"))
            await self.browser.hide_window(platform)
            pause["resuming"] = True
            pause["event"].set()
        return {"pause_id": pause_id, "resuming": True}

    async def _watch_verification(self, run_id, platform, pause):
        detect = getattr(self.browser, "verification_present", None)
        while not pause["event"].is_set():
            try:
                await asyncio.wait_for(pause["event"].wait(), self.verification_period)
            except TimeoutError:
                if detect is None:
                    continue
                try:
                    if await detect(platform) is not False:
                        continue
                    # 消失后再等一秒并复查，避免页面短暂刷新被当成验证已完成。
                    try:
                        await asyncio.wait_for(pause["event"].wait(), self.verification_period)
                        continue
                    except TimeoutError:
                        pass
                    if await detect(platform) is False and not pause["event"].is_set():
                        await self.resume(run_id, platform, pause["pause_id"])
                except Exception:
                    # 页面关闭或无法识别时保留手动继续入口，不自行放行。
                    continue

    async def _hide_cancelled_window(self, platform):
        # 撤销格子和父批次可能先后送来取消，收窗不能因此做到一半。
        task = asyncio.create_task(self.browser.hide_window(platform))
        interrupted = False
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                interrupted = True
            except Exception:
                break
        if not task.cancelled():
            try:
                task.result()
            except Exception:
                pass
        if interrupted:
            raise asyncio.CancelledError

    async def stream(self, candidates, platforms, *, checkers=None, retry=None):
        selected = checkers or {id: self.checkers[id] for id in platforms}
        details = {id: {"label": c.label, "mode": c.mode, "custom": bool(getattr(c, "custom", False)),
                        "kind": getattr(c, "kind", ""), "url_template": getattr(c, "url_template", "")} for id, c in selected.items()}
        record = {"id": uuid4().hex, "created_at": datetime.now(timezone.utc).isoformat(), "candidates": candidates,
                  "platforms": platforms, "platform_details": details, "results": [], "recommendations": {}, "recommended_rows": []}
        run = {"pauses": {}}
        self.runs[record["id"]] = run
        queue = asyncio.Queue()
        local_locks = {id: asyncio.Lock() for id in platforms}
        stopped = asyncio.Event()
        client_stopped = asyncio.Event()
        workers = set()
        login = set()
        originals = [{} for _ in candidates]
        cells = {}
        finished = False
        reserve = 4 if retry else min(3, len(candidates)) * 4
        pending = {id: (0 if retry else len(candidates)) + reserve for id in platforms}
        total = sum(pending.values())
        completed = 0
        phase = "variants" if retry else "original"
        interactive = self.browser is not None and hasattr(self.browser, "show_window") and hasattr(self.browser, "hide_window")
        if retry:
            if any(value["status"] == "blocked" for value in retry["original"].values()):
                stopped.set()
            login.update(id for id, value in retry["original"].items() if value["status"] == "login")

        def metrics():
            estimates = []
            for id, checker in selected.items():
                samples = self.costs.get(id, [])
                mean = sum(samples) / len(samples) if samples else (0 if checker.mode == "manual" else 0.55 if id in ("github", "x") or details[id]["kind"] == "profile" else 1.5)
                estimates.append(max(0, pending[id]) * mean)
            return {"completed": completed, "total": total, "eta_seconds": math.ceil(max(estimates, default=0)), "phase": phase, "paused": list(run["pauses"])}

        async def progress():
            await queue.put(("progress", metrics()))

        async def release_budget(rows):
            nonlocal total
            total -= rows * len(platforms)
            for id in platforms:
                pending[id] -= rows
            await progress()

        async def query(candidate, id, row, variant):
            async with local_locks[id]:
                if client_stopped.is_set():
                    raise asyncio.CancelledError
                validation = check_candidate(candidate["name"], candidate["handle"], [id])[id]
                if validation["verdict"] == "bad":
                    return Result("invalid", note="；".join(validation["reasons"])).to_dict()
                # 查重中途扫码登录成功后，后面的格子照常查，不再沿用“未登录”短路
                if id in login and getattr(self.browser, "login_status", {}).get(id) is True:
                    login.discard(id)
                if stopped.is_set() or id in login:
                    status = "blocked" if stopped.is_set() else "login"
                    return Result(status, note=t("runner." + status)).to_dict()
                checker = selected[id]
                while True:
                    started = time.monotonic()
                    if checker.mode != "manual" and id in self.last_finished:
                        interval = self.interval() if self.interval else query_interval(checker)
                        delay = interval - (time.monotonic() - self.last_finished[id])
                        if delay > 0:
                            await self.sleep(delay)
                    if stopped.is_set():
                        return Result("blocked", note=t("runner.blocked")).to_dict()
                    if client_stopped.is_set():
                        raise asyncio.CancelledError
                    try:
                        result = await checker.check(candidate["name"], candidate["handle"])
                    except Exception:
                        result = Result("error", note=t("runner.error"))
                    self.last_finished[id] = time.monotonic()
                    self.costs.setdefault(id, []).append(time.monotonic() - started)
                    self.costs[id] = self.costs[id][-20:]
                    if result.status == "blocked" and id in BROWSER_PLATFORMS and interactive:
                        pause = {"pause_id": uuid4().hex, "event": asyncio.Event(), "opened": False, "action_lock": asyncio.Lock()}
                        run["pauses"][id] = pause
                        message = {"run_id": record["id"], "platform": id, "row": row, "variant": variant,
                                   "pause_id": pause["pause_id"], "result": result.to_dict()}
                        if self.verification_lock.locked():
                            await queue.put(("verification", {**message, "opened": False, "queued": True}))
                        await progress()
                        async with self.verification_lock:
                            try:
                                pause["opened"] = True
                                await self.browser.show_window(id)
                                await queue.put(("verification", {**message, "opened": True, "queued": False}))
                                await self._watch_verification(record["id"], id, pause)
                            finally:
                                try:
                                    if pause["opened"] and not pause.get("resuming"):
                                        await self._hide_cancelled_window(id)
                                finally:
                                    run["pauses"].pop(id, None)
                        await queue.put(("verification_resumed", {"run_id": record["id"], "platform": id, "pause_id": pause["pause_id"]}))
                        continue
                    if result.status == "blocked":
                        stopped.set()
                    elif result.status == "login":
                        login.add(id)
                    return result.to_dict()

        async def all_platforms(candidate, row, variant=False):
            async def cell(id):
                nonlocal completed
                worker = asyncio.current_task()
                workers.add(worker)
                try:
                    result = await query(candidate, id, row, variant)
                    completed += 1
                    pending[id] -= 1
                    if not variant:
                        cells[row, id] = {"row": row, "platform": id, "result": result}
                        await queue.put(("result", {"row": row, "platform": id, "result": result}))
                    await progress()
                    return id, result
                finally:
                    workers.discard(worker)
            return dict(await asyncio.gather(*(cell(id) for id in platforms)))

        async def find(row, candidate, original, offset=0):
            if not conflict_platforms(original):
                await release_budget(4)
                return
            trials = []
            variants = generate_variants(candidate, original, platforms, details, offset=offset)

            async def panel(loading):
                await queue.put(("recommendation", {"row": row, "loading": loading and not stopped.is_set(), "checked": len(trials), "trials": list(trials),
                    "next_offset": offset + len(trials), "exhausted": len(variants) < 4 and len(trials) == len(variants),
                    "blocked": stopped.is_set(), "copy_prompt": t("copy.variants", name=candidate["name"]),
                    "choices": recommendations(candidate, original, trials, platforms, details)}))
            await panel(True)
            for item in variants:
                if stopped.is_set():
                    break
                pair = {key: item[key] for key in ("name", "handle")}
                results = await all_platforms(pair, row, variant=True)
                trials.append({"candidate": pair, "results": results, "group": item["group"]})
                if stopped.is_set() or all(value["status"] == "available" for value in results.values()):
                    break
                await panel(True)
            await panel(False)
            await release_budget(4 - len(trials))

        async def original_row(row):
            originals[row] = await all_platforms(candidates[row], row)

        async def produce():
            nonlocal phase
            async with AsyncExitStack() as stack:
                for id in sorted(platforms):
                    await stack.enter_async_context(self.locks.setdefault(id, asyncio.Lock()))
                if retry:
                    await find(0, candidates[0], retry["original"], retry["offset"])
                else:
                    for start in range(0, len(candidates), 10):
                        if start and not stopped.is_set():
                            await queue.put(("batch", {"number": start // 10 + 1, "total": (len(candidates) + 9) // 10}))
                        async with asyncio.TaskGroup() as group:
                            for row in range(start, min(start + 10, len(candidates))):
                                group.create_task(original_row(row))
                    scores = rank_rows(originals)
                    top = [score["row"] for score in scores[:3]]
                    record["recommended_rows"] = top
                    await queue.put(("ranking", {"recommended_rows": top, "scores": scores}))
                    auto = [row for row in top if conflict_platforms(originals[row]) and not stopped.is_set()]
                    phase = "variants"
                    await release_budget(reserve - len(auto) * 4)
                    async with asyncio.TaskGroup() as group:
                        for row in auto:
                            group.create_task(find(row, candidates[row], originals[row]))
            await queue.put(None)

        task = asyncio.create_task(produce())
        try:
            yield "start", {"id": record["id"], "batches": (len(candidates) + 9) // 10, "progress": metrics()}
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), 10)
                except TimeoutError:
                    if task.done():
                        await task
                    yield "ping", {}
                    continue
                if item is None:
                    break
                event, data = item
                if event == "result":
                    record["results"].append(data)
                elif event == "recommendation":
                    record["recommendations"][str(data["row"])] = data
                yield event, data
            await task
            finished = True
            if not retry:
                record["results"] = list(cells.values())
                record["stopped"] = False
                try:
                    self.history.append(record)
                except OSError:
                    yield "warning", {"message": t("runner.history")}
            yield "done", {"id": record["id"], "blocked": stopped.is_set()}
        finally:
            # 先同步标记并撤销所有格子，避免等待清理任务调度时又启动一次查询。
            client_stopped.set()
            for worker in tuple(workers):
                worker.cancel()
            if not task.done():
                task.cancel()

            async def cleanup():
                await asyncio.gather(task, return_exceptions=True)
                if not finished:
                    record["stopped"] = True
                    for row in range(len(candidates)):
                        for id in platforms:
                            result = retry["original"][id] if retry else Result("stopped", note=t("runner.stopped")).to_dict()
                            cells.setdefault((row, id), {"row": row, "platform": id, "result": result})
                    record["results"] = list(cells.values())
                    for panel in record["recommendations"].values():
                        panel["loading"] = False
                    try:
                        self.history.append(record)
                    except OSError:
                        pass
                self.runs.pop(record["id"], None)

            # 客户端断开时也要等子任务撤销完、收起验证窗口并保存停止记录。
            cleanup_task = asyncio.create_task(cleanup())
            await asyncio.shield(cleanup_task)
