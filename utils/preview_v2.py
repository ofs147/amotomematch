"""AOMatch v2 UI Preview 的纯展示辅助函数。"""

from math import ceil
from typing import Dict, List, Mapping

import pandas as pd

from utils.schema import (
    ARCHETYPE,
    LAYERS,
    LOOK,
    NUMERIC_DISPLAY_NAMES,
    NUMERIC_FEATURES,
    NUMERIC_FEATURES_BY_LAYER,
    PERSONALITY,
    ROMANCE,
)


LAYER_UI = {
    LOOK: ("你的视觉 XP", "外貌偏好"),
    PERSONALITY: ("你的性格 XP", "性格偏好"),
    ARCHETYPE: ("你的属性 XP", "人设 / 属性偏好"),
    ROMANCE: ("你的恋爱 XP", "恋爱关系偏好"),
}

MATCH_LEVELS = ("极高契合", "高契合", "中高契合", "中等契合", "较低契合")

FEATURE_PHRASES = {
    "visual_maturity": ("少年感更戳你", "偏爱成熟外形"),
    "physical_presence": ("偏爱轻盈体型", "偏爱强存在感"),
    "warmth": ("容易被清冷感吸引", "温柔很重要"),
    "extroversion": ("偏爱安静内敛", "偏爱外向活力"),
    "emotional_expression": ("偏爱克制表达", "偏爱直率表达"),
    "personality_maturity": ("青涩感也能打动你", "看重成熟可靠"),
    "humor": ("偏爱认真沉静", "会被幽默玩心吸引"),
    "cunning": ("偏爱坦诚直接", "容易被心机感吸引"),
    "emotional_stability": ("能接受情绪张力", "看重情绪稳定"),
    "danger_level": ("偏爱安心感", "危险感很戳你"),
    "mystery_level": ("偏爱坦率可读", "神秘感很戳你"),
    "gap_moe": ("偏爱表里一致", "反差感很重要"),
    "initiative": ("偏爱慢热靠近", "偏爱主动靠近"),
    "possessiveness": ("不强调占有", "偏爱强占有感"),
    "protectiveness": ("不强调被保护", "强保护感很重要"),
    "dependence": ("偏爱独立关系", "看重情感依恋"),
    "jealousy": ("偏爱低吃醋关系", "吃醋感也会心动"),
    "push_pull": ("偏爱直接关系", "享受关系拉扯"),
    "devotion": ("偏爱克制投入", "看重深情奉献"),
    "control": ("偏爱低压关系", "能接受强控制感"),
}

FLEXIBLE_PHRASES = {
    "visual_maturity": "视觉成熟度不固定",
    "physical_presence": "纤细或强存在感都可以",
    "warmth": "清冷与温柔都可能心动",
    "extroversion": "外向 / 内向都可以",
    "emotional_expression": "情绪表达方式比较开放",
    "personality_maturity": "青涩与成熟各有吸引力",
    "humor": "严肃或有玩心都可以",
    "cunning": "坦率与心机型都可能命中",
    "emotional_stability": "对情绪稳定度没有固定答案",
    "danger_level": "安心系与危险系都可能喜欢",
    "mystery_level": "坦率或神秘都可以",
    "gap_moe": "对反差感的接受范围较宽",
    "initiative": "主动或慢热都可能心动",
    "possessiveness": "对占有感的接受范围较宽",
    "protectiveness": "对保护感的偏好较灵活",
    "dependence": "独立与依恋型关系都可以",
    "jealousy": "对吃醋感的接受范围较宽",
    "push_pull": "直接与拉扯型关系都可以",
    "devotion": "对投入程度的偏好较灵活",
    "control": "对关系控制感的接受范围较宽",
}

