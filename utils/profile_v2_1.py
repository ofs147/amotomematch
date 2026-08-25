"""AOMatch v2.1 Coverage-aware XP Profile 并行原型。

保留 v2 Profile 的 ``numeric`` / ``tags`` 字段，只附加 coverage 信息。
当前 app.py 和 v2 正式原型不读取本模块。
"""

from typing import Dict, Mapping

import pandas as pd

from utils.data_utils import parse_tags
from utils.profile_v2 import build_xp_profile_v2
from utils.schema import (
    LAYERS,
    LAYER_WEIGHTS,
    MATCH_COMPONENT_WEIGHTS,
    NUMERIC_DISPLAY_NAMES,
    NUMERIC_FEATURES_BY_LAYER,
    TAG_FIELDS_BY_LAYER,
)


def build_xp_profile_v2_1(selected_characters: pd.DataFrame) -> Dict[str, object]:
    """生成兼容 v2 的 Profile，并附加数值、Tag 和分层覆盖率。"""
    profile = build_xp_profile_v2(selected_characters)
    selected_total = len(selected_characters)

    layer_coverages: Dict[str, float] = {}
    for layer in LAYERS:
        numeric_feature_coverage = {}
        for feature in NUMERIC_FEATURES_BY_LAYER[layer]:
            valid_count = int(
                pd.to_numeric(selected_characters[feature], errors="coerce")
                .notna()
                .sum()
            )
            numeric_feature_coverage[feature] = round(
                valid_count / selected_total, 4
            )

        numeric_coverage = round(
            sum(numeric_feature_coverage.values())
            / len(numeric_feature_coverage),
            4,
        )

        tag_field_coverages = {}
        for field in TAG_FIELDS_BY_LAYER[layer]:
            field_profile = profile[layer]["tags"][field]
            valid_field_count = field_profile["valid_character_count"]
            field_coverage = round(valid_field_count / selected_total, 4)
            tag_field_coverages[field] = field_coverage

            # frequency 保留 v2 语义（条件频率），新增 global_support
            # 作为面向用户的“全部已选角色支持度”。
            for detail in field_profile["frequencies"].values():
                support_count = detail["count"]
                detail["support_count"] = support_count
                detail["conditional_frequency"] = detail["frequency"]
                detail["global_support"] = round(
                    support_count / selected_total, 4
                )

            field_profile.update(
                {
                    "selected_total": selected_total,
                    "field_coverage": field_coverage,
                }
            )
            ordered_tags = list(field_profile["frequencies"])
            field_profile["common_tags"] = [
                tag
                for tag in ordered_tags
                if field_profile["frequencies"][tag]["global_support"] >= 0.5
            ]
            field_profile["selection_rule"] = "global_support_gte_50_percent"

        tag_coverage = round(
            sum(tag_field_coverages.values()) / len(tag_field_coverages), 4
        )
        component_weights = MATCH_COMPONENT_WEIGHTS[layer]
        layer_coverage = round(
            numeric_coverage * component_weights["numeric"]
            + tag_coverage * component_weights["tag"],
            4,
        )
        layer_coverages[layer] = layer_coverage
        profile[layer]["coverage"] = {
            "selected_total": selected_total,
            "numeric_coverage": numeric_coverage,
            "numeric_feature_coverage": numeric_feature_coverage,
            "tag_coverage": tag_coverage,
            "tag_field_coverage": tag_field_coverages,
            "layer_coverage": layer_coverage,
        }

    profile["coverage"] = {
        "selected_total": selected_total,
        "layer_coverage": layer_coverages,
        "overall_coverage": round(
            sum(
                layer_coverages[layer] * LAYER_WEIGHTS[layer]
                for layer in LAYERS
            ),
            4,
        ),
    }
    return profile


def generate_coverage_aware_explanations(
    profile: Mapping[str, object],
) -> Dict[str, str]:
    """生成不会把低覆盖条件频率误称为“100% 共同偏好”的摘要。"""
    explanations: Dict[str, str] = {}
    for layer in LAYERS:
        numeric = profile[layer]["numeric"]
        high = [
            NUMERIC_DISPLAY_NAMES[key]
            for key, value in numeric.items()
            if value is not None and value >= 4
        ]
        tag_evidence = []
        limited_evidence = False
        for field_profile in profile[layer]["tags"].values():
            for tag in field_profile["common_tags"]:
                detail = field_profile["frequencies"][tag]
                tag_evidence.append(
                    (
                        tag,
                        detail["support_count"],
                        field_profile["selected_total"],
                        detail["global_support"],
                    )
                )
                if field_profile["field_coverage"] < 1:
                    limited_evidence = True
        tag_evidence.sort(key=lambda item: (-item[3], item[0]))

        parts = []
        if high:
            parts.append(f"数值偏好突出在{'、'.join(high[:3])}")
        if tag_evidence:
            tags = "、".join(
                f"{tag}（{support}/{total}）"
                for tag, support, total, _ in tag_evidence[:3]
            )
            parts.append(f"当前 Tag 支持为{tags}")
        if limited_evidence:
            parts.append("部分 Tag 字段覆盖有限，不解读为确定的共同偏好")
        explanations[layer] = "；".join(parts) + "。" if parts else "当前证据不足。"
    return explanations
