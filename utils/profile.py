"""生成用户 XP 画像、标签和文字总结。"""

from typing import Dict, List

import pandas as pd


# MVP 使用的六个可量化偏好维度。
PROFILE_DIMENSIONS = {
    "possessiveness": "占有欲",
    "initiative": "主动程度",
    "danger_level": "危险感",
    "maturity": "成熟感",
    "humor": "幽默感",
    "gap_moe": "反差萌",
}


def build_xp_profile(selected_characters: pd.DataFrame) -> Dict[str, float]:
    """计算所选角色在各偏好维度上的平均值。"""
    return {
        dimension: round(float(selected_characters[dimension].mean()), 2)
        for dimension in PROFILE_DIMENSIONS
    }


def generate_xp_tags(profile: Dict[str, float]) -> List[str]:
    """根据画像分数生成 3～5 个 XP 标签，方便未来替换成更复杂逻辑。"""
    rules = [
        ("initiative", 4.0, "强主动型捕获者"),
        ("danger_level", 3.8, "危险系爱好者"),
        ("gap_moe", 4.0, "反差萌重度患者"),
        ("possessiveness", 3.8, "高占有欲偏好"),
        ("maturity", 4.0, "成熟可靠派"),
        ("humor", 4.0, "有趣灵魂雷达"),
    ]
    tags = [label for key, threshold, label in rules if profile[key] >= threshold]

    if profile["danger_level"] >= 3.3 and profile["possessiveness"] >= 3.3:
        tags.append("情绪拉扯型恋爱脑")

    # 分数不极端时，也根据最突出的维度补足至少 3 个标签。
    fallback = {
        "possessiveness": "专属感需求者",
        "initiative": "心动行动派",
        "danger_level": "刺激剧情偏好",
        "maturity": "安心感收藏家",
        "humor": "轻松互动派",
        "gap_moe": "反差感探测器",
    }
    for key, _ in sorted(profile.items(), key=lambda item: item[1], reverse=True):
        if len(tags) >= 3:
            break
        label = fallback[key]
        if label not in tags:
            tags.append(label)

    return tags[:5]


def generate_profile_summary(profile: Dict[str, float]) -> str:
    """使用简单规则生成自然语言 XP 总结，不调用外部 API。"""
    ranked = sorted(profile, key=profile.get, reverse=True)
    first, second = ranked[:2]
    first_name = PROFILE_DIMENSIONS[first]
    second_name = PROFILE_DIMENSIONS[second]

    text = f"你似乎特别容易被具有高{first_name}和明显{second_name}的角色吸引。"
    if profile["danger_level"] >= 3.5:
        text += "比起完全温柔稳定的关系，你更享受带有危险感与情绪张力的故事。"
    elif profile["maturity"] >= 3.8:
        text += "你也很看重关系中的可靠感、责任感与稳定陪伴。"
    else:
        text += "你偏爱的关系既需要心动刺激，也要保留自然相处的空间。"

    if profile["gap_moe"] >= 4.0:
        text += "角色表里不一、偶尔露出柔软一面的瞬间，尤其容易击中你。"
    return text
