from unittest.mock import AsyncMock

import httpx

import idradar.login as login_module
from idradar.login import LoginManager
from idradar.platforms import xiaohongshu
from test_browser_manager import managed_browser
from test_server import make_app


async def test_qr_api_refresh_status_success_and_unknown_flag(tmp_path, managed_browser, monkeypatch):
    browser, contexts, _ = managed_browser
    monkeypatch.setattr(login_module, "wait_for_visible", AsyncMock())
    clock = [0]
    manager = LoginManager(browser, clock=lambda: clock[0])
    app = make_app(tmp_path, browser, login_manager=manager)
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
            states = (await client.get("/api/platforms")).json()["platforms"]
            assert next(item for item in states if item["id"] == "xiaohongshu")["login_state"] == "unknown"
            qr = login_module.QR_IMAGES["xiaohongshu"]
            async with browser.page("xiaohongshu") as page:
                page.context.visible_selectors.update((".login-container", qr))
                page.context.attributes[(qr, "src")] = "data:image/png;base64,QUJD"
            response = await client.post("/api/login/xiaohongshu?lang=en", json={})
            assert response.status_code == 200
            first = response.json()
            assert first["status"] == "qr" and first["expires_in"] == 120 and first["qr_image"].startswith("data:image/png;base64,")
            clock[0] = 121
            assert (await client.get("/api/login/xiaohongshu")).json()["status"] == "expired"
            second = (await client.post("/api/login/xiaohongshu", json={})).json()
            assert second["session_id"] != first["session_id"]
            contexts[0].visible_selectors = {xiaohongshu.LOGGED_IN_SELECTOR}
            assert (await client.get("/api/login/xiaohongshu")).json()["status"] == "logged_in"
            states = (await client.get("/api/platforms")).json()["platforms"]
            assert next(item for item in states if item["id"] == "xiaohongshu")["login_state"] == "logged_in"
            assert (await client.delete("/api/login/xiaohongshu")).status_code == 200
            assert (await client.get("/api/login/xiaohongshu")).status_code == 400
    finally:
        await browser.close()