FEATURE_TRAITS = {
    "visual_maturity": ("少年感", "成熟外形"),
    "physical_presence": ("轻盈体型", "强存在感"),
    "warmth": ("清冷", "温柔"),
    "extroversion": ("内敛", "外向"),
    "emotional_expression": ("克制表达", "直率表达"),
    "personality_maturity": ("青涩", "成熟可靠"),
    "humor": ("认真沉静", "幽默玩心"),
    "cunning": ("坦诚", "心机感"),
    "emotional_stability": ("情绪张力", "情绪稳定"),
    "danger_level": ("安心感", "危险感"),
    "mystery_level": ("坦率", "神秘感"),
    "gap_moe": ("表里一致", "高反差"),
    "initiative": ("慢热靠近", "主动靠近"),
    "possessiveness": ("低占有", "强占有"),
    "protectiveness": ("低保护", "强保护"),
    "dependence": ("独立关系", "高依恋"),
    "jealousy": ("低吃醋", "吃醋感"),
    "push_pull": ("直接关系", "关系拉扯"),
    "devotion": ("克制投入", "高奉献"),
    "control": ("低压关系", "强控制"),
}


def profile_evidence_label(coverage: float) -> str:
    if coverage >= 0.75:
        return "证据充分"
    if coverage >= 0.5:
        return "有一定支持"
    return "当前样本较少"


def _feature_value(profile: Mapping[str, object], feature: str):
    for layer, features in NUMERIC_FEATURES_BY_LAYER.items():
        if feature in features:
            return profile[layer]["numeric"].get(feature)
    return None


def _feature_phrase(feature: str, value: float) -> str:
    return FEATURE_PHRASES[feature][value >= 3]


def _feature_trait(feature: str, value: float) -> str:
    return FEATURE_TRAITS[feature][value >= 3]


def extract_profile_preferences(
    selected: pd.DataFrame, profile: Mapping[str, object]
) -> Dict[str, List[Dict[str, object]]]:
    """提取稳定 Core Preference 与跨角色差异较大的 Flexible Preference。"""
    core = []
    flexible = []
    for feature in NUMERIC_FEATURES:
        values = pd.to_numeric(selected[feature], errors="coerce").dropna()
        if not len(values):
            continue
        value = float(values.mean())
        coverage = len(values) / len(selected)
        deviation = abs(value - 3.0)
        std = float(values.std(ddof=0))
        value_range = float(values.max() - values.min())
        consistency = max(0.0, 1.0 - std / 1.5)
        item = {
            "feature": feature,
            "display_name": NUMERIC_DISPLAY_NAMES[feature],
            "value": round(value, 2),
            "coverage": round(coverage, 4),
            "consistency": round(consistency, 4),
            "range": round(value_range, 2),
        }
        if coverage >= 0.7 and consistency >= 0.65 and deviation >= 0.5:
            item.update({
                "label": _feature_phrase(feature, value),
                "strength": deviation * coverage * consistency,
            })
            core.append(item)
        if coverage >= 0.5 and (std >= 0.9 or value_range >= 2.0):
            item = dict(item)
            item.update({
                "label": FLEXIBLE_PHRASES[feature],
                "flexibility": max(std, value_range / 2) * coverage,
            })
            flexible.append(item)
    core.sort(key=lambda item: (-item["strength"], item["feature"]))
    flexible.sort(key=lambda item: (-item["flexibility"], item["feature"]))
    return {"core": core, "flexible": flexible}


def build_core_xp_hero(
    selected: pd.DataFrame,
    profile: Mapping[str, object],
) -> Dict[str, object]:
    preferences = extract_profile_preferences(selected, profile)
    representative = preferences["core"][:3]
    if not representative:
        fallback = []
        for layer in LAYERS:
            fallback.extend(prominent_numeric_features(profile[layer], limit=2))
        fallback.sort(key=lambda item: -abs(item["value"] - 3) * item["coverage"])
        representative = [
            {
                **item,
                "label": _feature_phrase(item["feature"], item["value"]),
            }
            for item in fallback[:3]
        ]
    for item in representative:
        item["short_label"] = _feature_trait(item["feature"], item["value"])
    title = " × ".join(
        item["short_label"] for item in representative
    ) or "多面心动型"
    features = {item["feature"]: item for item in representative}
    all_values = {feature: _feature_value(profile, feature) for feature in NUMERIC_FEATURES}
    if (
        (all_values.get("protectiveness") or 0) >= 4
        and (all_values.get("devotion") or 0) >= 4
        and (all_values.get("control") or 5) <= 2.5
    ):
        summary = "你更容易被愿意守护并认真投入、但不会过度控制你的角色吸引。"
    elif (
        (all_values.get("dependence") or 0) >= 4
        and (all_values.get("push_pull") or 0) >= 4
    ):
        summary = "你更容易被情感连接强、关系中带有明显拉扯感的角色吸引。"
    elif representative:
        summary = "你更容易被" + "、".join(
            item["label"] for item in representative[:3]
        ) + "的角色吸引。"
    else:
        summary = "你的心动类型比较多元，目前还没有单一特征占据绝对主导。"
    coverage = float(profile["coverage"]["overall_coverage"])
    return {
        "title": title,
        "summary": summary,
        "representative_preferences": representative,
        "coverage": coverage,
        "evidence_label": profile_evidence_label(coverage),
        "preferences": preferences,
    }


