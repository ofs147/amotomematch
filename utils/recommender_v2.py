"""AOMatch v2 四层 Hybrid Matching 原型。

本模块尚未接入当前 MVP v1.1。所有得分均来自 Character Database v2 的
Numeric Features 与各自字段内的 Tag Similarity，不使用随机数。
"""

from typing import Dict, List, Mapping, Optional, Sequence

import pandas as pd

from utils.data_utils import normalize_numeric_score, parse_tags
from utils.schema import (
    LAYERS,
    LAYER_WEIGHTS,
    MATCH_COMPONENT_WEIGHTS,
    NUMERIC_DISPLAY_NAMES,
    NUMERIC_FEATURES_BY_LAYER,
    TAG_FIELDS_BY_LAYER,
)


def numeric_feature_similarity(
    user_score: object, character_score: object
) -> Optional[float]:
    """计算单一数值维度相似度；任一侧缺失时返回 None。"""
    user_normalized = normalize_numeric_score(user_score)
    character_normalized = normalize_numeric_score(character_score)
    if user_normalized is None or character_normalized is None:
        return None
    return 1 - abs(user_normalized - character_normalized)


def weighted_tag_similarity(
    user_frequencies: Mapping[str, Mapping[str, float]], candidate_value: object
) -> Optional[float]:
    """计算同一 Tag Field 内的 Weighted Jaccard similarity。

    用户标签权重是 Profile 中的出现频率，候选角色标签是 0/1。用户或候选
    整个字段缺失时返回 None，表示 unavailable，而不是不匹配。
    """
    candidate_tags = parse_tags(candidate_value)
    if not user_frequencies or not candidate_tags:
        return None

    all_tags = set(user_frequencies) | candidate_tags
    numerator = 0.0
    denominator = 0.0
    for tag in all_tags:
        user_value = float(user_frequencies.get(tag, {}).get("frequency", 0.0))
        candidate_binary = 1.0 if tag in candidate_tags else 0.0
        numerator += min(user_value, candidate_binary)
        denominator += max(user_value, candidate_binary)
    return numerator / denominator if denominator else None


def _available_weighted_average(
    values: Mapping[str, Optional[float]], weights: Mapping[str, float]
) -> Optional[float]:
    """只对可用部分加权，并把剩余权重重新归一化。"""
    available = {key: value for key, value in values.items() if value is not None}
    if not available:
        return None
    if len(available) == 1:
        return next(iter(available.values()))
    available_weight = sum(weights[key] for key in available)
    return sum(available[key] * weights[key] for key in available) / available_weight


def calculate_layer_breakdown(
    layer: str, layer_profile: Mapping[str, object], character: pd.Series
) -> Dict[str, object]:
    """计算一层的 Numeric、Tag 和重新归一化后的 Layer Score。"""
    numeric_details = []
    for feature in NUMERIC_FEATURES_BY_LAYER[layer]:
        user_score = layer_profile["numeric"].get(feature)
        character_score = character.get(feature)
        similarity = numeric_feature_similarity(user_score, character_score)
        if similarity is not None:
            numeric_details.append(
                {
                    "feature": feature,
                    "display_name": NUMERIC_DISPLAY_NAMES[feature],
                    "layer": layer,
                    "user_score": float(user_score),
                    "character_score": float(character_score),
                    "similarity": similarity,
                }
            )

    numeric_score = (
        sum(item["similarity"] for item in numeric_details) / len(numeric_details)
        if numeric_details
        else None
    )

    tag_field_details = []
    for field in TAG_FIELDS_BY_LAYER[layer]:
        field_profile = layer_profile["tags"].get(field, {})
        frequencies = field_profile.get("frequencies", {})
        candidate_value = character.get(field)
        similarity = weighted_tag_similarity(frequencies, candidate_value)
        if similarity is None:
            continue

        candidate_tags = parse_tags(candidate_value)
        matched_tags = sorted(
            set(frequencies) & candidate_tags,
            key=lambda tag: (-frequencies[tag]["frequency"], tag),
        )
        tag_field_details.append(
            {
                "field": field,
                "layer": layer,
                "similarity": similarity,
                "matched_tags": matched_tags,
                "matched_frequencies": {
                    tag: frequencies[tag]["frequency"] for tag in matched_tags
                },
            }
        )

    tag_score = (
        sum(item["similarity"] for item in tag_field_details) / len(tag_field_details)
        if tag_field_details
        else None
    )
    layer_score = _available_weighted_average(
        {"numeric": numeric_score, "tag": tag_score},
        MATCH_COMPONENT_WEIGHTS[layer],
    )

    return {
        "score": layer_score,
        "numeric_score": numeric_score,
        "tag_score": tag_score,
        "numeric_details": numeric_details,
        "tag_field_details": tag_field_details,
    }


