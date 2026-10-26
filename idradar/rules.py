"""只拦截明确违反的格式；冲突和未知项保留为提示。"""

import json
from pathlib import Path
import unicodedata

from .i18n import t

RULES_PATH = Path(__file__).parent / "data" / "platform_rules.json"
PLATFORM_RULES = json.loads(RULES_PATH.read_text(encoding="utf-8"))
CATEGORY_LABELS = {
    "cjk": t('char.cjk'), "latin": t('char.latin'), "digit": t('char.digit'), "underscore": t('char.underscore'),
    "hyphen": t('char.hyphen'), "space": t('char.space'), "middle_dot": t('char.middle_dot'), "other_punct": t('char.other_punct'), "emoji": t('char.emoji'),
}


def is_cjk(char: str) -> bool:
    return char == "〇" or unicodedata.name(char, "").startswith(("CJK UNIFIED IDEOGRAPH", "CJK COMPATIBILITY IDEOGRAPH"))


def character_category(char: str) -> str:
    if is_cjk(char):
        return "cjk"
    if char.isascii() and char.isalpha():
        return "latin"
    if char in "0123456789":
        return "digit"
    if char in "_-·":
        return {"_": "underscore", "-": "hyphen", "·": "middle_dot"}[char]
    if char.isspace():
        return "space"
    if 0x1F000 <= ord(char) <= 0x1FAFF or 0x2600 <= ord(char) <= 0x27BF or char in "\ufe0f\u200d\u20e3":
        return "emoji"
    return "other_punct"


def check_name(platform: str, name: str) -> dict:
    rule = PLATFORM_RULES.get(platform)
    if rule is None:
        return {"verdict": "unknown", "reasons": [t('rule.unknown')]}
    if rule["target"] == "handle" and not name.strip():
        return {"verdict": "bad", "reasons": [t('rule.handle')]}
    bad, uncertain = [], []
    confidence = rule.get("field_confidence", {})
    # 按字段保留可信度，改名次数的矛盾不会削弱明确的格式规则。
    def issue(reason, field):
        level = confidence.get(field, confidence.get("length") if field in ("min_len", "max_len") else rule["confidence"])
        (uncertain if level == "conflict" else bad).append(reason)

    categories = {character_category(char) for char in name}
    length = sum(rule["cjk_width"] if is_cjk(char) and rule["cjk_width"] is not None else 1 for char in name)
    if platform == "x" and length > rule["max_len"]:
        return {"verdict": "bad", "reasons": [t('rule.max', length=length, limit=rule['max_len'])]}
    if rule["min_len"] is None:
        uncertain.append(t('rule.min_unknown'))
    elif length < rule["min_len"]:
        issue(t('rule.min', length=length, limit=rule['min_len']), "min_len")
    if rule["max_len"] is None:
        uncertain.append(t('rule.max_unknown'))
    elif length > rule["max_len"]:
        issue(t('rule.max', length=length, limit=rule['max_len']), "max_len")
    if confidence.get("length") == "conflict" and (platform != "x" or length == 4):
        uncertain.append(t('rule.conflict'))
    if "cjk" in categories and rule["cjk_width"] is None:
        uncertain.append(t('rule.cjk_unknown'))
    for category in CATEGORY_LABELS:
        if category not in categories:
            continue
        allowed = rule["allowed"][category]
        if allowed == "no":
            issue(t('rule.forbidden', category=CATEGORY_LABELS[category]), "allowed")
        elif allowed == "unknown":
            uncertain.append(t('rule.category_unknown', category=CATEGORY_LABELS[category]))
    for check in rule["extra_rules"]:
        if check == "hyphen_not_at_edges" and (name.startswith("-") or name.endswith("-")):
            issue(t('rule.hyphen_edges'), "extra_rules")
        elif check == "no_consecutive_hyphens" and "--" in name:
            issue(t('rule.hyphen_double'), "extra_rules")
        elif check == "x_reserved_terms_uncertain" and any(word in name.casefold() for word in ("admin", "twitter")):
            # 只查 admin / twitter：单个字母 x 太常见，查它会让大量正常 handle 都带提示
            uncertain.append(t('rule.x_reserved'))
    return {"verdict": "bad" if bad else "unknown" if uncertain else "ok", "reasons": list(dict.fromkeys(bad + uncertain))}


def check_candidate(name: str, handle: str, platforms: list[str]) -> dict:
    return {platform: check_name(platform, handle if PLATFORM_RULES.get(platform, {}).get("target") == "handle" else name) for platform in platforms}
