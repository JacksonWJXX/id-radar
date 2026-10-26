from pathlib import Path
import re

import pytest

from idradar.parse_names import HANDLE_PROMPT, NAMING_PROMPT, build_handle_prompt, make_handle, merge_candidates, parse_names


@pytest.mark.parametrize("text,name,handle", [
    ("```\n名字 | handle\n```", "名字", "handle"),
    ("```text\n百号工具人 | baihao_tool\n```", "百号工具人", "baihao_tool"),
    ("造轮子百回｜zaolunzi", "造轮子百回", "zaolunzi"),
    ("1. 百号工具人 | baihao", "百号工具人", "baihao"),
    ("1、百号工具人 | baihao", "百号工具人", "baihao"),
    ("(1) 百号工具人 | baihao", "百号工具人", "baihao"),
    ("（1）百号工具人 | baihao", "百号工具人", "baihao"),
    ("- 百号工具人 —— 开源创作者的自嘲", "百号工具人", "baihaogongjuren"),
    ("* 百号工具人 -- 动手做工具", "百号工具人", "baihaogongjuren"),
    ("• 百号工具人—动手做工具", "百号工具人", "baihaogongjuren"),
    ("· 百号工具人：动手做工具", "百号工具人", "baihaogongjuren"),
    ("百号工具人:动手做工具", "百号工具人", "baihaogongjuren"),
    ('“百号工具人” | @ baihao_tool ', "百号工具人", "baihao_tool"),
    ("'百号工具人'", "百号工具人", "baihaogongjuren"),
    ('"百号工具人"', "百号工具人", "baihaogongjuren"),
    ("「百号工具人」", "百号工具人", "baihaogongjuren"),
    ("《百号工具人》", "百号工具人", "baihaogongjuren"),
    ("工具人 |", "工具人", "gongjuren"),
])
def test_formats(text, name, handle):
    result = parse_names(text)
    assert len(result) == 1
    assert result[0]["name"] == name
    assert result[0]["handle"] == handle


def test_whole_reply_discards_explanation_paragraphs():
    text = """这是为你准备的一批名字：
以下是推荐的名字：
```text
1. “百号工具人” | @baihao
2. 造轮子百回 | zaolunzi
```
百号工具人：工具创作者的自嘲。
造轮子百回 —— 一百次练习，一百次成长。
这些名字都兼顾了好记和个人特点。
这里有一些补充建议：
推荐理由：这些名字都和你有关。
注意：先检查各个平台的格式。
Here are the names:
你可以选择一个喜欢的名字。
你最喜欢哪一个？
"""
    assert [item["name"] for item in parse_names(text)] == ["百号工具人", "造轮子百回"]


def test_dedup_normalizes_case_width_and_whitespace():
    result = parse_names("ＡＩ包工头 | first\nai 包工头 | second\nAI包工头 | third")
    assert len(result) == 1
    assert result[0]["name"] == "ＡＩ包工头"
    assert result[0]["handle"] == "first"


def test_maximum_thirty_without_truncating_name():
    result = parse_names("\n".join(f"名字{i}" for i in range(40)))
    assert len(result) == 30
    assert result[-1]["name"] == "名字29"
    assert parse_names("甲" * 31) == []
    assert parse_names("甲" * 30)[0]["name"] == "甲" * 30
    assert parse_names("甲")[0]["name"] == "甲"


@pytest.mark.parametrize("text", ["", " \n\t ", "```text\n```", "这是一个解释句。", "这是一个问题？", "Is this a name?", "This is a sentence.", "---"])
def test_empty_sentences_and_formatting(text):
    assert parse_names(text) == []


def test_make_handle_short_without_hyphens_and_long_empty():
    assert make_handle("百号工具人") == "baihaogongjuren"
    assert make_handle("hello-world") == "helloworld"
    assert make_handle("a" * 15) == "a" * 15
    assert make_handle("a" * 16) == ""
    assert make_handle("很长的名字" * 20) == ""


def test_explicit_handle_is_not_silently_truncated():
    handle = "a" * 100
    assert parse_names("工具人 | @ " + handle)[0]["handle"] == handle


def test_prompt_matches_design_word_for_word():
    design = (Path(__file__).resolve().parents[1] / "docs" / "PROMPTS.md").read_text(encoding="utf-8")
    section = design.split("### 提示词原文", 1)[1]
    original = re.search(r"```\n(.*?)\n```", section, re.S).group(1)
    assert NAMING_PROMPT == original


def test_handle_prompt_matches_design_and_appends_names():
    design = (Path(__file__).resolve().parents[1] / "docs" / "PROMPTS.md").read_text(encoding="utf-8")
    section = design.split("### 二、英文 handle", 1)[1]
    original = re.search(r"```\n(.*?)\n```", section, re.S).group(1)
    assert HANDLE_PROMPT == original
    assert build_handle_prompt(["名字甲", "名字乙"]) == original + "\n名字甲\n名字乙"
    assert build_handle_prompt([]) == ""


def test_merge_updates_existing_handle_without_losing_candidate():
    existing = [{"name": "AI包工头", "handle": "oldname"}, {"name": "名字乙", "handle": "keepme"}]
    parsed = [{"name": "ａｉ 包工头", "handle": "albertwu"}, {"name": "名字乙", "handle": ""}, {"name": "名字丙", "handle": "carolwu"}]
    result = merge_candidates(parsed, existing)
    assert result["count"] == 3 and result["added"] == 1 and result["updated"] == 1
    assert result["updates"] == [{"index": 0, "handle": "albertwu"}]
    assert result["candidates"] == [parsed[2]]
    assert existing[0]["handle"] == "oldname"


def test_real_reply_with_pipe_lines_keeps_only_pipe_lines():
    text = (Path(__file__).parent / "fixtures" / "ai_reply_with_chatter.txt").read_text(encoding="utf-8")
    assert [(item["name"], item["handle"]) for item in parse_names(text)] == [
        ("林小舟Leo", "leolinzhou"),
        ("Leo在造", "leobuilds"),
        ("小舟造工具", "zhoubuilds"),
        ("鑫手开源", "xinopensource"),
        ("林小舟", "linxiaozhou"),
        ("Leo林", "leolin_dev"),
        ("林老板造轮子", "linbosswheel"),
    ]