def build_layer_summaries(profile: Mapping[str, object]) -> Dict[str, Dict[str, object]]:
    summaries = {}
    for layer in LAYERS:
        numeric = prominent_numeric_features(profile[layer], limit=3)
        for item in numeric:
            item["interpretation"] = _feature_phrase(item["feature"], item["value"])
        coverage = float(profile[layer]["coverage"]["layer_coverage"])
        summaries[layer] = {
            "numeric": numeric,
            "tags": [item["tag"] for item in supported_tags(profile[layer], limit=3)],
            "coverage": coverage,
            "evidence_label": profile_evidence_label(coverage),
        }
    return summaries


def generate_profile_insights(
    selected: pd.DataFrame, profile: Mapping[str, object]
) -> List[str]:
    preferences = extract_profile_preferences(selected, profile)
    values = {feature: _feature_value(profile, feature) for feature in NUMERIC_FEATURES}
    insights = []
    if (values.get("protectiveness") or 0) >= 4 and (values.get("control") or 5) <= 2.5:
        insights.append("你喜欢强保护感，但并不偏好高控制。")
    if (values.get("dependence") or 0) >= 4 and (values.get("push_pull") or 0) >= 4:
        insights.append("你看重深度情感连接，也容易被关系拉扯感吸引。")
    if (values.get("danger_level") or 0) >= 4 and (values.get("emotional_stability") or 0) >= 3.5:
        insights.append("危险感可以很强，但角色本身最好仍有稳定可靠的一面。")
    if (values.get("devotion") or 0) >= 4 and (values.get("initiative") or 5) <= 2.5:
        insights.append("你看重深情投入，但不要求感情一开始就非常主动。")
    if len(insights) < 3 and preferences["core"]:
        item = preferences["core"][0]
        text = f"「{item['label']}」是目前证据最稳定的心动线索。"
        if text not in insights:
            insights.append(text)
    if len(insights) < 3 and preferences["flexible"]:
        insights.append(f"同时，{preferences['flexible'][0]['label']}。")
    return insights[:3]


def build_branch_display_groups(
    multi_profile: Mapping[str, object], selected_total: int
) -> Dict[str, List[Dict[str, object]]]:
    sub_branches = list(multi_profile.get("sub_branches", []))
    candidates = sub_branches or (
        list(multi_profile.get("branches", []))
        if len(multi_profile.get("branches", [])) > 1
        else []
    )
    primary = []
    hidden = []
    for branch in candidates:
        features = []
        for feature in branch.get("label_source_features", [])[:3]:
            value = _feature_value(branch["profile"], feature)
            if value is not None:
                features.append({
                    "feature": feature,
                    "label": _feature_trait(feature, float(value)),
                    "value": float(value),
                })
        explanation = (
            "这条支线更偏向" + "、".join(item["label"] for item in features) + "。"
            if features
            else branch["summary"]
        )
        item = {
            "branch_id": branch["branch_id"],
            "label": branch["name"],
            "members": branch["character_names"],
            "features": features,
            "confidence": float(branch["confidence"]),
            "confidence_label": profile_evidence_label(float(branch["confidence"])),
            "support_count": int(branch["selected_count"]),
            "selected_total": selected_total,
            "support": f"{branch['selected_count']}/{selected_total}",
            "explanation": explanation,
            "branch_importance": float(branch.get(
                "branch_importance", branch["confidence"] * branch["selected_count"]
            )),
        }
        if int(branch["selected_count"]) == 1 or branch.get("is_hidden_preference", False):
            item["caption"] = "你可能偶尔也会被这种类型击中。"
            hidden.append(item)
        else:
            primary.append(item)
    primary.sort(
        key=lambda item: (
            -item["branch_importance"], -item["support_count"], item["label"]
        )
    )
    limit = visible_branch_limit(selected_total)
    for item in primary[limit:]:
        item["caption"] = "这条口味目前相对次要，也值得继续观察。"
        item["is_demoted_branch"] = True
        hidden.append(item)
    primary = primary[:limit]
    return {"primary": primary, "hidden": hidden}