def calculate_match_breakdown(
    profile: Mapping[str, object], character: pd.Series
) -> Dict[str, object]:
    """计算候选角色的四层 Breakdown、总分和真实匹配亮点。"""
    layers = {
        layer: calculate_layer_breakdown(layer, profile[layer], character)
        for layer in LAYERS
    }
    layer_scores = {layer: layers[layer]["score"] for layer in LAYERS}
    final_similarity = _available_weighted_average(layer_scores, LAYER_WEIGHTS)
    final_similarity = final_similarity if final_similarity is not None else 0.0

    numeric_matches = [
        detail
        for layer in LAYERS
        for detail in layers[layer]["numeric_details"]
    ]
    numeric_matches.sort(
        key=lambda item: (
            -item["similarity"],
            -abs(item["user_score"] - 3),
            item["feature"],
        )
    )

    tag_matches = []
    for layer in LAYERS:
        for field_detail in layers[layer]["tag_field_details"]:
            for tag in field_detail["matched_tags"]:
                tag_matches.append(
                    {
                        "tag": tag,
                        "field": field_detail["field"],
                        "layer": layer,
                        "user_frequency": field_detail["matched_frequencies"][tag],
                    }
                )
    tag_matches.sort(key=lambda item: (-item["user_frequency"], item["tag"]))

    available_layers = [layer for layer in LAYERS if layer_scores[layer] is not None]
    highest_layer = (
        max(available_layers, key=lambda layer: layer_scores[layer])
        if available_layers
        else None
    )

    return {
        "final_score_raw": final_similarity * 100,
        "final_match_score": round(final_similarity * 100),
        "layer_scores_raw": {
            layer: None if layer_scores[layer] is None else layer_scores[layer] * 100
            for layer in LAYERS
        },
        "layer_scores": {
            layer: None if layer_scores[layer] is None else round(layer_scores[layer] * 100)
            for layer in LAYERS
        },
        "highest_matching_layer": highest_layer,
        "numeric_highlights": numeric_matches[:3],
        "tag_highlights": tag_matches[:3],
        "layers": layers,
    }


def generate_recommendation_reason(
    character_name: str, breakdown: Mapping[str, object]
) -> str:
    """只根据 Breakdown 中的真实亮点生成规则推荐理由。"""
    highest_layer = breakdown["highest_matching_layer"]
    numeric = breakdown["numeric_highlights"]
    tags = breakdown["tag_highlights"]

    parts = []
    if highest_layer:
        layer_score = breakdown["layer_scores"][highest_layer]
        parts.append(f"{character_name}与你最匹配的是 {highest_layer} 层（{layer_score}%）")

    if numeric:
        numeric_names = [item["display_name"] for item in numeric]
        high_preferences = [
            item["display_name"] for item in numeric if item["user_score"] >= 4
        ]
        if high_preferences:
            parts.append(
                f"你对{'、'.join(high_preferences)}表现出较高偏好，"
                f"该角色在{'、'.join(numeric_names)}上与你非常接近"
            )
        else:
            parts.append(f"双方在{'、'.join(numeric_names)}上非常接近")

    if tags:
        tag_names = [f"「{item['tag']}」" for item in tags]
        parts.append(f"你高频出现的{'、'.join(tag_names)}属性也与该角色重合")

    if not parts:
        return "当前有效数据不足，暂时无法生成详细推荐理由。"
    return "。".join(parts) + "。"


def recommend_characters_v2(
    characters: pd.DataFrame,
    profile: Mapping[str, object],
    selected_character_ids: Sequence[str],
    top_n: int = 5,
) -> pd.DataFrame:
    """排除已选角色，返回按未取整总分降序排列的 v2 推荐结果。"""
    candidates = characters[
        ~characters["character_id"].isin(selected_character_ids)
    ].copy()

    results: List[Dict[str, object]] = []
    for _, character in candidates.iterrows():
        breakdown = calculate_match_breakdown(profile, character)
        results.append(
            {
                "character_id": character["character_id"],
                "character_name": character["character_name"],
                "game": character["game"],
                "final_score_raw": breakdown["final_score_raw"],
                "final_match_score": breakdown["final_match_score"],
                **{
                    f"{layer}_score": breakdown["layer_scores"][layer]
                    for layer in LAYERS
                },
                "highest_matching_layer": breakdown["highest_matching_layer"],
                "numeric_highlights": breakdown["numeric_highlights"],
                "tag_highlights": breakdown["tag_highlights"],
                "recommendation_reason": generate_recommendation_reason(
                    character["character_name"], breakdown
                ),
                "score_breakdown": breakdown,
            }
        )

    if not results:
        return pd.DataFrame()
    return (
        pd.DataFrame(results)
        .sort_values(
            ["final_score_raw", "character_id"], ascending=[False, True]
        )
        .head(top_n)
        .reset_index(drop=True)
    )
