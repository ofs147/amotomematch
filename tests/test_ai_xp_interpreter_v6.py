from pathlib import Path

import pandas as pd

from utils.ai_xp_interpreter_v6 import MockAIProvider, fallback_as_ai_response, generate_result
from utils.tag_recommender_v6 import build_fallback_result, load_tag_characters

ROOT = Path(__file__).resolve().parents[1]


def _fixture():
    characters = load_tag_characters(ROOT / "data" / "core_xp_tags_v6.csv", ROOT / "data" / "core_xp_tags_v6_2_review.csv")
    # This deterministic fixture has a full valid recommendation shape. Tests
    # for best-effort exploration coverage live in test_tag_recommender_v6.py.
    selected = [item for item in characters if item.character_id in {"C001", "C004", "C005", "C077", "C087"}]
    controlled = set(pd.read_csv(ROOT / "data" / "core_xp_tag_dictionary_v6.csv")["canonical_tag"])
    return characters, selected, controlled


def test_valid_structured_mock_uses_one_provider_call_path():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    result = generate_result(selected, characters, controlled, MockAIProvider(fallback_as_ai_response(fallback)))
    assert result.mode == "MOCK"
    assert len(result.high_matches) == 5
    assert len(result.explorations) == 3


def test_invalid_ai_id_falls_back_without_crashing():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    response["high_match_character_ids"][0] = "NOT_IN_POOL"
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "FALLBACK_AFTER_AI_ERROR"
    assert "ai_validation_error" in result.debug


def test_duplicate_ai_titles_are_repaired_without_inventing_branches():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    for signal in response["heart_signals"]:
        signal["title"] = "同一个标题 ！！"
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "MOCK"
    assert len({signal.title for signal in result.heart_signals}) == len(result.heart_signals)
    assert [signal.tags for signal in result.heart_signals] == [signal.tags for signal in fallback.heart_signals]


def test_best_effort_fallback_round_trips_through_mock_ai_validation():
    characters, _, controlled = _fixture()
    selected = [
        item for item in characters
        if item.character_id in {"C001", "C004", "C005", "C044", "C077", "C087"}
    ]
    fallback = build_fallback_result(selected, characters)
    assert len(fallback.explorations) == 2
    result = generate_result(
        selected,
        characters,
        controlled,
        MockAIProvider(fallback_as_ai_response(fallback)),
    )
    assert result.mode == "MOCK"
    assert len(result.high_matches) == 5
    assert len(result.explorations) == 2


def test_normal_context_rejects_too_few_exploration_picks():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    response["exploration"].pop()
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "FALLBACK_AFTER_AI_ERROR"
    assert "exactly 3 exploration picks" in result.debug["ai_validation_error"]


def test_normal_context_rejects_too_many_exploration_picks():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    response["exploration"].append(dict(response["exploration"][0]))
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "FALLBACK_AFTER_AI_ERROR"
    assert "exactly 3 exploration picks" in result.debug["ai_validation_error"]


def test_invalid_exploration_id_is_rejected():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    response["exploration"][0]["character_id"] = "NOT_IN_POOL"
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "FALLBACK_AFTER_AI_ERROR"
    assert "recommendation IDs are invalid" in result.debug["ai_validation_error"]


def test_duplicate_id_across_recommendation_groups_is_rejected():
    characters, selected, controlled = _fixture()
    fallback = build_fallback_result(selected, characters)
    response = fallback_as_ai_response(fallback)
    response["exploration"][0]["character_id"] = response["high_match_character_ids"][0]
    result = generate_result(selected, characters, controlled, MockAIProvider(response))
    assert result.mode == "FALLBACK_AFTER_AI_ERROR"
    assert "recommendation IDs are invalid" in result.debug["ai_validation_error"]
