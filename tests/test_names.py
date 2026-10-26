import pytest

from idradar.platforms.base import compare_names, distance_one, match_results, normalize


@pytest.mark.parametrize("left,right,expected", [
    ("AI包工头", "Ai包工头", "taken"),
    ("ＡＩ包工头", "ai包工头", "taken"),
    (" AI\u3000包\t工\n头 ", "ai包工头", "taken"),
    ("工具人", "工具人三百九十九号", "similar"),
    ("百号工具人", "工具人三百九十九号", None),
    ("百号工具人", "百号工具仁", "similar"),
    ("百号工具人", "百号工具", "similar"),
    ("百号工人", "百号工具人", "similar"),
    ("工具", "工人", None),
    ("工具", "工具人", None),
    ("ab", "abc", None),
    ("abc", "axc", "similar"),
    ("造轮子百回", "月亮研究所", None),
    ("", "", None),
])
def test_compare(left, right, expected):
    assert compare_names(left, right) == expected


def test_normalize_casefold():
    assert normalize(" ＳＴＲＡＳＳＥ \n") == normalize("Straße")


@pytest.mark.parametrize("left,right,expected", [("abc", "abc", False), ("abc", "abcd", True), ("abc", "abdc", True), ("abc", "adc", True), ("abc", "axy", False), ("abc", "a", False)])
def test_distance(left, right, expected):
    assert distance_one(left, right) is expected


def test_exact_first_and_max_five():
    accounts = [{"name": f"百号工具人{i}", "url": str(i), "extra": ""} for i in range(8)]
    accounts.append({"name": "百号工具人", "url": "exact", "extra": ""})
    result = match_results("百号工具人", accounts, "https://example.test")
    assert result.status == "taken"
    assert len(result.matches) == 5
    assert result.matches[0]["url"] == "exact"
