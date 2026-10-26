import asyncio
import json
from pathlib import Path
import re
from string import Formatter

import httpx

from idradar.i18n import LANG, TEXT, localize_data, t
from idradar.prompts import NAMING_PROMPT_EN, HANDLE_PROMPT_EN
from idradar.rules import check_name
from idradar.variants import generate_variants
from test_server import make_app


def test_english_prompt_exact_design():
    design = (Path(__file__).resolve().parents[1] / "docs" / "PROMPTS.md").read_text(encoding="utf-8")
    section = design[design.index("### 英文提示词原文（照抄，不要改写）") :]
    expected = section.split("```", 2)[1].strip("\n")
    assert NAMING_PROMPT_EN == expected


def test_catalog_language_keys_and_placeholders_match():
    assert set(TEXT["zh"]) == set(TEXT["en"])
    formatter = Formatter()
    for key in TEXT["zh"]:
        assert TEXT["zh"][key] and TEXT["en"][key]
        fields = lambda lang: {field for _, field, _, _ in formatter.parse(TEXT[lang][key]) if field is not None}
        assert fields("zh") == fields("en"), key


def test_frontend_has_no_scattered_chinese():
    from scripts.check_i18n import violations
    assert violations() == []


def test_rule_messages_and_translation_are_english():
    token = LANG.set("en")
    try:
        assert check_name("x", "") == {"verdict": "bad", "reasons": ["No English handle provided."]}
        assert "exceeds" in check_name("x", "a" * 16)["reasons"][0]
        assert all(not re.search(r"[\u3400-\u9fff]", reason) for reason in check_name("github", "中_文")["reasons"])
        result = localize_data({"note": t("connect", platform="X", domain="x.com")})
        assert "proxy" in result["note"] and "连不上" in result["note_i18n"]["zh"]
    finally:
        LANG.reset(token)


def test_combined_snapshot_notes_remain_bilingual():
    message = t("qr.fallback", lang="zh") + " " + t("snapshot.saved", lang="zh", html="D:/probe/a.html", png="D:/probe/a.png")
    result = localize_data({"note": message}, "en")
    assert "Page snapshots saved" in result["note"]
    assert not re.search(r"[\u3400-\u9fff]", result["note"])
    assert "已保存页面快照" in result["note_i18n"]["zh"]


async def test_english_api_prompt_rules_errors_and_sse(tmp_path, fake_browser):
    from idradar.platforms.github import GitHubChecker
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(404))) as fake_http:
        app = make_app(tmp_path, fake_browser, checkers={"github": GitHubChecker(fake_http)})
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
            assert (await client.get("/api/prompt?lang=en")).json()["prompt"] == NAMING_PROMPT_EN
            rules = (await client.get("/api/rules?lang=en")).json()["platforms"]
            assert rules["bilibili"]["label"] == "Bilibili"
            assert rules["xiaohongshu"]["label"] == "Xiaohongshu (RED)"
            assert not re.search(r"[\u3400-\u9fff]", json.dumps(rules, ensure_ascii=False))
            result = (await client.post("/api/rules/check?lang=en", json={"candidates": [{"name": "Name", "handle": ""}], "platforms": ["github"]})).json()
            assert result["validations"][0]["github"]["reasons"] == ["No English handle provided."]
            assert result["handle_prompt"] == HANDLE_PROMPT_EN + "\nName"
            for body in ({"candidates": [], "platforms": ["github"]}, {"candidates": [{"name": "Name"}], "platforms": ["nope"]}):
                result = (await client.post("/api/check?lang=en", json=body)).json()
                assert not re.search(r"[\u3400-\u9fff]", result["detail"])
            response = await client.post("/api/check?lang=en", json={"candidates": [{"name": "Name", "handle": "toolman"}], "platforms": ["github"]})
            cell = next(json.loads(chunk.split("data: ")[1]) for chunk in response.text.split("\n\n") if chunk.startswith("event: result"))
            assert "Registration" in cell["result"]["note"]
            assert not re.search(r"[\u3400-\u9fff]", cell["result"]["note"])
            assert "未找到" in cell["result"]["note_i18n"]["zh"]


async def test_request_language_is_isolated(tmp_path, fake_browser):
    app = make_app(tmp_path, fake_browser)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="http://testserver") as client:
        zh, en = await asyncio.gather(client.get("/api/platforms?lang=zh"), client.get("/api/platforms?lang=en"))
        assert zh.json()["platforms"][0]["label"] == "B站"
        assert en.json()["platforms"][0]["label"] == "Bilibili"
    assert LANG.get() == "zh"


def test_english_word_variants_have_specified_suffixes_and_prefixes():
    original = {"bilibili": {"status": "taken"}}
    pair = {"name": "Alex", "handle": "alexwu"}
    variants = []
    for offset in range(0, 16, 4):
        variants += generate_variants(pair, original, ["bilibili"], {}, offset=offset)
    words = [item["name"] for item in variants if item["group"] == "words"]
    assert words == ["Alexdev", "Alexhq", "Alexlab", "Alexbuilds", "Alexofficial", "realAlex", "itsAlex", "theAlex"]
    assert all(item["handle"] == "alexwu" for item in variants)
    accented = generate_variants({"name": "Zoë", "handle": "zoewu"}, original, ["bilibili"], {})
    assert accented[0]["name"] == "Zoëdev"
