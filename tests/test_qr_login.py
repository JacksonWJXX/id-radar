import base64
from unittest.mock import AsyncMock

import pytest

import idradar.login as login_module
from idradar.login import LoginManager
from idradar.platforms import douyin, xiaohongshu
from test_browser_manager import managed_browser, PNG


async def test_qr_from_visible_region_expiry_refresh_and_success(managed_browser, monkeypatch):
    manager, contexts, _ = managed_browser
    monkeypatch.setattr(login_module, "wait_for_visible", AsyncMock())
    clock = [0]
    logins = LoginManager(manager, clock=lambda: clock[0])
    try:
        qr = login_module.QR_IMAGES["xiaohongshu"]
        async with manager.page("xiaohongshu") as page:
            page.context.visible_selectors.update((".login-container", qr))
            page.context.attributes[(qr, "src")] = "data:image/png;base64," + base64.b64encode(PNG).decode("ascii")
        first = await logins.start("xiaohongshu")
        assert first["status"] == "qr" and first["expires_in"] == 120
        # 直接用页面上已加载好的二维码图片，不截整块区域
        assert base64.b64decode(first["qr_image"].split(",", 1)[1]) == PNG
        assert not page.screenshots
        assert not contexts[0].cdp_calls and not manager.probe_path.exists()
        clock[0] = 121
        expired = await logins.status("xiaohongshu")
        assert expired["status"] == "expired" and not expired["qr_image"]
        renewed = await logins.start("xiaohongshu")
        assert renewed["session_id"] != first["session_id"] and renewed["expires_in"] == 120
        assert len(contexts[0].pages) == 1
        contexts[0].visible_selectors = {xiaohongshu.LOGGED_IN_SELECTOR}
        success = await logins.status("xiaohongshu")
        assert success["status"] == "logged_in" and success["logged_in"] is True
        assert not success["qr_image"] and not contexts[0].cdp_calls
    finally:
        await manager.close()


async def test_missing_qr_falls_back_shows_window_and_continues_only_if_confirmed(managed_browser, monkeypatch):
    manager, contexts, _ = managed_browser
    monkeypatch.setattr(login_module, "wait_for_visible", AsyncMock())
    logins = LoginManager(manager, qr_wait=0)
    try:
        fallback = await logins.start("douyin")
        assert fallback["status"] == "fallback" and manager.window_visible
        assert "已保存页面快照" in fallback["note"]
        assert len(list(manager.probe_path.glob("*.html"))) == len(list(manager.probe_path.glob("*.png"))) == 1
        assert (await logins.finish_fallback("douyin"))["status"] == "fallback"
        assert manager.window_visible
        contexts[0].session[douyin.LOGIN_URL] = [{"name": "sessionid", "value": "fake-session"}]
        # 窗口登录成功后仍等用户点继续，不能自动把用户正在操作的窗口藏起来。
        assert (await logins.status("douyin"))["status"] == "fallback"
        result = await logins.finish_fallback("douyin")
        assert result["status"] == "logged_in" and not manager.window_visible
    finally:
        await manager.close()


async def test_xhs_qr_missing_and_cancel_fallback(managed_browser, monkeypatch):
    manager, _, _ = managed_browser
    monkeypatch.setattr(login_module, "wait_for_visible", AsyncMock())
    logins = LoginManager(manager, qr_wait=0)
    try:
        result = await logins.start("xiaohongshu")
        assert result["status"] == "fallback" and result["logged_in"] is None
        assert manager.window_visible
        await logins.cancel("xiaohongshu")
        assert not manager.window_visible
        with pytest.raises(ValueError):
            await logins.status("xiaohongshu")
    finally:
        await manager.close()


async def test_verification_image_is_not_presented_as_qr(managed_browser, monkeypatch):
    manager, contexts, _ = managed_browser
    monkeypatch.setattr(login_module, "wait_for_visible", AsyncMock())
    logins = LoginManager(manager, qr_wait=0)
    try:
        async with manager.page("xiaohongshu") as page:
            page.context.visible_selectors.update((".login-container", login_module.QR_IMAGES["xiaohongshu"], "#captcha"))
        result = await logins.start("xiaohongshu")
        assert result["status"] == "fallback" and not result["qr_image"]
        assert manager.window_visible
        assert all("clip" not in kwargs for kwargs in page.screenshots)
    finally:
        await manager.close()


async def test_douyin_qr_read_from_loaded_image(managed_browser, monkeypatch):
    manager, _, _ = managed_browser
    logins = LoginManager(manager, qr_wait=0)
    try:
        qr = login_module.QR_IMAGES["douyin"]
        async with manager.page("douyin") as page:
            page.context.visible_selectors.add(qr)
            page.context.attributes[(qr, "src")] = "data:image/png;base64,QUJD"
        result = await logins.start("douyin")
        assert result["status"] == "qr" and result["qr_image"] == "data:image/png;base64,QUJD"
        assert not manager.window_visible
    finally:
        await manager.close()
