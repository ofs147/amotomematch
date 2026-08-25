"""Provider-neutral, fact-constrained AI interpretation for AOMatch v6.4."""
from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from typing import Callable, Mapping, Protocol, Sequence

from utils.tag_recommender_v6 import (
    CharacterTags,
    HeartSignal,
    RecommendationCard,
    RetrievedCandidate,
    TagResult,
    build_fallback_result,
    ensure_unique_signal_titles,
    normalize_signal_title,
    retrieve_candidates,
)


class AIProvider(Protocol):
    mode: str

    def generate(self, payload: Mapping[str, object]) -> Mapping[str, object]: ...


class CallableAIProvider:
    """Adapter for a real provider client supplied by deployment code."""

    mode = "REAL_AI"

    def __init__(self, generate_once: Callable[[Mapping[str, object]], Mapping[str, object]]):
        self._generate_once = generate_once

    def generate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self._generate_once(payload)


class MockAIProvider:
    """Deterministic structured mock; never calls a network service."""

    mode = "MOCK"

    def __init__(self, response: Mapping[str, object]):
        self.response = response

    def generate(self, payload: Mapping[str, object]) -> Mapping[str, object]:
        return self.response


FACT_SAFETY_INSTRUCTION = (
    "只允许解释给定受控标签与用户偏好关系。不得添加路线事件、背景故事、标签之外的人格事实、"
    "隐藏身份或剧透；不得使用模型对作品的外部记忆。只能从给定候选池选择ID。"
)


def stable_request_hash(selected: Sequence[CharacterTags], pool: Sequence[RetrievedCandidate]) -> str:
    value = {
        "selected": [(item.character_id, item.tags) for item in selected],
        "pool": [(item.character.character_id, item.character.tags, item.score) for item in pool],
    }
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def build_safe_payload(
    selected: Sequence[CharacterTags], signals: Sequence[HeartSignal], pool: Sequence[RetrievedCandidate],
    expected_high_match_count: int, expected_exploration_count: int,
) -> dict[str, object]:
    return {
        "instruction": FACT_SAFETY_INSTRUCTION,
        "output_contract": {
            "xp_personality": "3–5句中文",
            "heart_signals": "保留输入signal_id，只改title/explanation",
            "high_match_character_ids": f"exactly {expected_high_match_count} retrieved IDs",
            "exploration": f"exactly {expected_exploration_count} entries with character_id/familiar_tags/new_tags",
            "recommendation_reasons": "object keyed by recommended character_id",
        },
        "selected": [
            {"character_id": item.character_id, "character_name": item.character_name, "game": item.game_title, "tags": list(item.tags)}
            for item in selected
        ],
        "heart_signals": [asdict(signal) for signal in signals],
        "retrieved_candidates": [
            {
                "character_id": item.character.character_id,
                "character_name": item.character.character_name,
                "game": item.character.game_title,
                "tags": list(item.character.tags),
                "retrieval_signals": {
                    "matched_tags": item.matched_tags,
                    "heart_signal_ids": item.branch_hits,
                    "rarity_score": item.rarity_score,
                    "combination_score": item.combination_score,
                    "pre_ai_score": item.score,
                },
            }
            for item in pool
        ],
    }


def fallback_as_ai_response(result: TagResult) -> dict[str, object]:
    return {
        "xp_personality": result.xp_personality,
        "heart_signals": [
            {
                "signal_id": item.signal_id,
                "title": item.title,
                "tags": item.tags,
                "supporting_character_ids": item.supporting_character_ids,
                "explanation": item.explanation,
            }
            for item in result.heart_signals
        ],
        "high_match_character_ids": [item.character_id for item in result.high_matches],
        "exploration": [
            {"character_id": item.character_id, "familiar_tags": item.familiar_tags, "new_tags": item.new_tags}
            for item in result.explorations
        ],
        "recommendation_reasons": {
            item.character_id: item.reason for item in [*result.high_matches, *result.explorations]
        },
    }


def _text(value: object, maximum: int = 240) -> str:
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > maximum:
        raise ValueError("Invalid AI text")
    return value.strip()


