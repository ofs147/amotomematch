"""AOMatch v2 四层 XP Profile 原型。

本模块只服务于 Character Database v2 的验证，当前 MVP v1.1 尚未接入。
"""

from collections import Counter
from pathlib import Path
from typing import Dict, List, Mapping, Optional

import pandas as pd

from utils.data_utils import parse_tags
from utils.preference_strength_v4 import (
    DEFAULT_PREFERENCE_STRENGTH,
    PREFERENCE_STRENGTH_COLUMN,
    preference_strength_value,
)
from utils.schema import (
    ARCHETYPE,
    LAYERS,
    LOOK,
    NUMERIC_DISPLAY_NAMES,
    NUMERIC_FEATURES_BY_LAYER,
    PERSONALITY,
    ROMANCE,
    TAG_FIELDS_BY_LAYER,
)


def load_characters_v2(path: Path) -> pd.DataFrame:
    """读取 v2 角色数据；空字符串和 NA 会保留为缺失值。"""
    return pd.read_csv(path)


def _numeric_profile(
    selected_characters: pd.DataFrame, features: tuple[str, ...]
) -> Dict[str, Optional[float]]:
    """计算数值字段加权平均；Coverage 仍由实际有效角色数决定。"""
    result: Dict[str, Optional[float]] = {}
    if PREFERENCE_STRENGTH_COLUMN in selected_characters:
        weights = selected_characters[PREFERENCE_STRENGTH_COLUMN].map(
            preference_strength_value
        )
    else:
        weights = pd.Series(
            DEFAULT_PREFERENCE_STRENGTH, index=selected_characters.index
        )
    for feature in features:
        values = pd.to_numeric(selected_characters[feature], errors="coerce")
        valid = values.notna()
        mean_value = (
            (values[valid] * weights[valid]).sum() / weights[valid].sum()
            if valid.any()
            else float("nan")
        )
        result[feature] = None if pd.isna(mean_value) else round(float(mean_value), 2)
    return result


def _tag_field_profile(
    values: pd.Series, minimum_frequency: float = 0.5, fallback_limit: int = 3
) -> Dict[str, object]:
    """统计一个 Tag Field 内各标签按角色计数的频率。

    分母是该字段存在至少一个标签的有效角色数。同一角色即使重复写入同一标签，
    也只贡献一次计数。
    """
    tag_sets = [parse_tags(value) for value in values]
    valid_sets = [tags for tags in tag_sets if tags]
    valid_count = len(valid_sets)

    counter: Counter[str] = Counter()
    for tags in valid_sets:
        counter.update(tags)

    ordered_tags = sorted(counter, key=lambda tag: (-counter[tag], tag))
    frequencies = {
        tag: {
            "count": counter[tag],
            "frequency": round(counter[tag] / valid_count, 2),
        }
        for tag in ordered_tags
    } if valid_count else {}

    common_tags = [
        tag
        for tag in ordered_tags
        if frequencies[tag]["frequency"] >= minimum_frequency
    ]
    selection_rule = "frequency_gte_50_percent"

    # 没有标签达到阈值时，保留最高频的最多 3 个，避免 Profile 完全空白。
    if not common_tags and ordered_tags:
        common_tags = ordered_tags[:fallback_limit]
        selection_rule = "top_frequency_fallback"

    return {
        "valid_character_count": valid_count,
        "frequencies": frequencies,
        "common_tags": common_tags,
        "selection_rule": selection_rule,
    }


def build_xp_profile_v2(selected_characters: pd.DataFrame) -> Dict[str, object]:
    """从一个或多个所选角色生成 LOOK/PERSONALITY/ARCHETYPE/ROMANCE。"""
    if selected_characters.empty:
        raise ValueError("至少需要选择一个角色才能生成 v2 XP Profile")

    profile: Dict[str, object] = {}
    for layer in LAYERS:
        numeric = _numeric_profile(
            selected_characters, NUMERIC_FEATURES_BY_LAYER[layer]
        )
        tags = {
            field: _tag_field_profile(selected_characters[field])
            for field in TAG_FIELDS_BY_LAYER[layer]
        }
        profile[layer] = {"numeric": numeric, "tags": tags}
    return profile


def _selected_layer_tags(layer_profile: Mapping[str, object]) -> List[str]:
    """按频率收集一层中已筛选的标签，用于生成简短解释。"""
    ranked = []
    tag_fields = layer_profile["tags"]
    for field_profile in tag_fields.values():
        for tag in field_profile["common_tags"]:
            detail = field_profile["frequencies"][tag]
            ranked.append((tag, detail["frequency"], detail["count"]))
    ranked.sort(key=lambda item: (-item[1], -item[2], item[0]))
    return [tag for tag, _, _ in ranked]


def _high_and_low_numeric(
    numeric: Mapping[str, Optional[float]],
) -> tuple[List[str], List[str]]:
    """高偏好使用 >=4，低偏好使用 <=2；缺失值不参与判断。"""
    high = [
        NUMERIC_DISPLAY_NAMES[key]
        for key, value in numeric.items()
        if value is not None and value >= 4
    ]
    low = [
        NUMERIC_DISPLAY_NAMES[key]
        for key, value in numeric.items()
        if value is not None and value <= 2
    ]
    return high, low


def generate_profile_explanations(profile: Mapping[str, object]) -> Dict[str, str]:
    """使用透明规则，为四层 Profile 分别生成简短中文解释。"""
    explanations: Dict[str, str] = {}

    for layer in LAYERS:
        layer_profile = profile[layer]
        high, low = _high_and_low_numeric(layer_profile["numeric"])
        tags = _selected_layer_tags(layer_profile)

        if layer == LOOK:
            details = high[:2] + tags[:3]
            explanations[layer] = (
                f"你似乎更容易被{'、'.join(details)}的角色吸引。"
                if details
                else "目前还没有足够的外貌偏好数据。"
            )
        elif layer == PERSONALITY:
            parts = []
            if high:
                parts.append(f"你对{'、'.join(high[:3])}表现出较高偏好")
            if tags:
                parts.append(f"共同性格标签包括{'、'.join(tags[:3])}")
            if low:
                parts.append(f"而{'、'.join(low[:2])}倾向较低")
            explanations[layer] = "；".join(parts) + "。" if parts else "目前还没有足够的性格偏好数据。"
        elif layer == ARCHETYPE:
            parts = []
            if tags:
                parts.append(f"{'、'.join(tags[:3])}属性出现频率较高")
            if high:
                parts.append(f"你也更容易被高{'、高'.join(high[:2])}击中")
            explanations[layer] = "；".join(parts) + "。" if parts else "目前还没有足够的角色属性数据。"
        elif layer == ROMANCE:
            parts = []
            if high:
                parts.append(f"你的关系偏好集中在高{'、高'.join(high[:3])}")
            if low:
                parts.append(f"对高{'、高'.join(low[:2])}关系兴趣较低")
            if tags:
                parts.append(f"常见恋爱模式为{'、'.join(tags[:3])}")
            explanations[layer] = "；".join(parts) + "。" if parts else "目前还没有足够的恋爱模式数据。"

    return explanations
