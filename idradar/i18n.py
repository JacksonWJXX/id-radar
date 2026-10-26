"""请求级语言与服务端文案；原始账号名、用户输入和网址不翻译。"""

from contextvars import ContextVar
from functools import lru_cache
import json
from pathlib import Path
import re

LANG = ContextVar("idradar_language", default="zh")
# 每项为中文、英文。两种语言均从同一组键构建，测试还校验占位符一致。
PAIRS = {
    "platform.bilibili": ("B站", "Bilibili"),
    "platform.douyin": ("抖音", "Douyin"),
    "platform.xiaohongshu": ("小红书", "Xiaohongshu (RED)"),
    "platform.weixin_channels": ("视频号", "WeChat Channels"),
    "platform.github": ("GitHub", "GitHub"), "platform.x": ("X", "X"),
    "app.title": ("ID 雷达", "ID Radar"),
    "input": ("输入格式不正确：最多 300 个候选，每批自动查 10 个，请检查字段和数量", "Invalid input: up to 300 candidates, checked in batches of 10. Please check the fields and counts."),
    "original": ("原始查询结果不完整", "The original results are incomplete."),
    "local": ("只允许本机访问", "Only local access is allowed."),
    "origin": ("不允许跨来源访问本机 API", "Cross-origin access to the local API is not allowed."),
    "http.not_found": ("没有这个接口或页面", "This endpoint or page does not exist."),
    "http.method": ("此接口不支持该请求方式", "This request method is not supported."),
    "cli.description": ("ID 雷达", "ID Radar"),
    "cli.demo": ("离线演示", "Offline demo"),
    "platforms": ("平台选择无效或重复", "The platform selection is invalid or contains duplicates."),
    "empty_name": ("原名不能为空", "The original name cannot be empty."),
    "duplicate": ("名字不能为空或重复", "Names cannot be empty or duplicated."),
    "login.unsupported": ("该平台不需要登录", "This platform does not require a browser login."),
    "login.opened": ("已在 ID 雷达专用浏览器中打开登录标签页，请自行登录；窗口可以保持打开并继续查重", "A login tab is open in the dedicated ID Radar browser. Sign in yourself; you can keep it open while checking names."),
    "login.failed": ("登录窗口打开失败", "Could not open the login window."),
    "probe.unsupported": ("该平台没有浏览器抓页功能", "Browser snapshots are not supported for this platform."),
    "probe.privacy": ("文件可能包含你的账号信息，只在本机，不会上传", "Files may contain your account information. They stay on this computer and are not uploaded."),
    "probe.failed": ("抓页失败，请检查专用浏览器与网络；已关闭的窗口会在下次操作时重开", "Could not capture the page. Check the dedicated browser and network; a closed window will reopen next time."),
    "history.read": ("历史记录读取失败，请检查目录权限", "Could not read history. Check directory permissions."),
    "runner.login": ("该平台未登录，本格未查询", "Not signed in to this platform; this cell was not checked."),
    "runner.stopped": ("已停止，本格未查完", "Stopped before this cell finished."),
    "verification.queued": ("验证窗口正在排队，请先完成前一个平台的验证", "This verification is queued. Complete the previous platform's verification first."),
    "runner.blocked": ("本次查询出现验证或风控，后续批次与变体已停止；本格未查询", "Verification or rate limiting was detected. Later batches and variants have stopped; this cell was not checked."),
    "runner.error": ("查询失败，请稍后重试", "The check failed. Please try again later."),
    "runner.history": ("本次查询已完成，但历史记录写入失败，请检查目录权限", "Checks finished, but history could not be saved. Check directory permissions."),
    "rule.unknown": ("尚未收录该平台规则", "Rules for this platform have not been collected."),
    "rule.handle": ("未填英文 handle", "No English handle provided."),
    "rule.max": ("长度 {length}，超过 {limit} 字符", "Length {length} exceeds the {limit}-character limit."),
    "rule.min": ("长度 {length}，少于 {limit} 字符", "Length {length} is below the {limit}-character minimum."),
    "rule.min_unknown": ("最短长度未查定", "The minimum length is unconfirmed."),
    "rule.max_unknown": ("最长长度未查定", "The maximum length is unconfirmed."),
    "rule.conflict": ("长度资料有矛盾，以平台提示为准", "Length sources conflict; follow the platform's instructions."),
    "rule.cjk_unknown": ("汉字计数未查定，当前仅按每字 1 字符估算", "CJK counting is unconfirmed; currently estimating one unit per character."),
    "rule.forbidden": ("含{category}，该平台不允许", "Contains {category}, which this platform does not allow."),
    "rule.category_unknown": ("{category}是否允许尚未查定", "Whether {category} are allowed is unconfirmed."),
    "rule.hyphen_edges": ("连字符不能在开头或结尾", "Hyphens cannot appear at the beginning or end."),
    "rule.hyphen_double": ("连字符不能连续", "Consecutive hyphens are not allowed."),
    "rule.x_reserved": ("X/Admin/Twitter 的受限用法未查定，请以平台提示为准", "Restrictions on X/Admin/Twitter are unconfirmed; follow the platform's instructions."),
    "rule.custom": ("自定义网站，规则未知", "Custom website; naming rules are unknown."),
    "char.cjk": ("中文", "Chinese characters"), "char.latin": ("英文字母", "Latin letters"),
    "char.digit": ("数字", "digits"), "char.underscore": ("下划线", "underscores"),
    "char.hyphen": ("连字符", "hyphens"), "char.space": ("空格", "spaces"),
    "char.middle_dot": ("中间点", "middle dots"), "char.other_punct": ("其他符号或非中英字符", "other symbols or non-Chinese/non-Latin characters"), "char.emoji": ("emoji", "emoji"),
    "site.label": ("网站名须为 1～12 字", "The website name must contain 1 to 12 characters."),
    "site.kind": ("请选择个人主页地址或搜索页", "Choose a profile URL or a search page."),
    "site.placeholder": ("网址必须含 {name} 或 {handle}", "The URL must contain {name} or {handle}."),
    "site.template": ("网址仅支持 {name} 和 {handle} 占位符，不能含空白", "Only {name} and {handle} placeholders are supported; whitespace is not allowed."),
    "site.url": ("请填写不含账号密码的完整 HTTP(S) 网址", "Enter a complete HTTP(S) URL without a username or password."),
    "site.file": ("自定义网站文件无法读取，请检查 custom_platforms.json", "Could not read custom websites. Check custom_platforms.json."),
    "site.limit": ("最多添加 10 个自定义网站，请先删除一个", "You can add up to 10 custom websites. Delete one first."),
    "site.missing": ("该自定义网站不存在", "This custom website does not exist."),
    "custom.search": ("自定义搜索页，请打开网站自行判断；规则未知", "Open this custom search page and check it yourself; naming rules are unknown."),
    "custom.available": ("该网址返回 404，不保证一定能注册", "This URL returned 404. Registration is not guaranteed."),
    "custom.extra": ("自定义网站主页", "Custom website profile"),
    "custom.taken": ("该网址返回 200，请打开主页核对；网站可能存在统一返回成功的页面", "This URL returned 200. Open it to confirm; some websites also return success for error pages."),
    "custom.http": ("网站返回 HTTP {status}，请打开网址自行判断", "The website returned HTTP {status}. Open the URL to check it yourself."),
    "custom.error": ("网络请求失败，请打开网址自行判断", "The request failed. Open the URL to check it yourself."),
    "connect": ("连不上 {platform}（{domain}），可能需要开代理后重试", "Cannot connect to {platform} ({domain}). You may need to enable a proxy and try again."),
    "github.available": ("未找到该 handle 的账号，不保证一定能注册（可能为保留用户名）", "No account was found for this handle. Registration is not guaranteed; it may be reserved."),
    "github.taken": ("GitHub 仅查英文 handle", "Only GitHub handles are checked."),
    "github.blocked": ("GitHub 限流或拒绝访问，已停止后续查询", "GitHub rate-limited or denied access. Further checks have stopped."),
    "github.http": ("GitHub 返回 HTTP {status}", "GitHub returned HTTP {status}."),
    "github.error": ("GitHub 请求失败或响应格式变化，请稍后重试", "The GitHub request failed or its response format changed. Try again later."),
    "x.available": ("X 上没有这个 handle 的主页；保留词或受限规则仍可能导致无法注册", "No X profile was found for this handle. Reserved names or restrictions may still prevent registration."),
    "x.taken": ("该 handle 有主页（含被封禁或停用的账号，名字仍被占用）；X 显示名可重名，本工具不查显示名", "This handle has a profile, including suspended or deactivated accounts that may keep their names. X display names can be duplicated and are not checked."),
    "x.blocked": ("X 限流或拒绝访问，已停止本批次后续查询，请稍后再试", "X rate-limited or denied access. Further checks have stopped; try again later."),
    "x.http": ("X 返回 HTTP {status}", "X returned HTTP {status}."),
    "bili.blocked": ("出现验证页，已停止 B 站后续查询，请手动处理", "Bilibili verification was detected. Further checks have stopped; handle it manually."),
    "bili.search": ("仅代表本次网页搜索结果，不保证一定能注册", "This only reflects the current web search. Registration is not guaranteed."),
    "bili.related": ("相关（非同名）", "Related (different name)"),
    "bili.available": ("没有同名或相近账号；列出的是 B 站模糊搜索返回的相关账号，仅供参考", "No exact or similar name was found. Listed accounts are loosely related Bilibili search results, for reference only."),
    "search.empty": ("搜索页面没有结果，不保证一定能注册", "The search page returned no results. Registration is not guaranteed."),
    "bili.unknown": ("未识别到用户卡片或空结果提示，页面结构可能已变化", "No user cards or empty-result indicator were recognized. The page structure may have changed."),
    "bili.error": ("B 站页面加载失败，请检查网络或稍后重试", "The Bilibili page failed to load. Check your connection or try again later."),
    "search.blocked": ("出现验证页，已停止{platform}后续查询。{note}", "Verification was detected on {platform}. Further checks have stopped. {note}"),
    "search.login": ("请先点击“去登录”，在浏览器中自行登录。{note}", "Click 'Sign in' and log in yourself in the browser first. {note}"),
    "search.auth": ("尚未确认登录状态，请先登录后重试。{note}", "Sign-in could not be confirmed. Sign in and try again. {note}"),
    "search.result": ("仅代表本次搜索结果，不保证一定能注册", "This only reflects the current search. Registration is not guaranteed."),
    "search.unknown": ("未识别到用户列表或空结果提示，需用 probe 核对选择器。{note}", "No user list or empty-result indicator was recognized. Use probe to check the selectors. {note}"),
    "search.error": ("{platform}页面加载失败，请检查网络或稍后重试。{note}", "The {platform} page failed to load. Check your connection or try again later. {note}"),
    "xhs.note": ("小红书昵称唯一性资料待实测，这里只表示有没有人在用，以平台提示为准", "Nickname uniqueness on Xiaohongshu (RED) needs testing. This only checks current usage; follow the platform's instructions."),
    "channels.note": ("视频号名字不能重名。在微信 → 发现 → 视频号 → 右上角搜索，或创建、改名时直接试填，提示‘已被占用’就是有人用了", "WeChat Channels names must be unique. In WeChat, open Discover > Channels > Search, or try the name when creating or renaming a channel. 'Already taken' means someone is using it."),
    "browser.launch": ("专用浏览器启动失败，请确认本机 Edge 或 Chrome 可用；工具不会下载浏览器", "The dedicated browser could not start. Check that Edge or Chrome is installed; this tool does not download browsers."),
    "browser.tab": ("专用浏览器暂时无法打开标签页，请稍后重试", "The dedicated browser could not open a tab. Try again later."),
    "browser.login": ("登录页打开失败，请检查网络后重试。", "The login page could not open. Check your connection and try again. "),
    "snapshot.incomplete": ("页面快照未能完整保存", "The page snapshot could not be saved completely."),
    "snapshot.saved": ("已保存页面快照：{html}、{png}。把这两个文件发给开发者可以帮助修正识别；文件可能包含你的账号信息，只在本机，不会上传。", "Page snapshots saved: {html}, {png}. Sharing these two files with the developer can help fix detection. Files may contain account information; they stay on this computer and are not uploaded."),
    "snapshot.failed": ("页面快照未能完整保存到 {path}，页面可能已关闭。若已生成部分文件，文件可能包含账号信息，只在本机，不会上传。", "Could not save complete snapshots to {path}; the page may have closed. Any partial files may contain account information. They stay on this computer and are not uploaded."),
    "copy.variants": ("帮我给{name}想 5 个同音字或中英混写的变体，每行一个，格式：名字 | handle", "Suggest 5 homophone or mixed-language variants of {name}, one per line, in this format: Name | handle"),
    "demo.note": ("演示模式：固定假结果，不联网、不写历史", "Demo: fixed sample results, no external requests and no saved history."),
    "demo.disabled": ("演示模式不打开浏览器，也不抓取真实页面", "Demo mode does not open a browser or capture real pages."),
    "demo.url": ("演示模式已就绪，请自行打开 http://127.0.0.1:8765", "Demo is ready. Open http://127.0.0.1:8765 yourself."),
    "demo.extra": ("演示账号", "Demo account"),
    "port": ("端口 8765 已被占用，请先关闭旧的 ID 雷达或占用该端口的程序", "Port 8765 is in use. Close the previous ID Radar instance or the application using that port."),
    "qr.unsupported": ("该平台暂不支持扫码登录", "QR sign-in is not supported for this platform."),
    "qr.scan": ("用 {platform} App 扫一扫", "Scan with the {platform} app."),
    "qr.expired": ("二维码过期了，请换一张", "The QR code expired. Request a new one."),
    "qr.fallback": ("取不到二维码，已打开窗口，请在窗口中自行登录", "No QR code could be captured. The browser window is open; sign in there yourself."),
    "qr.success": ("已登录 ✓", "Signed in ✓"),
    "qr.unknown": ("未确认登录，请先在窗口完成登录再继续", "Sign-in is unconfirmed. Finish signing in in the window before continuing."),
    "qr.missing": ("登录卡片已失效，请重新扫码登录", "This sign-in session is no longer active. Start QR sign-in again."),
    "qr.busy": ("该平台正在等待手动验证，请先完成验证再登录", "This platform is waiting for manual verification. Complete it before signing in."),
    "verification.missing": ("暂停状态已更新，请使用最新的验证提示卡", "The pause has changed. Use the latest verification card."),
    "verification.unavailable": ("暂时无法打开验证窗口，请重试", "Could not open the verification window. Try again."),
}
TEXT = {lang: {key: values[index] for key, values in PAIRS.items()} for index, lang in enumerate(("zh", "en"))}


