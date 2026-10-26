import pytest

from idradar.rules import PLATFORM_RULES, check_candidate, check_name


@pytest.mark.parametrize("name", ["中文", "a_b", "-abc", "abc-", "a--b", "a" * 40, "a b", "ＡＢＣ", "", "a😀b"])
def test_github_rejects_invalid(name):
    assert check_name("github", name)["verdict"] == "bad"


@pytest.mark.parametrize("name", ["a", "A0", "a-b", "a" * 39])
def test_github_boundaries(name):
    assert check_name("github", name) == {"verdict": "ok", "reasons": []}


@pytest.mark.parametrize("name", ["a-bc", "a" * 16, "中文名字", "abc def", "abc·def", "😀😀😀😀"])
def test_x_rejects_confirmed_violations(name):
    assert check_name("x", name)["verdict"] == "bad"


def test_x_minimum_conflict_not_a_hard_block():
    assert PLATFORM_RULES["x"]["min_len"] == 4
    assert check_name("x", "abc")["verdict"] == "unknown"
    assert any("少于 4" in reason for reason in check_name("x", "abc")["reasons"])
    assert check_name("x", "abcd")["verdict"] != "bad"
    assert check_name("x", "_ab__c_")["verdict"] != "bad"
    assert check_name("x", "a" * 15)["verdict"] != "bad"
    assert check_name("x", "maxwell")["verdict"] == "ok"


def test_x_length_conflict_only_at_four():
    assert check_name("x", "abcd")["reasons"] == ["长度资料有矛盾，以平台提示为准"]
    assert check_name("x", "abcde")["reasons"] == []
    assert check_name("x", "a" * 16)["reasons"] == ["长度 16，超过 15 字符"]
    assert check_name("x", "admin" + "a" * 11)["reasons"] == ["长度 16，超过 15 字符"]


def test_weixin_cjk_count_and_rename_conflict():
    assert check_name("weixin_channels", "汉" * 15)["verdict"] == "ok"
    result = check_name("weixin_channels", "汉" * 16)
    assert result["verdict"] == "bad"
    assert any("32" in reason and "30" in reason for reason in result["reasons"])
    assert check_name("weixin_channels", "ab")["verdict"] == "bad"
    assert check_name("weixin_channels", "abc")["verdict"] == "ok"
    assert check_name("weixin_channels", "工具")["verdict"] == "ok"


@pytest.mark.parametrize("name", ["百号_工具", "百号-工具", "百号·工具", "百号!工具", "工具😀"])
def test_weixin_special_characters(name):
    assert check_name("weixin_channels", name)["verdict"] == "bad"


def test_weixin_unknown_space_is_not_blocked():
    assert check_name("weixin_channels", "a b")["verdict"] == "unknown"


@pytest.mark.parametrize("platform", ["bilibili", "douyin", "xiaohongshu"])
@pytest.mark.parametrize("name", ["工具人", "a" * 80, "a😀 ·_"])
def test_unconfirmed_nickname_rules_only_warn(platform, name):
    assert check_name(platform, name)["verdict"] == "unknown"


def test_handles_are_checked_instead_of_display_names():
    result = check_candidate("中文名字", "valid-user", ["github", "x", "weixin_channels"])
    assert result["github"]["verdict"] == "ok"
    assert result["x"]["verdict"] == "bad"
    assert result["weixin_channels"]["verdict"] == "ok"


def test_data_schema_and_provenance():
    assert set(PLATFORM_RULES) == {"bilibili", "douyin", "xiaohongshu", "weixin_channels", "github", "x"}
    categories = {"cjk", "latin", "digit", "underscore", "hyphen", "space", "middle_dot", "other_punct", "emoji"}
    for rule in PLATFORM_RULES.values():
        assert set(rule["allowed"]) == categories
        assert set(rule["allowed"].values()) <= {"yes", "no", "unknown"}
        assert rule["sources"]
        assert all({"url", "date", "level"} <= source.keys() for source in rule["sources"])
        assert rule["confidence"] in {"official", "third_party", "user_tested", "conflict"}
        assert isinstance(rule["extra_rules"], list)
    assert PLATFORM_RULES["weixin_channels"]["unique"] == {"value": "yes", "confidence": "user_tested"}
    assert PLATFORM_RULES["x"]["target"] == "handle"
