"""AOMatch MVP 的可解释角色匹配算法。"""

from typing import Dict, List

import pandas as pd

from utils.profile import PROFILE_DIMENSIONS


def calculate_match_score(profile: Dict[str, float], character: pd.Series) -> int:
    """以加权平均绝对差计算 0～100 的匹配分。

    用户画像越偏离中间值 3，代表该维度的偏好越明确，因此权重稍高。
    0.85 次幂用于拉开相近候选人的分数，所有差异仍完全来自角色属性。
    """
    weighted_difference = 0.0
    total_weight = 0.0

    for dimension in PROFILE_DIMENSIONS:
        user_score = profile[dimension]
        difference = abs(user_score - float(character[dimension]))
        weight = 1 + abs(user_score - 3) * 0.25
        weighted_difference += difference * weight
        total_weight += weight

    average_difference = weighted_difference / total_weight
    similarity = max(0.0, 1 - average_difference / 4)
    return max(0, min(100, round((similarity**0.85) * 100)))


def get_matching_dimensions(
    profile: Dict[str, float], character: pd.Series, top_n: int = 3
) -> List[str]:
    """返回候选角色与用户画像最接近的 2～3 个维度键。"""
    top_n = max(2, min(3, top_n))
    return sorted(
        PROFILE_DIMENSIONS,
        key=lambda dimension: (
            abs(profile[dimension] - float(character[dimension])),
            -abs(profile[dimension] - 3),
        ),
    )[:top_n]


def explain_recommendation(profile: Dict[str, float], character: pd.Series) -> str:
    """根据真实匹配维度和偏好强度，选择不同的规则文案。"""
    closest = get_matching_dimensions(profile, character)
    names = [PROFILE_DIMENSIONS[dimension] for dimension in closest]
    high_matches = [dimension for dimension in closest if profile[dimension] >= 4]
    character_name = character["character_name"]

    # 只有用户分数达到 4，才描述为“较高偏好”或“明显偏好”。
    if len(high_matches) >= 2:
        high_names = [PROFILE_DIMENSIONS[dimension] for dimension in high_matches[:2]]
        return (
            f"你的 XP Profile 对{high_names[0]}与{high_names[1]}表现出较高偏好，"
            f"而{character_name}在这两个维度与你高度匹配。"
        )

    if (
        "gap_moe" in closest
        and profile["gap_moe"] >= 4
        and float(character["gap_moe"]) >= 4
    ):
        other_name = next(name for key, name in zip(closest, names) if key != "gap_moe")
        return (
            f"你选择的角色普遍带有明显的反差感，{character_name}的反差萌评分同样很高，"
            f"同时在{other_name}上也与你的偏好接近。"
        )

    if high_matches:
        high_name = PROFILE_DIMENSIONS[high_matches[0]]
        other_names = [
            PROFILE_DIMENSIONS[dimension]
            for dimension in closest
            if dimension != high_matches[0]
        ]
        return (
            f"你对{high_name}有较高偏好；{character_name}不仅符合这一点，"
            f"在{other_names[0]}与{other_names[1]}上也和你的 XP Profile 接近。"
        )

    exact_matches = [
        dimension
        for dimension in closest
        if abs(profile[dimension] - float(character[dimension])) <= 0.5
    ]
    if len(exact_matches) >= 2:
        exact_names = [PROFILE_DIMENSIONS[dimension] for dimension in exact_matches[:2]]
        return (
            f"{character_name}在{exact_names[0]}和{exact_names[1]}上与你目前的 XP Profile "
            "非常接近，整体气质与已有偏好自然衔接。"
        )

    return (
        f"虽然{character_name}并不是与你完全相同的类型，但在{names[0]}、{names[1]}和"
        f"{names[2]}上与你的 XP Profile 较为接近，可能是值得尝试的新方向。"
    )


def recommend_characters(
    characters: pd.DataFrame,
    profile: Dict[str, float],
    selected_names: List[str],
    top_n: int = 5,
) -> pd.DataFrame:
    """排除用户已选角色，并返回按匹配分排序的 Top N。"""
    candidates = characters[~characters["character_name"].isin(selected_names)].copy()
    candidates["match_score"] = candidates.apply(
        lambda row: calculate_match_score(profile, row), axis=1
    )
    candidates["matching_dimensions"] = candidates.apply(
        lambda row: get_matching_dimensions(profile, row), axis=1
    )
    candidates["recommendation_reason"] = candidates.apply(
        lambda row: explain_recommendation(profile, row), axis=1
    )
    return candidates.sort_values(
        ["match_score", "character_name"], ascending=[False, True]
    ).head(top_n)
