"""AOMatch v2.1 Coverage-aware Hybrid Matching 并行原型。

原始相似度完全复用 recommender_v2；本模块只新增证据覆盖率、
向 50% 中性值收缩的实验分数，以及并行排序。
"""

from typing import Dict, List, Mapping, Optional, Sequence

import pandas as pd

from utils.data_utils import normalize_numeric_score, parse_tags
from utils.recommender_v2 import (
    calculate_match_breakdown,
    generate_recommendation_reason,
)
from utils.schema import (
    LAYERS,
    LAYER_WEIGHTS,
    MATCH_COMPONENT_WEIGHTS,
    NUMERIC_FEATURES_BY_LAYER,
    TAG_FIELDS_BY_LAYER,
)


def shrink_similarity(raw_score: Optional[float], coverage: float) -> float:
    """将低覆盖的相似度向 0.5 中性值收缩，不把缺失视为不匹配。"""
    if not 0 <= coverage <= 1:
        raise ValueError("coverage 必须位于 0～1")
    if raw_score is None:
        return 0.5
    return 0.5 + coverage * (raw_score - 0.5)


def calculate_candidate_layer_coverage(
    layer: str, layer_profile: Mapping[str, object], character: pd.Series
) -> Dict[str, object]:
    """计算用户 Profile 与候选角色在一层中实际可比较的证据覆盖。"""
    numeric_feature_coverage = {}
    profile_numeric_coverage = layer_profile.get("coverage", {}).get(
        "numeric_feature_coverage", {}
    )
    for feature in NUMERIC_FEATURES_BY_LAYER[layer]:
        user_value = layer_profile["numeric"].get(feature)
        candidate_value = character.get(feature)
        candidate_available = normalize_numeric_score(candidate_value) is not None
        user_available = user_value is not None
        numeric_feature_coverage[feature] = (
            float(profile_numeric_coverage.get(feature, 1.0))
            if candidate_available and user_available
            else 0.0
        )
    numeric_coverage = sum(numeric_feature_coverage.values()) / len(
        numeric_feature_coverage
    )

    tag_field_coverage = {}
    for field in TAG_FIELDS_BY_LAYER[layer]:
        field_profile = layer_profile["tags"].get(field, {})
        has_user_evidence = bool(field_profile.get("frequencies"))
        candidate_available = bool(parse_tags(character.get(field)))
        tag_field_coverage[field] = (
            float(field_profile.get("field_coverage", 0.0))
            if has_user_evidence and candidate_available
            else 0.0
        )
    tag_coverage = sum(tag_field_coverage.values()) / len(tag_field_coverage)

    weights = MATCH_COMPONENT_WEIGHTS[layer]
    layer_coverage = (
        numeric_coverage * weights["numeric"]
        + tag_coverage * weights["tag"]
    )
    return {
        "numeric_coverage": round(numeric_coverage, 4),
        "numeric_feature_coverage": numeric_feature_coverage,
        "tag_coverage": round(tag_coverage, 4),
        "tag_field_coverage": tag_field_coverage,
        "layer_coverage": round(layer_coverage, 4),
    }


def calculate_coverage_aware_breakdown(
    profile: Mapping[str, object], character: pd.Series
) -> Dict[str, object]:
    """同时返回旧 Raw Breakdown 和 Coverage-adjusted Breakdown。"""
    raw = calculate_match_breakdown(profile, character)
    coverage = {
        layer: calculate_candidate_layer_coverage(
            layer, profile[layer], character
        )
        for layer in LAYERS
    }

    adjusted_layer_scores_raw = {}
    for layer in LAYERS:
        raw_percent = raw["layer_scores_raw"][layer]
        raw_similarity = None if raw_percent is None else raw_percent / 100
        adjusted_layer_scores_raw[layer] = shrink_similarity(
            raw_similarity, coverage[layer]["layer_coverage"]
        )

    adjusted_final_similarity = sum(
        adjusted_layer_scores_raw[layer] * LAYER_WEIGHTS[layer]
        for layer in LAYERS
    )
    overall_coverage = sum(
        coverage[layer]["layer_coverage"] * LAYER_WEIGHTS[layer]
        for layer in LAYERS
    )

    evidence_notes = []
    for layer in LAYERS:
        layer_coverage = coverage[layer]["layer_coverage"]
        if layer_coverage < 0.5:
            evidence_notes.append(
                f"{layer} 证据覆盖较低（{round(layer_coverage * 100)}%）"
            )
        elif layer_coverage < 0.75:
            evidence_notes.append(
                f"{layer} 证据覆盖中等（{round(layer_coverage * 100)}%）"
            )

    return {
        "raw": raw,
        "coverage": coverage,
        "overall_data_coverage": round(overall_coverage, 4),
        "coverage_adjusted_final_score_raw": adjusted_final_similarity * 100,
        "coverage_adjusted_match_score": round(adjusted_final_similarity * 100),
        "coverage_adjusted_layer_scores_raw": {
            layer: adjusted_layer_scores_raw[layer] * 100 for layer in LAYERS
        },
        "coverage_adjusted_layer_scores": {
            layer: round(adjusted_layer_scores_raw[layer] * 100)
            for layer in LAYERS
        },
        "evidence_coverage_notes": evidence_notes,
    }


