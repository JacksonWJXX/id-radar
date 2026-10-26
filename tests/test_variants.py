from idradar.rules import check_candidate
from idradar.variants import COPY_PROMPT, conflict_platforms, generate_variants, recommendations, target_for

PAIR = {"name": "工具人", "handle": "toolman"}
DETAILS = {"bilibili": {"label": "B站"}, "github": {"label": "GitHub"}, "x": {"label": "X"}}


def results(**statuses):
    return {id: {"status": status} for id, status in statuses.items()}


def test_name_conflict_only_changes_name_in_alternating_order():
    original = results(bilibili="taken", github="available")
    pairs = generate_variants(PAIR, original, list(original), DETAILS)
    assert [item["group"] for item in pairs] == ["words", "numbers", "words", "numbers"]
    assert [item["name"] for item in pairs] == ["工具人本人", "工具人001", "工具人Lab", "工具人002"]
    assert all(item["handle"] == "toolman" for item in pairs)


def test_handle_conflict_preserves_name_and_uses_pair_not_pinyin():
    original = results(bilibili="available", github="taken", x="similar")
    pairs = generate_variants(PAIR, original, list(original), DETAILS)
    assert all(item["name"] == PAIR["name"] for item in pairs)
    assert [item["handle"] for item in pairs] == ["toolmandev", "toolman001", "toolmanhq", "toolman002"]
    both = generate_variants(PAIR, results(bilibili="taken", x="taken"), ["bilibili", "x"], DETAILS)
    assert both[0]["name"] == "工具人本人" and both[0]["handle"] == "toolmandev"


def test_skip_bad_rules_before_cap_and_offset_and_duplicates():
    pair = {"name": "工具人", "handle": "a" * 13}
    original = results(x="taken")
    pairs = generate_variants(pair, original, ["x"], DETAILS)
    assert pairs[0]["handle"] == "a" * 13 + "hq"  # dev 和 001 都超长，跳过。
    assert all(check_candidate(p["name"], p["handle"], ["x"])["x"]["verdict"] != "bad" for p in pairs)
    original = results(bilibili="taken", github="taken")
    first = generate_variants(PAIR, original, list(original), DETAILS)
    second = generate_variants(PAIR, original, list(original), DETAILS, offset=4)
    assert not {(p["name"], p["handle"]) for p in first} & {(p["name"], p["handle"]) for p in second}
    without = generate_variants(PAIR, original, list(original), DETAILS, existing=[first[0]])
    assert without[0]["group"] == "numbers" and len(without) == 4


def test_custom_profile_conflict_changes_handle():
    details = {"custom_1": {"custom": True, "kind": "profile"}}
    assert target_for("custom_1", details) == "handle"
    assert generate_variants(PAIR, results(custom_1="taken"), ["custom_1"], details)[0]["handle"] == "toolmandev"


def test_only_taken_similar_conflict_and_copy_prompt():
    assert conflict_platforms(results(a="manual", b="login", c="error", d="invalid", e="blocked")) == []
    assert generate_variants(PAIR, results(bilibili="manual"), ["bilibili"], DETAILS) == []
    assert COPY_PROMPT.replace("【原名】", PAIR["name"]) == "帮我给工具人想 5 个同音字或中英混写的变体，每行一个，格式：名字 | handle"


def test_partial_first_available_per_platform_and_first_unified():
    original = results(bilibili="taken", github="similar", x="available")
    pairs = generate_variants(PAIR, original, list(original), DETAILS)
    trials = [
        {"candidate": pairs[0], "results": results(bilibili="available", github="taken", x="available")},
        {"candidate": pairs[1], "results": results(bilibili="taken", github="available", x="available")},
        {"candidate": pairs[2], "results": results(bilibili="available", github="available", x="available")},
        {"candidate": pairs[3], "results": results(bilibili="available", github="available", x="available")},
    ]
    choices = recommendations(PAIR, original, trials, list(original), DETAILS)
    assert choices["partial"]["ready"] and choices["unified"]["ready"]
    assert choices["partial"]["final"] == {"bilibili": pairs[0]["name"], "github": pairs[1]["handle"], "x": PAIR["handle"]}
    assert choices["unified"]["candidate"] == pairs[2]


def test_missing_recommendations_are_disabled_and_manual_prevents_unified():
    original = results(bilibili="taken", github="taken", x="manual")
    trials = [{"candidate": PAIR, "results": results(bilibili="available", github="error", x="manual")}]
    choices = recommendations(PAIR, original, trials, list(original), DETAILS)
    assert not choices["partial"]["ready"] and choices["partial"]["missing"] == ["github"]
    assert not choices["unified"]["ready"] and choices["unified"]["final"] == {}
