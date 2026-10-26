"""抖音选择器尚待登录后实测，可用 probe 抓页调整。"""

from urllib.parse import quote

from ..i18n import t
from .login_search import LoginSearchChecker

# 用户卡片本身就是指向主页的链接，里面有头像和“抖音号: …”
CARD_SELECTOR = 'a[href*="/user/"]:has([data-e2e="live-avatar"]):has-text("抖音号")'
# 卡片里第一个 <p> 是昵称（第二个是简介）
NAME_SELECTOR = 'p'
LINK_SELECTOR = 'a[href*="/user/"]'
LOGIN_SELECTOR = '[data-e2e="login-dialog"], .login-mask, :text-is("登录后查看搜索结果")'
LOGGED_IN_SELECTOR = '[data-e2e="user-avatar"], [data-e2e="profile-icon"]'
BLOCKED_SELECTOR = '#captcha_container, .captcha_verify_container, iframe[src*="verifycenter"], :text("请完成下列验证"), :text("滑动滑块")'
EMPTY_SELECTOR = '[data-e2e="search-empty"], :text("暂无搜索结果")'
# 登录后才会下发的会话 Cookie（未登录访客没有）
LOGIN_COOKIES = ("sessionid", "sessionid_ss", "sid_guard")
LOGIN_URL = "https://www.douyin.com/"


def search_url(name):
    return "https://www.douyin.com/search/" + quote(name) + "?type=user"


class DouyinChecker(LoginSearchChecker):
    id, label = "douyin", t('platform.douyin')
    search_url = staticmethod(search_url)
    card_selector, name_selector, link_selector = CARD_SELECTOR, NAME_SELECTOR, LINK_SELECTOR
    login_selector, logged_in_selector = LOGIN_SELECTOR, LOGGED_IN_SELECTOR
    login_cookies = LOGIN_COOKIES
    blocked_selector, empty_selector = BLOCKED_SELECTOR, EMPTY_SELECTOR
