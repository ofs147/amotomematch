"""AOMatch v2.2 Dynamic Multi-Branch XP 实验实现。

仅供 app_v2_preview.py 使用；保留既有 Global Centroid 与 v2.1 排名。
"""

from __future__ import annotations

from itertools import combinations
from math import sqrt
from typing import Dict, Iterable, List, Mapping, Sequence, Tuple

import pandas as pd

from utils.preview_v2 import (
    generate_preview_summary,
    generate_xp_labels_v2_1,
    prominent_numeric_features,
    supported_tags,
)
from utils.profile_v2_1 import build_xp_profile_v2_1
from utils.preference_strength_v4 import (
    DEFAULT_PREFERENCE_STRENGTH,
    PREFERENCE_STRENGTH_COLUMN,
    unweighted_selection,
)
from utils.recommender_v2_1 import (
    calculate_coverage_aware_breakdown,
    recommend_characters_v2_1,
)
from utils.schema import (
    LAYERS,
    NUMERIC_DISPLAY_NAMES,
    NUMERIC_FEATURES,
    NUMERIC_FEATURES_BY_LAYER,
    ROMANCE,
)


# Partition calibration constants：集中定义，避免算法中散落 magic number。
MAX_BRANCHES = 3
WITHIN_CLUSTER_WEIGHT = 0.65
BETWEEN_CLUSTER_WEIGHT = 0.35
EXTRA_BRANCH_PENALTY = 0.04
SINGLETON_PENALTY = 0.12
MIN_PARTITION_IMPROVEMENT = 0.05
MAX_SINGLETON_OUTSIDE_SIMILARITY = 0.55

# 仅在 Main Branch 保持为 1 时启用的 Sub-Branch 诊断阈值。
SUB_BRANCH_MIN_LAYER_GAP = 0.15
SUB_BRANCH_MIN_NUMERIC_GAP = 1.5
SUB_BRANCH_MIN_DIFFERENT_FEATURES = 2

# Branch confidence 与最终分数参数。
BRANCH_SAMPLE_CONFIDENCE = {1: 0.55, 2: 0.80, 3: 0.90}
BRANCH_MATCH_WEIGHT = 0.70
GLOBAL_MATCH_WEIGHT = 0.30
NEUTRAL_MATCH_SCORE = 50.0
BRANCH_HIT_HIGH = 75.0
GLOBAL_HIT_GENERAL = 70.0

# v2.3 两阶段 Branch-aware Reranking。
BASE_RETRIEVAL_MULTIPLIER = 2
BRANCH_RERANK_STRENGTH = 0.25
MAX_BRANCH_BONUS_RATIO = 0.10
COMPREHENSIVE_MATCH_MIN = 60.0
BRANCH_HIT_RAW_MIN = 65.0
BRANCH_HIT_RAW_MARGIN = 8.0

# v2.6 Gated Branch Rescue（由 v2.5 offline evaluation 选定）。
GATED_RESCUE_CONFIDENCE_THRESHOLD = 0.55
GATED_RESCUE_LAMBDA = 1.0

# v2.7 Branch Label：关系体验优先，LOOK 仅在差异非常明显时使用。
LABEL_LAYER_PRIORITY = {
    "ROMANCE": 1.0,
    "ARCHETYPE": 0.9,
    "PERSONALITY": 0.8,
    "LOOK": 0.35,
}
LABEL_FEATURE_PRIORITY = (
    "dependence", "possessiveness", "protectiveness", "devotion", "control",
    "push_pull", "initiative", "emotional_stability", "danger_level",
    "mystery_level", "gap_moe", "warmth", "emotional_expression",
    "personality_maturity", "cunning", "extroversion", "humor",
    "visual_maturity", "physical_presence",
)
LABEL_DESCRIPTORS = {
    "dependence": ("独立", "高依恋"),
    "possessiveness": ("低占有", "强占有"),
    "protectiveness": ("轻守护", "强守护"),
    "devotion": ("克制投入", "深情"),
    "control": ("低控制", "强控制"),
    "push_pull": ("低拉扯", "高拉扯"),
    "initiative": ("慢热", "主动"),
    "emotional_stability": ("情绪张力", "稳定"),
    "danger_level": ("安心", "危险"),
    "mystery_level": ("坦率", "神秘"),
    "gap_moe": ("直白", "反差"),
    "warmth": ("清冷", "温柔"),
    "emotional_expression": ("克制", "直率"),
    "personality_maturity": ("青涩", "成熟"),
    "cunning": ("坦诚", "心机"),
    "extroversion": ("安静", "外向"),
    "humor": ("认真", "玩心"),
    "visual_maturity": ("少年感", "年上感"),
    "physical_presence": ("轻盈", "强存在感"),
}


def _canonical_partition(groups: Iterable[Iterable[str]]) -> Tuple[Tuple[str, ...], ...]:
    return tuple(sorted((tuple(sorted(group)) for group in groups), key=lambda g: g[0]))