def generate_coverage_aware_reason(
    character_name: str, breakdown: Mapping[str, object]
) -> str:
    """只有高分且高覆盖时使用“高度匹配”。"""
    raw = breakdown["raw"]
    adjusted_scores = breakdown["coverage_adjusted_layer_scores"]
    coverage = breakdown["coverage"]
    best_layer = max(LAYERS, key=lambda layer: adjusted_scores[layer])
    best_adjusted = adjusted_scores[best_layer]
    best_coverage = coverage[best_layer]["layer_coverage"]

    if best_adjusted >= 75 and best_coverage >= 0.75:
        opening = (
            f"{character_name}在 {best_layer} 层与你高度匹配"
            f"（调整后 {best_adjusted}%，证据覆盖 "
            f"{round(best_coverage * 100)}%）"
        )
    elif best_coverage < 0.6:
        opening = (
            f"现有 {best_layer} 数据与{character_name}的 XP 较接近，"
            f"但该层证据覆盖仅 {round(best_coverage * 100)}%，"
            "因此可信度有限"
        )
    else:
        opening = (
            f"{character_name}与你目前最接近的是 {best_layer} 层"
            f"（调整后 {best_adjusted}%）"
        )

    raw_reason = generate_recommendation_reason(character_name, raw)
    notes = breakdown["evidence_coverage_notes"]
    note_text = f"覆盖提示：{'；'.join(notes)}。" if notes else ""
    return f"{opening}。{raw_reason}{note_text}"


def recommend_characters_v2_1(
    characters: pd.DataFrame,
    profile: Mapping[str, object],
    selected_character_ids: Sequence[str],
    top_n: int = 5,
    sort_by: str = "coverage_adjusted",
) -> pd.DataFrame:
    """返回 Raw 与 Adjusted 并存的结果，默认按实验分排序。"""
    if sort_by not in {"coverage_adjusted", "raw"}:
        raise ValueError("sort_by 必须是 coverage_adjusted 或 raw")

    candidates = characters[
        ~characters["character_id"].isin(selected_character_ids)
    ]
    results: List[Dict[str, object]] = []
    for _, character in candidates.iterrows():
        breakdown = calculate_coverage_aware_breakdown(profile, character)
        raw = breakdown["raw"]
        result = {
            "character_id": character["character_id"],
            "character_name": character["character_name"],
            "game": character["game"],
            "raw_final_score_raw": raw["final_score_raw"],
            "raw_match_score": raw["final_match_score"],
            "coverage_adjusted_final_score_raw": breakdown[
                "coverage_adjusted_final_score_raw"
            ],
            "coverage_adjusted_match_score": breakdown[
                "coverage_adjusted_match_score"
            ],
            "overall_data_coverage": breakdown["overall_data_coverage"],
            "numeric_highlights": raw["numeric_highlights"],
            "tag_highlights": raw["tag_highlights"],
            "evidence_coverage_notes": breakdown["evidence_coverage_notes"],
            "recommendation_reason": generate_coverage_aware_reason(
                character["character_name"], breakdown
            ),
            "score_breakdown": breakdown,
        }
        for layer in LAYERS:
            result[f"raw_{layer}"] = raw["layer_scores"][layer]
            result[f"adjusted_{layer}"] = breakdown[
                "coverage_adjusted_layer_scores"
            ][layer]
            result[f"{layer}_coverage"] = breakdown["coverage"][layer][
                "layer_coverage"
            ]
        results.append(result)

    if not results:
        return pd.DataFrame()
    sort_column = (
        "coverage_adjusted_final_score_raw"
        if sort_by == "coverage_adjusted"
        else "raw_final_score_raw"
    )
    return (
        pd.DataFrame(results)
        .sort_values([sort_column, "character_id"], ascending=[False, True])
        .head(top_n)
        .reset_index(drop=True)
    )