def visible_branch_limit(selected_total: int) -> int:
    """Keep the product profile readable as selection size grows."""
    return 2 if selected_total <= 4 else 3


def candidate_pool_percentile(candidate_rank: int, candidate_pool_size: int) -> int:
    """把候选池名次转为 Top N%；使用向上取整避免夸大排名。"""
    if candidate_pool_size < 1:
        raise ValueError("candidate_pool_size must be positive")
    if candidate_rank < 1 or candidate_rank > candidate_pool_size:
        raise ValueError("candidate_rank must be within the candidate pool")
    return max(1, ceil(candidate_rank / candidate_pool_size * 100))


def match_level(percentile: int, evidence_score: float, coverage: float) -> str:
    """以候选池相对位置为主，并由 evidence 与 coverage 作克制校正。"""
    if percentile <= 5:
        tier = 0
    elif percentile <= 15:
        tier = 1
    elif percentile <= 35:
        tier = 2
    elif percentile <= 65:
        tier = 3
    else:
        tier = 4

    if evidence_score >= 72 and coverage >= 0.65:
        tier = max(0, tier - 1)
    elif evidence_score < 55:
        tier = min(4, tier + 1)

    # 低 evidence coverage 只能限制表达强度，不影响排序。
    if coverage < 0.4:
        tier = max(tier, 3)
    elif coverage < 0.6:
        tier = max(tier, 2)
    return MATCH_LEVELS[tier]


def coverage_display_note(coverage: float) -> str | None:
    if coverage < 0.4:
        return "当前角色资料覆盖有限"
    if coverage < 0.6:
        return "基于部分有效特征判断"
    return None


def branch_rescue_display(
    branch_rescued: bool,
    matched_branch_name: str | None,
    branch_member_count: int,
) -> str | None:
    """只有 eligible multi-character rescue 才生成用户可见说明。"""
    if branch_rescued and matched_branch_name and branch_member_count >= 2:
        return f"特别命中「{matched_branch_name}」"
    return None


def coverage_label(coverage: float) -> str:
    if coverage >= 0.8:
        return "高"
    if coverage >= 0.5:
        return "中"
    return "较低"


def prominent_numeric_features(
    layer_profile: Mapping[str, object], limit: int = 4
) -> List[Dict[str, object]]:
    """选出离中性值 3 最远、且证据覆盖较高的 Numeric。"""
    feature_coverage = layer_profile["coverage"]["numeric_feature_coverage"]
    items = []
    for feature, value in layer_profile["numeric"].items():
        if value is None:
            continue
        coverage = float(feature_coverage.get(feature, 0.0))
        items.append(
            {
                "feature": feature,
                "display_name": NUMERIC_DISPLAY_NAMES[feature],
                "value": float(value),
                "coverage": coverage,
            }
        )
    items.sort(
        key=lambda item: (
            -abs(item["value"] - 3) * item["coverage"],
            -item["coverage"],
            item["display_name"],
        )
    )
    return items[:limit]


def supported_tags(
    layer_profile: Mapping[str, object], limit: int = 6
) -> List[Dict[str, object]]:
    """按 global support 排序，不把条件频率冒充共同偏好。"""
    tags = []
    for field, field_profile in layer_profile["tags"].items():
        for tag, detail in field_profile["frequencies"].items():
            tags.append(
                {
                    "tag": tag,
                    "field": field,
                    "support_count": detail["support_count"],
                    "selected_total": field_profile["selected_total"],
                    "global_support": detail["global_support"],
                    "conditional_frequency": detail["conditional_frequency"],
                    "field_coverage": field_profile["field_coverage"],
                }
            )
    tags.sort(
        key=lambda item: (
            -item["global_support"],
            -item["field_coverage"],
            item["tag"],
        )
    )
    return tags[:limit]