def enumerate_partitions(ids: Sequence[str], max_branches: int = MAX_BRANCHES):
    """枚举所有 1～max_branches 的无序集合分区。"""
    ids = tuple(ids)
    if not ids:
        return []
    partitions = set()

    def visit(index: int, groups: List[List[str]]) -> None:
        if index == len(ids):
            if len(groups) <= min(max_branches, len(ids)):
                partitions.add(_canonical_partition(groups))
            return
        value = ids[index]
        for position in range(len(groups)):
            groups[position].append(value)
            visit(index + 1, groups)
            groups[position].pop()
        if len(groups) < max_branches:
            groups.append([value])
            visit(index + 1, groups)
            groups.pop()

    visit(0, [])
    return sorted(partitions, key=lambda p: (len(p), p))


def pairwise_similarity_matrix(selected: pd.DataFrame) -> pd.DataFrame:
    """以现有四层 Coverage-aware Match 计算对称 pairwise similarity。"""
    ids = selected["character_id"].tolist()
    matrix = pd.DataFrame(1.0, index=ids, columns=ids, dtype=float)
    rows = {row["character_id"]: row for _, row in selected.iterrows()}
    profiles = {
        character_id: build_xp_profile_v2_1(
            selected[selected["character_id"].eq(character_id)]
        )
        for character_id in ids
    }
    for left, right in combinations(ids, 2):
        forward = calculate_coverage_aware_breakdown(
            profiles[left], rows[right]
        )["coverage_adjusted_final_score_raw"] / 100
        backward = calculate_coverage_aware_breakdown(
            profiles[right], rows[left]
        )["coverage_adjusted_final_score_raw"] / 100
        similarity = (forward + backward) / 2
        matrix.loc[left, right] = similarity
        matrix.loc[right, left] = similarity
    return matrix


