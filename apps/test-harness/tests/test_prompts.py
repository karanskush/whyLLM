"""Tests for the prompt definitions."""

from test_harness.prompts import PROMPT_MAP, PROMPTS, TestPrompt


def test_all_prompts_have_unique_names():
    names = [p.name for p in PROMPTS]
    assert len(names) == len(set(names))


def test_prompt_map_matches_list():
    assert len(PROMPT_MAP) == len(PROMPTS)
    for p in PROMPTS:
        assert PROMPT_MAP[p.name] is p


def test_all_prompts_have_required_fields():
    for p in PROMPTS:
        assert p.name
        assert p.system
        assert p.user
        assert p.model
        assert p.max_tokens > 0
        assert 0.0 <= p.temperature <= 2.0


def test_prompt_is_frozen():
    p = PROMPTS[0]
    try:
        p.name = "changed"
        assert False, "Should not allow mutation"
    except AttributeError:
        pass


def test_known_prompts_exist():
    expected = {"summarise", "translate", "classify", "code_gen", "creative"}
    assert set(PROMPT_MAP.keys()) == expected
