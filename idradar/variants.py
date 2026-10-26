"""成对生成名字和 handle，只推荐实际查过可用的替换。"""

from .platforms.base import normalize
from .rules import PLATFORM_RULES, check_candidate, is_cjk
from .i18n import t

COPY_PROMPT = t("copy.variants", lang="zh", name="\u3010\u539f\u540d\u3011")
CONFLICTS = {"taken", "similar"}
NAME_WORDS = ("本人", "Lab", "工作室", "日记", "君", "小屋", "笔记", "来了")
HANDLE_WORDS = ("dev", "hq", "lab", "builds", "real", "its", "the", "go")
ENGLISH_WORDS = (("dev", False), ("hq", False), ("lab", False), ("builds", False), ("official", False), ("real", True), ("its", True), ("the", True))


def target_for(platform, details):
    item = details.get(platform, {})
    return "handle" if (item.get("custom") and item.get("kind") == "profile") else PLATFORM_RULES.get(platform, {}).get("target", "name")


def used_name(candidate, platform, details):
    return candidate[target_for(platform, details)]


def conflict_platforms(results):
    return [id for id, result in results.items() if result["status"] in CONFLICTS]


def generate_variants(candidate, original, platforms, details, *, offset=0, existing=()):
    """先过滤规则与重复，再按加词、加数字交替取最多四对；offset 按合规对计数。"""
    conflicts = conflict_platforms(original)
    change_name = any(target_for(id, details) == "name" for id in conflicts)
    change_handle = any(target_for(id, details) == "handle" for id in conflicts)
    seen = {(normalize(item["name"]), normalize(item["handle"])) for item in [candidate, *existing]}
    accepted = []
    if not conflicts:
        return []
    english_name = not any(is_cjk(char) for char in candidate["name"])
    for index in range(100):
        cycle = str(index // len(NAME_WORDS) + 1) if index >= len(NAME_WORDS) else ""
        word, prefix = ENGLISH_WORDS[index % len(ENGLISH_WORDS)]
        word_name = (word + candidate["name"] if prefix else candidate["name"] + word) + cycle if english_name else candidate["name"] + NAME_WORDS[index % len(NAME_WORDS)] + cycle
        for group, name_suffix, handle_suffix in (
            ("words", NAME_WORDS[index % len(NAME_WORDS)] + cycle, HANDLE_WORDS[index % len(HANDLE_WORDS)] + cycle),
            ("numbers", f"{index + 1:03}", f"{index + 1:03}"),
        ):
            item = {"name": (word_name if group == "words" else candidate["name"] + name_suffix) if change_name else candidate["name"],
                    "handle": candidate["handle"] + handle_suffix if change_handle else candidate["handle"]}
            key = (normalize(item["name"]), normalize(item["handle"]))
            checks = check_candidate(item["name"], item["handle"], platforms)
            if key in seen or len(item["name"]) > 60 or any(value["verdict"] == "bad" for value in checks.values()):
                continue
            seen.add(key)
            accepted.append({**item, "group": group, "validations": checks})
            if len(accepted) >= offset + 4:
                return accepted[offset:]
    return accepted[offset:offset + 4]


def recommendations(candidate, original, trials, platforms, details):
    """局部方案逐平台取第一个可用项，统一方案要求每个已选平台都可用。"""
    conflicts = conflict_platforms(original)
    final = {id: used_name(candidate, id, details) for id in platforms}
    missing = []
    for id in conflicts:
        first = next((trial for trial in trials if trial["results"].get(id, {}).get("status") == "available"), None)
        if first:
            final[id] = used_name(first["candidate"], id, details)
        else:
            missing.append(id)
    unified = next((trial for trial in trials if all(trial["results"].get(id, {}).get("status") == "available" for id in platforms)), None)
    return {
        "partial": {"ready": bool(conflicts) and not missing, "final": final, "missing": missing, "changed": conflicts},
        "unified": {"ready": unified is not None, "final": {id: used_name(unified["candidate"], id, details) for id in platforms} if unified else {},
                    "candidate": unified["candidate"] if unified else None},
    }