def pairwise_layer_similarity_matrices(selected: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """返回四层对称 pairwise similarity，供 Sub-Branch 诊断使用。"""
    ids = selected["character_id"].tolist()
    matrices = {
        layer: pd.DataFrame(1.0, index=ids, columns=ids, dtype=float)
        for layer in LAYERS
    }
    rows = {row["character_id"]: row for _, row in selected.iterrows()}
    profiles = {
        character_id: build_xp_profile_v2_1(
            selected[selected["character_id"].eq(character_id)]
        )
        for character_id in ids
    }
    for left, right in combinations(ids, 2):
        forward = calculate_coverage_aware_breakdown(profiles[left], rows[right])
        backward = calculate_coverage_aware_breakdown(profiles[right], rows[left])
        for layer in LAYERS:
            value = (
                forward["coverage_adjusted_layer_scores_raw"][layer]
                + backward["coverage_adjusted_layer_scores_raw"][layer]
            ) / 200
            matrices[layer].loc[left, right] = value
            matrices[layer].loc[right, left] = value
    return matrices


def _mean(values: Sequence[float], fallback: float) -> float:
    return sum(values) / len(values) if values else fallback


def partition_quality(partition, matrix: pd.DataFrame) -> Dict[str, float]:
    within_values = []
    cross_values = []
    for group in partition:
        within_values.extend(
            float(matrix.loc[a, b]) for a, b in combinations(group, 2)
        )
    for left_index, left in enumerate(partition):
        for right in partition[left_index + 1 :]:
            cross_values.extend(float(matrix.loc[a, b]) for a in left for b in right)

    within = _mean(within_values, 0.5)
    separation = 1 - _mean(cross_values, 1.0) if len(partition) > 1 else 0.0
    branch_penalty = EXTRA_BRANCH_PENALTY * (len(partition) - 1)
    singleton_count = sum(len(group) == 1 for group in partition)
    singleton_penalty = SINGLETON_PENALTY * singleton_count
    quality = (
        WITHIN_CLUSTER_WEIGHT * within
        + BETWEEN_CLUSTER_WEIGHT * separation
        - branch_penalty
        - singleton_penalty
    )
    return {
        "within_cluster_similarity": within,
        "between_cluster_separation": separation,
        "branch_count_penalty": branch_penalty,
        "singleton_penalty": singleton_penalty,
        "partition_quality": quality,
    }


def _singletons_are_distinct(partition, matrix: pd.DataFrame) -> bool:
    all_ids = list(matrix.index)
    for group in partition:
        if len(group) != 1:
            continue
        item = group[0]
        outside = [other for other in all_ids if other != item]
        affinity = _mean([float(matrix.loc[item, other]) for other in outside], 1.0)
        if affinity > MAX_SINGLETON_OUTSIDE_SIMILARITY:
            return False
    return True


def choose_partition(selected: pd.DataFrame) -> Dict[str, object]:
    matrix = pairwise_similarity_matrix(selected)
    ids = selected["character_id"].tolist()
    candidates = []
    for partition in enumerate_partitions(ids):
        if len(partition) > 1 and not _singletons_are_distinct(partition, matrix):
            continue
        details = partition_quality(partition, matrix)
        candidates.append({"partition": partition, **details})

    baseline = next(item for item in candidates if len(item["partition"]) == 1)
    best = max(candidates, key=lambda item: (item["partition_quality"], -len(item["partition"])))
    if (
        len(best["partition"]) > 1
        and best["partition_quality"]
        < baseline["partition_quality"] + MIN_PARTITION_IMPROVEMENT
    ):
        best = baseline
    return {**best, "similarity_matrix": matrix, "candidate_partitions": candidates}


def branch_confidence(profile: Mapping[str, object], selected_count: int) -> float:
    sample_factor = BRANCH_SAMPLE_CONFIDENCE.get(selected_count, 1.0)
    coverage = float(profile["coverage"]["overall_coverage"])
    # Coverage 不足时向下调整，但不把未知视为零证据。
    return round(sample_factor * (0.5 + 0.5 * coverage), 4)


def _branch_name(profile: Mapping[str, object]) -> str:
    labels = generate_xp_labels_v2_1(profile)
    for label in labels:
        if label not in {"多维 XP 探索者", "角色关系观察家", "心动线索收集家"}:
            return label
    top = prominent_numeric_features(profile[ROMANCE], limit=1)
    if top:
        return f"{top[0]['display_name']}支线"
    return "核心 XP"


def _group_numeric_differences(selected: pd.DataFrame, partition) -> List[Dict[str, object]]:
    """比较两个 Sub-Branch 的 Numeric 均值，不使用 Tag 触发拆分。"""
    if len(partition) != 2:
        return []
    means = []
    for group in partition:
        frame = selected[selected["character_id"].isin(group)]
        means.append(frame)
    differences = []
    for feature in NUMERIC_FEATURES:
        left = pd.to_numeric(means[0][feature], errors="coerce").mean()
        right = pd.to_numeric(means[1][feature], errors="coerce").mean()
        if pd.isna(left) or pd.isna(right):
            continue
        gap = abs(float(left) - float(right))
        if gap >= SUB_BRANCH_MIN_NUMERIC_GAP:
            differences.append({
                "feature": feature,
                "display_name": NUMERIC_DISPLAY_NAMES[feature],
                "left_value": round(float(left), 2),
                "right_value": round(float(right), 2),
                "gap": round(gap, 2),
            })
    return sorted(differences, key=lambda item: (-item["gap"], item["feature"]))


def _sub_branch_name(profile: Mapping[str, object]) -> str:
    """使用连续数值组合命名细分支线，不依赖单个 Tag。"""
    personality = profile["PERSONALITY"]["numeric"]
    romance = profile["ROMANCE"]["numeric"]
    if (
        romance.get("dependence") is not None
        and romance["dependence"] >= 4
        and romance.get("push_pull") is not None
        and romance["push_pull"] >= 4
    ):
        return "高依恋拉扯派"
    if (
        personality.get("personality_maturity") is not None
        and personality["personality_maturity"] >= 4
        and personality.get("emotional_stability") is not None
        and personality["emotional_stability"] >= 3.5
        and romance.get("protectiveness") is not None
        and romance["protectiveness"] >= 4
    ):
        return "成熟稳定守护派"
    return _branch_name(profile)


def _numeric_profile_value(profile: Mapping[str, object], feature: str):
    for layer in LAYERS:
        if feature in NUMERIC_FEATURES_BY_LAYER[layer]:
            return profile[layer]["numeric"].get(feature)
    return None


def _relationship_suffix(profile: Mapping[str, object]) -> str:
    romance = profile[ROMANCE]["numeric"]
    choices = (
        ("protectiveness", "守护派"),
        ("devotion", "深情派"),
        ("dependence", "依恋派"),
        ("push_pull", "拉扯派"),
        ("initiative", "直球派"),
    )
    feature, suffix = max(
        choices,
        key=lambda item: abs(float(romance.get(item[0]) or 3.0) - 3.0),
    )
    if feature == "initiative" and float(romance.get(feature) or 3.0) < 3:
        return "慢热派"
    return suffix


def _compose_branch_label(
    feature: str,
    value: float,
    profile: Mapping[str, object],
    singleton: bool,
) -> str:
    descriptor = LABEL_DESCRIPTORS[feature][value >= 3]
    if singleton:
        return f"次级{descriptor}线索"
    suffix = _relationship_suffix(profile)
    if any(word in descriptor for word in ("守护", "深情", "依恋", "拉扯")):
        suffix = "派"
    return f"{descriptor}{suffix}"


def generate_distinctive_branch_labels(
    selected: pd.DataFrame,
    branches: Sequence[Mapping[str, object]],
    global_profile: Mapping[str, object],
    core_name: str,
) -> List[Dict[str, object]]:
    """用相对 Core/其他 Branch 的连续数值差异生成 context-aware 标签。"""
    if not branches:
        return []
    feature_layer = {
        feature: layer
        for layer in LAYERS
        for feature in NUMERIC_FEATURES_BY_LAYER[layer]
    }
    branch_means = []
    for branch in branches:
        members = selected[selected["character_id"].isin(branch["character_ids"])]
        branch_means.append({
            feature: pd.to_numeric(members[feature], errors="coerce").mean()
            for feature in NUMERIC_FEATURES
        })

    ranked_features = []
    for index, branch in enumerate(branches):
        members = selected[selected["character_id"].isin(branch["character_ids"])]
        candidates = []
        for priority_index, feature in enumerate(LABEL_FEATURE_PRIORITY):
            value = branch_means[index][feature]
            if pd.isna(value):
                continue
            core_value = _numeric_profile_value(global_profile, feature)
            other_values = [
                means[feature]
                for other_index, means in enumerate(branch_means)
                if other_index != index and not pd.isna(means[feature])
            ]
            core_gap = (
                abs(float(value) - float(core_value))
                if core_value is not None
                else 0.0
            )
            other_gap = (
                max(abs(float(value) - float(other)) for other in other_values)
                if other_values
                else 0.0
            )
            values = pd.to_numeric(members[feature], errors="coerce").dropna()
            consistency = max(0.25, 1.0 - float(values.std(ddof=0) if len(values) else 0) / 2)
            coverage = len(values) / max(1, len(members))
            raw_difference = 0.4 * core_gap + 0.6 * other_gap
            # 单一 Main Branch 与 Core 完全一致时，保留自身突出程度作 fallback。
            if len(branches) == 1:
                raw_difference = max(raw_difference, abs(float(value) - 3.0) * 0.25)
            score = (
                raw_difference
                * consistency
                * coverage
                * float(branch["confidence"])
                * LABEL_LAYER_PRIORITY[feature_layer[feature]]
            )
            candidates.append({
                "feature": feature,
                "value": float(value),
                "score": score,
                "core_gap": core_gap,
                "other_branch_gap": other_gap,
            })
        candidates.sort(
            key=lambda item: (
                -item["score"],
                LABEL_FEATURE_PRIORITY.index(item["feature"]),
            )
        )
        ranked_features.append(candidates)

    results = []
    used = {core_name}
    for branch, candidates in zip(branches, ranked_features):
        singleton = int(branch["selected_count"]) == 1
        label = None
        source_index = 0
        for source_index, candidate in enumerate(candidates):
            proposed = _compose_branch_label(
                candidate["feature"], candidate["value"], branch["profile"], singleton
            )
            if proposed not in used:
                label = proposed
                break
        if label is None:
            # 极端同值资料仍以第二区别词消歧，避免保留两个完全相同标题。
            first = candidates[0]
            second = candidates[min(1, len(candidates) - 1)]
            label = (
                f"次级{LABEL_DESCRIPTORS[second['feature']][second['value'] >= 3]}线索"
                if singleton
                else f"{LABEL_DESCRIPTORS[first['feature']][first['value'] >= 3]}"
                     f"{LABEL_DESCRIPTORS[second['feature']][second['value'] >= 3]}派"
            )
        used.add(label)
        source_features = [item["feature"] for item in candidates[:3]]
        if candidates[source_index]["feature"] not in source_features:
            source_features.insert(0, candidates[source_index]["feature"])
        results.append({
            "name": label,
            "label_source_features": source_features[:3],
            "distinctiveness_score": round(candidates[source_index]["score"], 4),
        })
    return results


def detect_core_sub_branches(
    selected: pd.DataFrame, main_partition: Mapping[str, object]
) -> Dict[str, object]:
    """Main 只有一支时，检测共同 Core 下是否存在细分吸引模式。"""
    if len(main_partition["partition"]) != 1 or len(selected) < 3:
        return {"detected": False, "reason": "main_partition_not_single_or_too_small"}

    overall_matrix = main_partition["similarity_matrix"]
    baseline = partition_quality(main_partition["partition"], overall_matrix)
    two_branch_candidates = []
    for partition in enumerate_partitions(selected["character_id"].tolist(), max_branches=2):
        if len(partition) != 2:
            continue
        two_branch_candidates.append({"partition": partition, **partition_quality(partition, overall_matrix)})
    best = max(two_branch_candidates, key=lambda item: item["partition_quality"])
    quality_gain = best["partition_quality"] - baseline["partition_quality"]

    layer_matrices = pairwise_layer_similarity_matrices(selected)
    layer_means = {}
    for layer, matrix in layer_matrices.items():
        values = [float(matrix.loc[a, b]) for a, b in combinations(matrix.index, 2)]
        layer_means[layer] = _mean(values, 1.0)
    layer_gap = max(layer_means.values()) - min(layer_means.values())
    numeric_differences = _group_numeric_differences(selected, best["partition"])
    detected = (
        quality_gain > 0
        and layer_gap >= SUB_BRANCH_MIN_LAYER_GAP
        and len(numeric_differences) >= SUB_BRANCH_MIN_DIFFERENT_FEATURES
    )
    return {
        "detected": detected,
        "partition": best["partition"],
        "partition_quality": best["partition_quality"],
        "baseline_quality": baseline["partition_quality"],
        "quality_gain": quality_gain,
        "layer_similarity_means": layer_means,
        "layer_gap": layer_gap,
        "numeric_differences": numeric_differences,
        "layer_similarity_matrices": layer_matrices,
        "reason": "core_plus_sub_branch_evidence" if detected else "insufficient_sub_branch_evidence",
    }


def build_multi_branch_profile(selected: pd.DataFrame) -> Dict[str, object]:
    global_profile = build_xp_profile_v2_1(selected)
    ranking_global_profile = build_xp_profile_v2_1(
        unweighted_selection(selected)
    )
    core_name = _branch_name(global_profile)
    selection = choose_partition(selected)
    names = dict(zip(selected["character_id"], selected["character_name"]))
    branches = []
    for index, group in enumerate(selection["partition"], start=1):
        members = selected[selected["character_id"].isin(group)]
        profile = build_xp_profile_v2_1(members)
        ranking_profile = build_xp_profile_v2_1(unweighted_selection(members))
        weight_sum = float(
            members.get(
                PREFERENCE_STRENGTH_COLUMN,
                pd.Series(DEFAULT_PREFERENCE_STRENGTH, index=members.index),
            ).sum()
        )
        highlights = []
        for layer in LAYERS:
            for item in prominent_numeric_features(profile[layer], limit=2):
                if item["coverage"] >= 0.7:
                    highlights.append(item)
        highlights.sort(key=lambda item: -abs(item["value"] - 3) * item["coverage"])
        branches.append(
            {
                "branch_id": f"B{index:02d}",
                "name": _branch_name(profile),
                "character_ids": list(group),
                "character_names": [names[item] for item in group],
                "selected_count": len(group),
                "profile": profile,
                "ranking_profile": ranking_profile,
                "summary": generate_preview_summary(profile),
                "labels": generate_xp_labels_v2_1(profile),
                "numeric_highlights": highlights[:3],
                "tag_highlights": [item["tag"] for layer in LAYERS for item in supported_tags(profile[layer], 2)][:4],
                "confidence": branch_confidence(profile, len(group)),
                "preference_weight_sum": round(weight_sum, 4),
                "branch_importance": round(
                    weight_sum * branch_confidence(profile, len(group)), 4
                ),
            }
        )
    for branch, label in zip(
        branches,
        generate_distinctive_branch_labels(
            selected, branches, global_profile, core_name
        ),
    ):
        branch.update(label)
    sub_detection = detect_core_sub_branches(selected, selection)
    sub_branches = []
    if sub_detection["detected"]:
        for index, group in enumerate(sub_detection["partition"], start=1):
            members = selected[selected["character_id"].isin(group)]
            profile = build_xp_profile_v2_1(members)
            ranking_profile = build_xp_profile_v2_1(
                unweighted_selection(members)
            )
            weight_sum = float(
                members.get(
                    PREFERENCE_STRENGTH_COLUMN,
                    pd.Series(DEFAULT_PREFERENCE_STRENGTH, index=members.index),
                ).sum()
            )
            highlights = [
                item for layer in LAYERS
                for item in prominent_numeric_features(profile[layer], limit=2)
                if item["coverage"] >= 0.7
            ]
            highlights.sort(
                key=lambda item: -abs(item["value"] - 3) * item["coverage"]
            )
            sub_branches.append({
                "branch_id": f"S{index:02d}",
                "name": _sub_branch_name(profile),
                "character_ids": list(group),
                "character_names": [names[item] for item in group],
                "selected_count": len(group),
                "profile": profile,
                "ranking_profile": ranking_profile,
                "summary": generate_preview_summary(profile),
                "numeric_highlights": highlights[:3],
                "confidence": branch_confidence(profile, len(group)),
                "is_hidden_preference": len(group) == 1,
                "preference_weight_sum": round(weight_sum, 4),
                "branch_importance": round(
                    weight_sum * branch_confidence(profile, len(group)), 4
                ),
            })
        for branch, label in zip(
            sub_branches,
            generate_distinctive_branch_labels(
                selected, sub_branches, global_profile, core_name
            ),
        ):
            branch.update(label)
    return {
        "global_profile": global_profile,
        "ranking_global_profile": ranking_global_profile,
        "unweighted_global_profile": ranking_global_profile,
        "branches": branches,
        "partition": selection,
        "core": {
            "name": core_name,
            "profile": global_profile,
            "summary": generate_preview_summary(global_profile),
        },
        "sub_branch_detection": sub_detection,
        "sub_branches": sub_branches,
    }


def recommend_multi_branch(
    characters: pd.DataFrame,
    multi_profile: Mapping[str, object],
    selected_character_ids: Sequence[str],
    top_n: int = 5,
) -> pd.DataFrame:
    global_results = recommend_characters_v2_1(
        characters,
        multi_profile.get("ranking_global_profile", multi_profile["global_profile"]),
        selected_character_ids,
        top_n=len(characters), sort_by="coverage_adjusted"
    ).set_index("character_id", drop=False)
    branch_results = []
    for branch in multi_profile["branches"]:
        results = recommend_characters_v2_1(
            characters, branch.get("ranking_profile", branch["profile"]), selected_character_ids,
            top_n=len(characters), sort_by="coverage_adjusted"
        ).set_index("character_id", drop=False)
        branch_results.append((branch, results))

    output = []
    for character_id, global_row in global_results.iterrows():
        scores = []
        for branch, results in branch_results:
            row = results.loc[character_id]
            raw_branch = float(row["coverage_adjusted_final_score_raw"])
            confidence = float(branch["confidence"])
            confidence_adjusted = NEUTRAL_MATCH_SCORE + confidence * (raw_branch - NEUTRAL_MATCH_SCORE)
            scores.append((confidence_adjusted, raw_branch, branch, row))
        best_adjusted, best_raw, best_branch, best_row = max(scores, key=lambda item: item[0])
        global_score = float(global_row["coverage_adjusted_final_score_raw"])
        final = BRANCH_MATCH_WEIGHT * best_adjusted + GLOBAL_MATCH_WEIGHT * global_score
        branch_score_map = {item[2]["branch_id"]: round(item[1], 2) for item in scores}
        is_branch_hit = best_raw >= BRANCH_HIT_HIGH and global_score < GLOBAL_HIT_GENERAL
        highlights = [item["display_name"] for item in best_row["numeric_highlights"][:3]]
        detail = "、".join(highlights) if highlights else "四层特征"
        if is_branch_hit:
            reason = f"他不一定符合你所有类型，但精准踩中了「{best_branch['name']}」，主要匹配在{detail}。"
        else:
            reason = f"他与你的「{best_branch['name']}」最接近，主要匹配在{detail}，同时保留整体 XP 的约束。"
        row = global_row.to_dict()
        row.update({
            "global_adjusted_score": round(global_score, 2),
            "branch_adjusted_scores": branch_score_map,
            "best_branch_score": round(best_raw, 2),
            "best_branch_confidence_adjusted_score": round(best_adjusted, 2),
            "best_branch_name": best_branch["name"],
            "best_branch_id": best_branch["branch_id"],
            "branch_confidence": best_branch["confidence"],
            "multi_branch_score_raw": final,
            "multi_branch_score": round(final),
            "branch_hit": is_branch_hit,
            "multi_branch_reason": reason,
        })
        output.append(row)
    return pd.DataFrame(output).sort_values(
        ["multi_branch_score_raw", "character_id"], ascending=[False, True]
    ).head(top_n).reset_index(drop=True)


def recommend_branch_aware(
    characters: pd.DataFrame,
    multi_profile: Mapping[str, object],
    selected_character_ids: Sequence[str],
    top_n: int = 5,
) -> pd.DataFrame:
    """两阶段排序：Core 检索，随后只让多人支线提供受限 bonus。"""
    retrieval_size = min(
        len(characters) - len(selected_character_ids),
        max(top_n, top_n * BASE_RETRIEVAL_MULTIPLIER),
    )
    global_results = recommend_characters_v2_1(
        characters,
        multi_profile.get("ranking_global_profile", multi_profile["global_profile"]),
        selected_character_ids,
        top_n=retrieval_size,
        sort_by="coverage_adjusted",
    ).reset_index(drop=True)
    global_results["base_rank"] = global_results.index + 1
    global_results = global_results.set_index("character_id", drop=False)
    old_multi = recommend_multi_branch(
        characters, multi_profile, selected_character_ids, top_n=len(characters)
    ).set_index("character_id", drop=False)

    sub_results = []
    for branch in multi_profile.get("sub_branches", []):
        results = recommend_characters_v2_1(
            characters,
            branch.get("ranking_profile", branch["profile"]),
            selected_character_ids,
            top_n=len(characters),
            sort_by="coverage_adjusted",
        ).set_index("character_id", drop=False)
        sub_results.append((branch, results))

    output = []
    for character_id, global_row in global_results.iterrows():
        core_score = float(global_row["coverage_adjusted_final_score_raw"])
        row = old_multi.loc[character_id].to_dict()
        if not sub_results:
            row.update({
                "core_adjusted_score": round(core_score, 2),
                "base_score": round(core_score, 2),
                "base_rank": int(global_row["base_rank"]),
                "sub_branch_scores": {},
                "best_sub_branch_score": None,
                "best_sub_branch_signal": None,
                "best_sub_branch_name": None,
                "best_sub_branch_confidence": None,
                "best_sub_branch_is_singleton": False,
                "branch_support_count": 0,
                "rerank_bonus": 0.0,
                "branch_aware_score_raw": core_score,
                "branch_aware_score": round(core_score),
                "recommendation_type": "综合高匹配" if core_score >= COMPREHENSIVE_MATCH_MIN else "探索推荐",
                "branch_aware_reason": global_row["recommendation_reason"],
            })
            output.append(row)
            continue

        signals = []
        for branch, results in sub_results:
            result = results.loc[character_id]
            match = float(result["coverage_adjusted_final_score_raw"])
            confidence = float(branch["confidence"])
            # 向 50 中性值收缩；低 confidence 不是 mismatch。
            signal = NEUTRAL_MATCH_SCORE + confidence * (match - NEUTRAL_MATCH_SCORE)
            signals.append((signal, match, branch, result))
        best_signal, best_match, best_branch, best_result = max(
            signals, key=lambda item: item[1]
        )

        # Singleton 只解释，不加分。多人支线只奖励高于 Core 的部分。
        eligible_bonuses = []
        for signal, match, branch, result in signals:
            if branch["selected_count"] < 2:
                continue
            advantage = max(0.0, match - core_score)
            proposed = advantage * float(branch["confidence"]) * BRANCH_RERANK_STRENGTH
            cap = core_score * MAX_BRANCH_BONUS_RATIO
            eligible_bonuses.append((min(proposed, cap), branch))
        rerank_bonus, rerank_branch = (
            max(eligible_bonuses, key=lambda item: item[0])
            if eligible_bonuses
            else (0.0, None)
        )
        final = core_score + rerank_bonus

        if core_score >= COMPREHENSIVE_MATCH_MIN:
            recommendation_type = "综合高匹配"
        elif best_match >= BRANCH_HIT_RAW_MIN and best_match - core_score >= BRANCH_HIT_RAW_MARGIN:
            recommendation_type = "支线命中"
        else:
            recommendation_type = "探索推荐"

        numeric = best_result["numeric_highlights"][:3]
        numeric_text = "、".join(item["display_name"] for item in numeric)
        tags = [item["tag"] for item in best_result["tag_highlights"][:2]]
        evidence = numeric_text or "四层数值"
        if tags:
            evidence += f"，并与你常见的「{'、'.join(tags)}」属性重合"
        if best_branch["selected_count"] == 1:
            reason = (
                f"他额外命中了你的隐藏 XP「{best_branch['name']}」，主要体现在"
                f"{evidence}。该支线目前只有单角色证据，不参与排名加分。"
            )
        elif recommendation_type == "支线命中":
            reason = (
                f"他未必符合你所有偏好的平均值，但较精准地命中了你的"
                f"「{best_branch['name']}」支线，主要体现在{evidence}。"
            )
        elif recommendation_type == "综合高匹配":
            reason = (
                f"他与整体核心及「{best_branch['name']}」支线都较接近，"
                f"主要匹配在{evidence}。"
            )
        else:
            reason = (
                f"当前没有非常强的整体命中；在现有候选中，他与"
                f"「{best_branch['name']}」相对接近，参考特征为{evidence}。"
            )
        row.update({
            "core_adjusted_score": round(core_score, 2),
            "base_score": round(core_score, 2),
            "base_rank": int(global_row["base_rank"]),
            "sub_branch_scores": {
                item[2]["branch_id"]: {
                    "match": round(item[1], 2),
                    "confidence_adjusted_signal": round(item[0], 2),
                }
                for item in signals
            },
            "best_sub_branch_score": round(best_match, 2),
            "best_sub_branch_signal": round(best_signal, 2),
            "best_sub_branch_name": best_branch["name"],
            "best_sub_branch_confidence": best_branch["confidence"],
            "best_sub_branch_is_singleton": best_branch["is_hidden_preference"],
            "branch_support_count": best_branch["selected_count"],
            "rerank_bonus": round(rerank_bonus, 4),
            "rerank_branch_name": rerank_branch["name"] if rerank_branch else None,
            "branch_aware_score_raw": final,
            "branch_aware_score": round(final),
            "recommendation_type": recommendation_type,
            "branch_aware_reason": reason,
        })
        output.append(row)

    ranked = pd.DataFrame(output).sort_values(
        ["branch_aware_score_raw", "character_id"], ascending=[False, True]
    ).reset_index(drop=True)
    ranked["final_rank"] = ranked.index + 1
    return ranked.head(top_n).reset_index(drop=True)


def calculate_gated_rescue(
    core_score: float,
    branch_score: float | None,
    branch_confidence_value: float | None,
    branch_member_count: int,
    selected_total: int,
    confidence_threshold: float = GATED_RESCUE_CONFIDENCE_THRESHOLD,
    rescue_lambda: float = GATED_RESCUE_LAMBDA,
) -> Dict[str, float | bool]:
    """计算单个候选的 v2.6 rescue；singleton 和低信心分支不加分。"""
    support_ratio = (
        branch_member_count / selected_total
        if branch_member_count > 0 and selected_total > 0
        else 0.0
    )
    confidence = float(branch_confidence_value or 0.0)
    eligible = (
        branch_score is not None
        and branch_member_count >= 2
        and selected_total > 0
        and confidence >= confidence_threshold
    )
    advantage = max(0.0, float(branch_score) - core_score) if eligible else 0.0
    support_factor = sqrt(support_ratio) if eligible else 0.0
    branch_gate = confidence * support_factor if eligible else 0.0
    rescue_bonus = max(0.0, rescue_lambda * branch_gate * advantage)
    return {
        "core_score": core_score,
        "eligible": eligible,
        "support_ratio": support_ratio,
        "support_factor": support_factor,
        "branch_gate": branch_gate,
        "branch_advantage": advantage,
        "rescue_bonus": rescue_bonus,
        "final_score": core_score + rescue_bonus,
    }


def recommend_branch_aware_gated_rescue(
    characters: pd.DataFrame,
    multi_profile: Mapping[str, object],
    selected_character_ids: Sequence[str],
    top_n: int = 5,
) -> pd.DataFrame:
    """按 v2.6 Gated Rescue 排序，同时保留 legacy 函数供 A/B。"""
    selected_total = len(selected_character_ids)
    global_results = recommend_characters_v2_1(
        characters,
        multi_profile.get("ranking_global_profile", multi_profile["global_profile"]),
        selected_character_ids,
        top_n=len(characters),
        sort_by="coverage_adjusted",
    ).reset_index(drop=True)
    global_results["base_rank"] = global_results.index + 1
    global_results = global_results.set_index("character_id", drop=False)

    branch_results = []
    for branch in multi_profile.get("branches", []):
        results = recommend_characters_v2_1(
            characters,
            branch.get("ranking_profile", branch["profile"]),
            selected_character_ids,
            top_n=len(characters),
            sort_by="coverage_adjusted",
        ).set_index("character_id", drop=False)
        branch_results.append((branch, results))

    # 解释数据继续复用 legacy 输出；其分数不参与 v2.6 排名。
    legacy = recommend_branch_aware(
        characters, multi_profile, selected_character_ids, top_n=len(characters)
    ).set_index("character_id", drop=False)
    output = []
    for character_id, core_row in global_results.iterrows():
        core_score = float(core_row["coverage_adjusted_final_score_raw"])
        eligible_scores = []
        for branch, results in branch_results:
            if (
                int(branch["selected_count"]) < 2
                or float(branch["confidence"])
                < GATED_RESCUE_CONFIDENCE_THRESHOLD
            ):
                continue
            score = float(
                results.loc[character_id, "coverage_adjusted_final_score_raw"]
            )
            eligible_scores.append((score, branch))

        best_score, best_branch = (
            max(eligible_scores, key=lambda item: item[0])
            if eligible_scores
            else (None, None)
        )
        rescue = calculate_gated_rescue(
            core_score=core_score,
            branch_score=best_score,
            branch_confidence_value=(
                float(best_branch["confidence"]) if best_branch else None
            ),
            branch_member_count=(
                int(best_branch["selected_count"]) if best_branch else 0
            ),
            selected_total=selected_total,
        )
        branch_rescued = rescue["rescue_bonus"] > 0
        row = legacy.loc[character_id].to_dict()
        row.update({
            "core_score": core_score,
            "core_adjusted_score": round(core_score, 2),
            "base_score": round(core_score, 2),
            "base_rank": int(core_row["base_rank"]),
            "best_multi_branch_score": best_score,
            "branch_confidence": (
                float(best_branch["confidence"]) if best_branch else None
            ),
            "branch_member_count": (
                int(best_branch["selected_count"]) if best_branch else 0
            ),
            "support_ratio": rescue["support_ratio"],
            "branch_advantage": rescue["branch_advantage"],
            "branch_gate": rescue["branch_gate"],
            "rescue_bonus": rescue["rescue_bonus"],
            "final_score": rescue["final_score"],
            "branch_rescued": branch_rescued,
            "matched_branch_name": best_branch["name"] if branch_rescued else None,
            # UI 继续显示原有 Core 契合度；融合 final_score 只负责排序。
            "branch_aware_score": round(core_score),
            "branch_aware_score_raw": rescue["final_score"],
        })
        if branch_rescued:
            row["branch_aware_reason"] = (
                f"特别命中你的「{best_branch['name']}」支线。"
                + str(row["branch_aware_reason"])
            )
        output.append(row)

    ranked = pd.DataFrame(output).sort_values(
        ["final_score", "character_id"], ascending=[False, True]
    ).reset_index(drop=True)
    ranked["final_rank"] = ranked.index + 1
    return ranked.head(top_n).reset_index(drop=True)