def validate_ai_response(
    response: Mapping[str, object], selected: Sequence[CharacterTags], signals: Sequence[HeartSignal],
    pool: Sequence[RetrievedCandidate], controlled_tags: set[str], fallback: TagResult,
    expected_high_match_count: int, expected_exploration_count: int,
) -> TagResult:
    pool_by_id = {item.character.character_id: item for item in pool}
    selected_ids = {item.character_id for item in selected}
    selected_tags = {tag for item in selected for tag in item.tags}
    fallback_signals = {item.signal_id: item for item in signals}

    raw_signals = response.get("heart_signals")
    if not isinstance(raw_signals, list) or len(raw_signals) != len(signals):
        raise ValueError("AI heart signal count mismatch")
    parsed_signals = []
    for raw in raw_signals:
        if not isinstance(raw, Mapping):
            raise ValueError("Invalid heart signal")
        signal_id = raw.get("signal_id")
        if signal_id not in fallback_signals:
            raise ValueError("Unknown heart signal")
        original = fallback_signals[str(signal_id)]
        tags = raw.get("tags")
        supporters = raw.get("supporting_character_ids")
        if tags != original.tags or supporters != original.supporting_character_ids:
            raise ValueError("AI changed evidence-backed heart signal facts")
        if any(tag not in controlled_tags for tag in tags):
            raise ValueError("Uncontrolled heart signal tag")
        if any(item not in selected_ids for item in supporters):
            raise ValueError("Heart signal supporter was not selected")
        parsed_signals.append(HeartSignal(original.signal_id, _text(raw.get("title"), 40), list(tags), list(supporters), original.support_details, _text(raw.get("explanation"), 180)))
    seen_titles: set[str] = set()
    for signal in parsed_signals:
        normalized_title = normalize_signal_title(signal.title)
        if normalized_title in seen_titles:
            fallback_title = fallback_signals[signal.signal_id].title
            if normalize_signal_title(fallback_title) not in seen_titles:
                signal.title = fallback_title
                normalized_title = normalize_signal_title(fallback_title)
        seen_titles.add(normalized_title)
    parsed_signals = ensure_unique_signal_titles(parsed_signals)

    high_ids = response.get("high_match_character_ids")
    exploration = response.get("exploration")
    reasons = response.get("recommendation_reasons")
    if not isinstance(high_ids, list) or len(high_ids) != expected_high_match_count:
        raise ValueError(f"AI must return exactly {expected_high_match_count} high matches")
    if not isinstance(exploration, list) or len(exploration) != expected_exploration_count:
        raise ValueError(f"AI must return exactly {expected_exploration_count} exploration picks")
    if not isinstance(reasons, Mapping):
        raise ValueError("Missing recommendation reasons")
    exploration_ids = [item.get("character_id") for item in exploration if isinstance(item, Mapping)]
    all_ids = [*high_ids, *exploration_ids]
    if len(all_ids) != len(set(all_ids)) or any(item not in pool_by_id or item in selected_ids for item in all_ids):
        raise ValueError("AI recommendation IDs are invalid")
    high_signal_hits = []
    for character_id in high_ids:
        candidate_tags = set(pool_by_id[str(character_id)].character.tags)
        hits = {signal.signal_id for signal in parsed_signals if candidate_tags & set(signal.tags)}
        if not hits:
            raise ValueError("High match does not align with a Heart Signal")
        high_signal_hits.append(hits)
    available_signal_ids = {
        signal.signal_id
        for signal in parsed_signals
        if any(set(item.character.tags) & set(signal.tags) for item in pool)
    }
    if len(available_signal_ids) >= 2 and len(set().union(*high_signal_hits)) < 2:
        raise ValueError("AI high matches collapse onto one branch despite viable diversity")

    def signal_for(candidate: RetrievedCandidate) -> HeartSignal | None:
        return max(parsed_signals, key=lambda item: len(set(item.tags) & set(candidate.character.tags)), default=None)

    high_cards = []
    for character_id in high_ids:
        candidate = pool_by_id[str(character_id)]
        signal = signal_for(candidate)
        high_cards.append(RecommendationCard(candidate.character.character_id, candidate.character.character_name, candidate.character.game_title, list(candidate.character.tags), signal.signal_id if signal else "", signal.title if signal else "相邻心动支线", _text(reasons.get(character_id), 180)))

    exploration_cards = []
    for raw in exploration:
        character_id = raw["character_id"]
        candidate = pool_by_id[character_id]
        familiar = raw.get("familiar_tags")
        new = raw.get("new_tags")
        if not isinstance(familiar, list) or not isinstance(new, list) or not 1 <= len(familiar) <= 2 or not 1 <= len(new) <= 2:
            raise ValueError("Invalid exploration tag counts")
        if any(tag not in candidate.character.tags or tag not in selected_tags for tag in familiar):
            raise ValueError("Invalid familiar exploration tag")
        if any(tag not in candidate.character.tags or tag in selected_tags for tag in new):
            raise ValueError("Invalid new exploration tag")
        signal = signal_for(candidate)
        exploration_cards.append(RecommendationCard(candidate.character.character_id, candidate.character.character_name, candidate.character.game_title, list(candidate.character.tags), signal.signal_id if signal else "", signal.title if signal else "相邻心动支线", _text(reasons.get(character_id), 180), familiar, new))

    return TagResult(_text(response.get("xp_personality"), 360), parsed_signals, high_cards, exploration_cards, "REAL_AI", fallback.debug)


def generate_result(
    selected: Sequence[CharacterTags], eligible: Sequence[CharacterTags], controlled_tags: set[str],
    provider: AIProvider | None = None, retrieval_limit: int = 20,
) -> TagResult:
    fallback = build_fallback_result(selected, eligible, retrieval_limit)
    if provider is None:
        return fallback
    pool = retrieve_candidates(selected, eligible, fallback.heart_signals, retrieval_limit)
    expected_high_match_count = len(fallback.high_matches)
    expected_exploration_count = len(fallback.explorations)
    payload = build_safe_payload(
        selected, fallback.heart_signals, pool,
        expected_high_match_count, expected_exploration_count,
    )
    try:
        result = validate_ai_response(
            provider.generate(payload), selected, fallback.heart_signals, pool,
            controlled_tags, fallback,
            expected_high_match_count, expected_exploration_count,
        )
        result.mode = provider.mode
        result.debug["request_hash"] = stable_request_hash(selected, pool)
        return result
    except Exception as error:  # Provider outage or malformed response must not break preview.
        fallback.mode = "FALLBACK_AFTER_AI_ERROR"
        fallback.debug["ai_validation_error"] = str(error)
        return fallback
