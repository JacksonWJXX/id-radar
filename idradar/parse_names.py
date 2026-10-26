"""本地识别粘贴的昵称列表，不请求外部服务。"""

import re

from pypinyin import lazy_pinyin

from .platforms.base import normalize
from .prompts import NAMING_PROMPT, HANDLE_PROMPT, handle_prompt


LEADING_MARKER = re.compile(r"^\s*(?:[（(]\d+[）)]|\d+[.．、)]|[-*•·])\s*")
EXPLANATION_SEPARATOR = re.compile(r"—+|--+|：|:")
SENTENCE_MARKS = re.compile(r"[。．.？?！!，,；;]")
NARRATIVE_START = re.compile(
    r"^(?:(?:以下|下面|以上)(?:是|为|的|这些|推荐)|这些(?:名字|昵称|建议)|这批(?:名字|昵称)|"
    r"这是(?:我|为|给|一些|一批)|这里(?:是|有|给)|我(?:为你|给你|推荐了)|"
    r"建议你|你可以|希望你|如果你|每个名字|所有名字|根据你的|收到你的|"
    r"(?i:here (?:are|is)|these (?:names|suggestions)|below (?:are|is)|i (?:recommend|suggest)|you can))"
)
EXPLANATION_LABELS = {"说明", "解释", "含义", "推荐理由", "名字列表", "昵称列表", "格式", "提示", "注意", "备注", "建议", "补充", "总结", "温馨提示"}
PIPE = re.compile(r"[|｜]")
QUOTES = "“”\"'「」《》`"


def make_handle(name: str) -> str:
    value = "".join(lazy_pinyin(name)).lower()
    value = re.sub(r"[^a-z0-9]+", "", value)
    return value if len(value) <= 15 else ""


def build_handle_prompt(names: list[str], lang=None) -> str:
    return handle_prompt(lang) + "\n" + "\n".join(names) if names else ""


def merge_candidates(candidates: list[dict], existing: list[dict]) -> dict:
    indices = {normalize(candidate["name"]): index for index, candidate in enumerate(existing)}
    additions, updates = [], []
    for candidate in candidates:
        index = indices.get(normalize(candidate["name"]))
        if index is None:
            additions.append(candidate)
        elif candidate["handle"] and candidate["handle"] != existing[index].get("handle", ""):
            updates.append({"index": index, "handle": candidate["handle"]})
    return {"candidates": additions, "updates": updates, "count": len(candidates), "added": len(additions), "updated": len(updates)}


def parse_names(text: str) -> list[dict]:
    candidates, seen = [], set()
    lines = [raw.strip().replace("**", "") for raw in text.splitlines()]
    pipe_mode = any(PIPE.search(line) for line in lines)
    for line in lines:
        if not line or line.startswith(("```", "#")):
            continue
        while True:
            stripped = LEADING_MARKER.sub("", line, count=1)
            if stripped == line:
                break
            line = stripped
        if not line or NARRATIVE_START.match(line) or re.fullmatch(r"[-=*_~:|｜\s]+", line):
            continue
        if pipe_mode and not PIPE.search(line) and (EXPLANATION_SEPARATOR.search(line) or re.search(r"\s", line) or any(q in line for q in QUOTES)):
            continue
        parts = PIPE.split(line, maxsplit=1)
        if len(parts) == 2:
            name, handle = parts
            handle = "".join(handle.strip().strip(QUOTES).replace("@", "").split())
        else:
            name = EXPLANATION_SEPARATOR.split(line, maxsplit=1)[0]
            handle = ""
        name = name.strip().strip(QUOTES).strip()
        if len(parts) == 1 and EXPLANATION_SEPARATOR.search(line) and name in EXPLANATION_LABELS:
            continue
        if not 1 <= len(name) <= 30 or SENTENCE_MARKS.search(name):
            continue
        key = normalize(name)
        if not key or key in seen:
            continue
        seen.add(key)
        candidates.append({"name": name, "handle": handle if handle else make_handle(name), "meaning": "", "tags": []})
        if len(candidates) == 30:
            break
    return candidates