def _add_rule_text():
    data = Path(__file__).parent / "data"
    original = json.loads((data / "platform_rules.json").read_text(encoding="utf-8"))
    english = json.loads((data / "rules.en.json").read_text(encoding="utf-8"))
    for id, rule in original.items():
        translated = english[id]
        pairs = [("rename", rule["rename_limit"], translated["rename_limit"])]
        assert len(rule["notes"]) == len(translated["notes"])
        assert len(rule["sources"]) == len(translated["sources"])
        pairs += [(f"note.{i}", source, translated["notes"][i]) for i, source in enumerate(rule["notes"])]
        pairs += [(f"source.{i}.{field}", source[field], translated["sources"][i][field]) for i, source in enumerate(rule["sources"]) for field in ("title", "date")]
        for suffix, zh, en in pairs:
            key = f"rules.{id}.{suffix}"
            TEXT["zh"][key], TEXT["en"][key] = zh, en


_add_rule_text()


def language(value=None):
    return value if value in ("zh", "en") else LANG.get()


def t(key, *, lang=None, **values):
    template = TEXT[language(lang)][key]
    values = {field: translate_text(value, lang) if field in ("platform", "category", "note") else value for field, value in values.items()}
    return template.format(**values) if values else template


def platform_label(id, fallback="", *, lang=None):
    key = "platform." + id
    return t(key, lang=lang) if key in TEXT["zh"] else fallback or id


