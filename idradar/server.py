"""本机 API 与静态单页。"""

from contextlib import asynccontextmanager
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException as StarletteHTTPException

from .i18n import LANG, language, localize_data, platform_label, t
from .browser import BrowserManager
from .history import HistoryStore
from .custom_platforms import CustomPlatformStore
from .platforms.base import normalize
from .platforms.bilibili import BilibiliChecker
from .platforms.github import GitHubChecker
from .platforms.douyin import DouyinChecker
from .platforms.xiaohongshu import XiaohongshuChecker
from .platforms.x import XChecker
from .platforms.weixin_channels import WeixinChannelsChecker
from .platforms.custom import CustomChecker
from .runner import CheckRunner
from .login import LoginManager
from .parse_names import build_handle_prompt, merge_candidates, parse_names
from .prompts import naming_prompt
from .rules import PLATFORM_RULES, check_candidate
from .variants import generate_variants

STATIC_PATH = Path(__file__).parent / "static"


class Candidate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    handle: str = Field(default="", max_length=20000)


class CheckRequest(BaseModel):
    candidates: list[Candidate] = Field(min_length=1, max_length=300)
    platforms: list[str] = Field(min_length=1, max_length=16)


class RulesRequest(BaseModel):
    candidates: list[Candidate] = Field(max_length=300)
    platforms: list[str] = Field(max_length=16)


class VariantsRequest(BaseModel):
    candidate: Candidate
    original: dict[str, dict]
    offset: int = Field(default=0, ge=0, le=200)
    platforms: list[str] = Field(min_length=1, max_length=16)


class ParseRequest(BaseModel):
    text: str = Field(max_length=20000)
    existing: list[Candidate | str] = Field(default_factory=list, max_length=300)


class CustomSiteRequest(BaseModel):
    label: str = Field(min_length=1, max_length=12)
    url_template: str = Field(min_length=1, max_length=2000)
    kind: str


class VerificationRequest(BaseModel):
    pause_id: str = Field(min_length=1, max_length=80)


