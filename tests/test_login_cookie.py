from types import SimpleNamespace

from idradar.platforms import douyin, xiaohongshu
from idradar.platforms.login_search import has_login_cookie


def fake_context(cookies):
    async def get(url):
        return cookies
    return SimpleNamespace(cookies=get)


async def test_session_cookie_means_logged_in():
    ctx = fake_context([{"name": "sessionid", "value": "abc"}])
    assert await has_login_cookie(ctx, "https://www.douyin.com/", douyin.LOGIN_COOKIES)


async def test_guest_cookies_are_not_login():
    ctx = fake_context([{"name": "ttwid", "value": "x"}, {"name": "sessionid", "value": ""}])
    assert not await has_login_cookie(ctx, "https://www.douyin.com/", douyin.LOGIN_COOKIES)
    assert not await has_login_cookie(fake_context([{"name": "a1", "value": "x"}]), "https://www.xiaohongshu.com/", xiaohongshu.LOGIN_COOKIES)


async def test_cookie_read_failure_is_not_login():
    async def broken(url):
        raise RuntimeError("浏览器已关闭")
    assert not await has_login_cookie(SimpleNamespace(cookies=broken), "https://x", ("sessionid",))