@lru_cache(maxsize=None)
def template_pattern(template):
    escaped = re.escape(template)
    for field in set(re.findall(r"\{(\w+)\}", template)):
        escaped = escaped.replace(re.escape("{" + field + "}"), "(?P<" + field + ">.*?)")
    return re.compile(escaped, re.DOTALL)


def translate_text(value, lang=None, depth=0):
    """还原已保存的双语文案；未知文本（如用户起的网站名）保持原样。"""
    target = language(lang)
    if not isinstance(value, str) or not value or depth > 8:
        return value
    for source in ("zh", "en"):
        for key, template in TEXT[source].items():
            if value == template:
                return TEXT[target][key]
    # 说明可能由“加载失败 + 快照路径”等两段组成，先按完整静态前缀拆开。
    for source in ("zh", "en"):
        for key, template in sorted(TEXT[source].items(), key=lambda item: -len(item[1])):
            if "{" in template or len(template) < 8 or not value.startswith(template):
                continue
            rest = value[len(template):]
            if rest and rest[0] in " 。；":
                separator = ". " if target == "en" and rest[0] == "。" else "；" if target == "zh" and rest[0] == "；" else " "
                return TEXT[target][key] + separator + translate_text(rest.lstrip(" 。；"), target, depth + 1)
    for source in ("zh", "en"):
        for key, template in TEXT[source].items():
            if "{" not in template:
                continue
            match = template_pattern(template).fullmatch(value)
            if match:
                values = {key: translate_text(part, target, depth + 1) for key, part in match.groupdict().items()}
                return TEXT[target][key].format(**values)
    if "；" in value:
        return ("；" if target == "zh" else "; ").join(translate_text(part, target, depth + 1) for part in value.split("；"))
    # 兼容历史里拼接的说明；只在说明字段调用，不处理账号名与昵称。
    other = "en" if target == "zh" else "zh"
    for key, source in sorted(TEXT[other].items(), key=lambda item: -len(item[1])):
        if "{" not in source and len(source) > 3:
            value = value.replace(source, TEXT[target][key])
    return value


def localize_data(value, lang=None):
    """为格子说明保留双语副本，切换语言不必重新查询平台。"""
    lang = language(lang)
    if isinstance(value, list):
        return [localize_data(item, lang) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: localize_data(item, lang) for key, item in value.items() if not key.endswith("_i18n")}
    for key in ("note", "message", "detail", "copy_prompt", "handle_prompt", "extra"):
        if isinstance(value.get(key), str):
            previous = value.get(key + "_i18n", {})
            result[key + "_i18n"] = {code: previous.get(code, translate_text(value[key], code)) for code in ("zh", "en")}
            result[key] = result[key + "_i18n"][lang]
    for key in ("label", "rename_limit", "title", "date"):
        if isinstance(value.get(key), str) and not (key == "label" and (value.get("custom") or str(value.get("id", "")).startswith("custom_"))):
            result[key] = translate_text(value[key], lang)
    for key in ("notes", "reasons"):
        if isinstance(value.get(key), list):
            result[key] = [translate_text(item, lang) for item in value[key]]
    return result