def create_app(*, history_store=None, browser=None, checkers=None, runner_options=None, custom_store=None, demo=False, login_manager=None):
    if demo:
        from .demo import DemoBrowser, DemoHistory, DemoSites, demo_checkers
        history, browser, sites, checkers = DemoHistory(), DemoBrowser(), DemoSites(), demo_checkers()
    else:
        history = history_store or HistoryStore()
        browser = browser or BrowserManager()
        sites = custom_store or CustomPlatformStore()
        checkers = checkers or {checker.id: checker for checker in (
            BilibiliChecker(browser), GitHubChecker(), DouyinChecker(browser), XiaohongshuChecker(browser), XChecker(), WeixinChannelsChecker(),
        )}
    options = ({"interval": lambda: 0} if demo else {}) | (runner_options or {})
    runner = CheckRunner(checkers, history, browser=browser, **options)
    logins = login_manager or LoginManager(browser)

    def sync_custom():
        try:
            records = sites.list()
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        active = {site["id"] for site in records}
        for id, checker in tuple(checkers.items()):
            if getattr(checker, "custom", False) and id not in active:
                del checkers[id]
        for site in records:
            if site["id"] not in checkers:
                if demo:
                    from .demo import DemoChecker
                    checkers[site["id"]] = DemoChecker(site["id"], site["label"], "manual" if site["kind"] == "search" else "auto", site)
                else:
                    checkers[site["id"]] = CustomChecker(site)
        return records

    def platform_list():
        sync_custom()
        return [{"id": c.id, "label": platform_label(c.id, c.label), "mode": c.mode,
                 "logged_in": browser.login_status.get(c.id),
                 "login_state": "logged_in" if browser.login_status.get(c.id) is True else "logged_out" if browser.login_status.get(c.id) is False else "unknown",
                 "target": PLATFORM_RULES.get(c.id, {}).get("target"),
                 "custom": bool(getattr(c, "custom", False)),
                 **({"kind": c.kind, "url_template": c.url_template} if bool(getattr(c, "custom", False)) else {})}
                for c in checkers.values()]

    @asynccontextmanager
    async def lifespan(app):
        yield
        await browser.close()

    app = FastAPI(title=t('app.title'), lifespan=lifespan)
    app.state.runner = runner
    app.state.demo = demo
    app.state.logins = logins

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request, exc):
        detail = t("http.not_found") if exc.status_code == 404 else t("http.method") if exc.status_code == 405 else str(exc.detail)
        return JSONResponse(localize_data({"detail": detail}), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request, exc):
        # 不回显整段输入，只提示检查格式和查询数量。
        return JSONResponse(localize_data({"detail": t("input")}), status_code=422)

    @app.middleware("http")
    async def local_only(request: Request, call_next):
        token = LANG.set("en" if request.query_params.get("lang") == "en" else "zh")
        try:
            host = request.url.hostname
            if host not in ("localhost", "127.0.0.1", "::1", "testserver"):
                return JSONResponse(localize_data({"detail": t('local')}), status_code=403)
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return JSONResponse(localize_data({"detail": t('origin')}), status_code=403)
            response = await call_next(request)
            response.headers["Cache-Control"] = "no-store"
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            return response
        finally:
            LANG.reset(token)

    @app.get("/")
    async def index():
        return FileResponse(STATIC_PATH / "index.html")

    @app.get("/api/prompt")
    async def get_prompt():
        from .demo import SAMPLES
        return localize_data({"prompt": naming_prompt(), "demo": demo, "sample": SAMPLES[language()] if demo else ""})

    @app.post("/api/parse-names")
    async def recognize_names(body: ParseRequest):
        candidates = parse_names(body.text)
        existing = [candidate.model_dump() if isinstance(candidate, Candidate) else {"name": candidate, "handle": ""} for candidate in body.existing]
        return merge_candidates(candidates, existing)

    @app.get("/api/platforms")
    async def get_platforms():
        refresh = getattr(browser, "refresh_login_status", None)
        if refresh:
            await refresh()
        return localize_data({"platforms": platform_list(), "browser_open": bool(getattr(browser, "is_open", False))})

    def validate_platforms(platforms):
        sync_custom()
        if len(set(platforms)) != len(platforms) or any(platform not in checkers for platform in platforms):
            raise HTTPException(400, t('platforms'))

    @app.get("/api/rules")
    async def get_rules():
        custom_rules = {site["id"]: {"label": site["label"], "custom": True, "notes": [t('rule.custom')], "sources": []} for site in sync_custom()}
        return localize_data({"platforms": {**PLATFORM_RULES, **custom_rules}})

    @app.get("/api/rules/source")
    async def get_rules_source():
        return FileResponse(STATIC_PATH.parents[1] / "docs" / "platform_naming_rules.md", media_type="text/plain; charset=utf-8")

    @app.post("/api/rules/check")
    async def validate_names(body: RulesRequest):
        validate_platforms(body.platforms)
        validations = [check_candidate(candidate.name, candidate.handle, body.platforms) for candidate in body.candidates]
        names = [candidate.name for candidate, checks in zip(body.candidates, validations)
                 if not candidate.handle.strip() or any(checks[id]["verdict"] == "bad" for id in body.platforms if PLATFORM_RULES.get(id, {}).get("target") == "handle")]
        return localize_data({"validations": validations, "handle_names": names, "handle_prompt": build_handle_prompt(names),
                              "handle_prompt_i18n": {code: build_handle_prompt(names, code) for code in ("zh", "en")}})

    @app.get("/api/custom-platforms")
    async def list_custom_sites():
        return localize_data({"sites": sync_custom()})

    @app.post("/api/custom-platforms")
    async def add_custom_site(body: CustomSiteRequest):
        try:
            site = sites.add(body.label, body.url_template, body.kind)
        except (ValueError, OSError) as error:
            raise HTTPException(400, str(error) if isinstance(error, ValueError) else t("site.file")) from None
        return localize_data({"site": site, "platforms": platform_list()})

    @app.delete("/api/custom-platforms/{id}")
    async def delete_custom_site(id: str):
        try:
            sites.delete(id)
        except (ValueError, OSError) as error:
            raise HTTPException(400, str(error) if isinstance(error, ValueError) else t("site.file")) from None
        return localize_data({"platforms": platform_list()})

    @app.post("/api/variants")
    async def variants(body: VariantsRequest):
        validate_platforms(body.platforms)
        if not normalize(body.candidate.name):
            raise HTTPException(400, t('empty_name'))
        if set(body.original) != set(body.platforms) or any(item.get("status") not in ("available", "taken", "similar", "invalid", "manual", "login", "blocked", "error") for item in body.original.values()):
            raise HTTPException(400, t("original"))
        return localize_data({"variants": generate_variants(body.candidate.model_dump(), body.original, body.platforms,
                {item["id"]: item for item in platform_list()}, offset=body.offset)})

    @app.post("/api/variants/check")
    async def check_more_variants(body: VariantsRequest):
        await variants(body)
        selected = {id: checkers[id] for id in body.platforms}

        stream = runner.stream([body.candidate.model_dump()], body.platforms, checkers=selected,
                              retry={"original": body.original, "offset": body.offset})
        return StreamingResponse(check_events(stream), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    async def check_events(stream):
        try:
            async for event, data in stream:
                yield f"event: {event}\ndata: {json.dumps(localize_data(data), ensure_ascii=False)}\n\n"
        finally:
            await stream.aclose()

    @app.post("/api/login/{platform}")
    async def login(platform: str):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        if platform not in ("douyin", "xiaohongshu"):
            raise HTTPException(400, t('login.unsupported'))
        if runner.paused(platform):
            raise HTTPException(409, t("qr.busy"))
        try:
            return localize_data(await logins.start(platform))
        except ValueError as error:
            raise HTTPException(400, (str(error).splitlines() or [t('login.failed')])[0][:400]) from None
        except Exception:
            raise HTTPException(400, t("login.failed")) from None

    @app.get("/api/login/{platform}")
    async def login_status(platform: str):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        try:
            return localize_data(await logins.status(platform))
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        except Exception:
            raise HTTPException(400, t("login.failed")) from None

    @app.post("/api/login/{platform}/continue")
    async def finish_login(platform: str):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        try:
            return localize_data(await logins.finish_fallback(platform))
        except ValueError as error:
            raise HTTPException(400, str(error)) from None
        except Exception:
            raise HTTPException(400, t("login.failed")) from None

    @app.delete("/api/login/{platform}")
    async def cancel_login(platform: str):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        try:
            await logins.cancel(platform)
        except Exception:
            raise HTTPException(400, t("login.failed")) from None
        return {"ok": True}

    @app.post("/api/login/{platform}/window")
    async def open_login_window(platform: str):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        try:
            await logins.show_window(platform)
            return {"ok": True}
        except Exception:
            raise HTTPException(400, t("login.failed")) from None

    @app.post("/api/check/{run_id}/{platform}/show")
    async def show_verification(run_id: str, platform: str, body: VerificationRequest):
        try:
            return await runner.show_verification(run_id, platform, body.pause_id)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(400, t("verification.unavailable")) from None

    @app.post("/api/check/{run_id}/{platform}/continue")
    async def continue_verification(run_id: str, platform: str, body: VerificationRequest):
        try:
            return await runner.resume(run_id, platform, body.pause_id)
        except ValueError as error:
            raise HTTPException(409, str(error)) from None
        except Exception:
            raise HTTPException(400, t("verification.unavailable")) from None

    @app.post("/api/check")
    async def check(body: CheckRequest):
        validate_platforms(body.platforms)
        candidates = [candidate.model_dump() for candidate in body.candidates]
        normalized = [normalize(c["name"]) for c in candidates]
        if any(not name for name in normalized) or len(set(normalized)) != len(normalized):
            raise HTTPException(400, t('duplicate'))
        selected = {platform: checkers[platform] for platform in body.platforms}

        return StreamingResponse(check_events(runner.stream(candidates, body.platforms, checkers=selected)),
                                 media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})

    @app.post("/api/probe/{platform}")
    async def capture_probe(platform: str, body: Candidate):
        if demo:
            raise HTTPException(400, t("demo.disabled"))
        from .probe import capture_page

        if platform not in ("bilibili", "douyin", "xiaohongshu"):
            raise HTTPException(400, t('probe.unsupported'))
        try:
            html, png = await capture_page(browser, platform, body.name)
            return localize_data({"html": str(html), "png": str(png), "note": t('probe.privacy')})
        except Exception:
            raise HTTPException(400, t('probe.failed')) from None

    @app.get("/api/history")
    async def get_history():
        try:
            return localize_data({"history": history.list()})
        except OSError:
            raise HTTPException(400, t('history.read')) from None

    app.mount("/static", StaticFiles(directory=STATIC_PATH), name="static")
    return app


app = create_app()