def generate_preview_summary(profile: Mapping[str, object]) -> str:
    """只使用中高覆盖数值生成一段规则总结。"""
    personality = profile[PERSONALITY]
    romance = profile[ROMANCE]
    parts = []

    personality_high = [
        NUMERIC_DISPLAY_NAMES[key]
        for key, value in personality["numeric"].items()
        if value is not None
        and value >= 4
        and personality["coverage"]["numeric_feature_coverage"].get(key, 0) >= 0.5
    ]
    if personality_high:
        parts.append(f"你更容易被{'、'.join(personality_high[:3])}突出的角色吸引")

    romance_high = [
        NUMERIC_DISPLAY_NAMES[key]
        for key, value in romance["numeric"].items()
        if value is not None
        and value >= 4
        and romance["coverage"]["numeric_feature_coverage"].get(key, 0) >= 0.5
    ]
    romance_low = [
        NUMERIC_DISPLAY_NAMES[key]
        for key, value in romance["numeric"].items()
        if value is not None
        and value <= 2.25
        and romance["coverage"]["numeric_feature_coverage"].get(key, 0) >= 0.5
    ]
    if romance_high:
        parts.append(f"在恋爱关系中更看重{'、'.join(romance_high[:3])}")
    if romance_low:
        parts.append(f"对高{'、高'.join(romance_low[:2])}的关系偏好较低")

    if not parts:
        return "当前证据还不足以生成稳定的 XP 总结。"
    return "。".join(parts) + "。"


def generate_xp_labels_v2_1(profile: Mapping[str, object]) -> List[str]:
    """根据 Numeric 值与覆盖率生成 3～5 个产品化 XP Labels。"""
    labels = []

    def eligible(layer: str, feature: str) -> tuple[float, float]:
        value = profile[layer]["numeric"].get(feature)
        coverage = profile[layer]["coverage"]["numeric_feature_coverage"].get(
            feature, 0
        )
        return value, coverage

    rules = (
        (PERSONALITY, "personality_maturity", lambda v: v >= 4, "成熟可靠派"),
        (ROMANCE, "protectiveness", lambda v: v >= 4, "强保护感偏好"),
        (ROMANCE, "devotion", lambda v: v >= 4.5, "深情奉献派"),
        (ROMANCE, "control", lambda v: v <= 2.25, "低控制恋爱"),
        (ROMANCE, "push_pull", lambda v: v >= 4, "高拉扯玩家"),
        (ROMANCE, "dependence", lambda v: v >= 4, "高关系连接需求"),
        (ARCHETYPE, "danger_level", lambda v: v >= 4, "危险感爱好者"),
        (LOOK, "visual_maturity", lambda v: v <= 2.5, "少年感收集家"),
        (ROMANCE, "initiative", lambda v: v >= 4, "主动恋爱派"),
    )
    for layer, feature, condition, label in rules:
        value, coverage = eligible(layer, feature)
        if value is not None and coverage >= 0.7 and condition(value):
            labels.append(label)
        if len(labels) == 5:
            break

    fallback = ["多维 XP 探索者", "角色关系观察家", "心动线索收集家"]
    for label in fallback:
        if len(labels) >= 3:
            break
        labels.append(label)
    return labels


def is_surprise_match(result: Mapping[str, object]) -> bool:
    """整体不低，但 Romance 明显弱于性格/属性时标记 Surprise。"""
    overall = float(result["coverage_adjusted_match_score"])
    romance = float(result[f"adjusted_{ROMANCE}"])
    alternative = max(
        float(result[f"adjusted_{PERSONALITY}"]),
        float(result[f"adjusted_{ARCHETYPE}"]),
    )
    return overall >= 55 and (romance < 55 or alternative - romance >= 15)


def surprise_explanation() -> str:
    return "虽然你们的恋爱模式不完全一致，但在性格与人设层面出现了较强匹配。"
