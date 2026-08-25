"""Offline v6.1 calibration: high-identity 2 SELF + 1 ROMANCE selection."""
from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

from utils.core_xp_tags_v6 import split_tags

SELF_PREFIXES = ("A_", "B_")
ROMANCE_PREFIXES = ("C_", "D_")

SELF_MAP = {
    "阳光": "阳光", "清冷": "冷感", "温柔": "温柔", "毒舌": "毒舌",
    "腹黑": "腹黑", "笑面虎": "腹黑", "天然": "天然", "傲娇": "傲娇",
    "嘴硬心软": "傲娇", "疯批": "疯感", "理性": "理性沉稳",
    "危险系": "危险系", "神秘系": "神秘系", "白切黑": "反差萌",
    "黑切白": "反差萌", "表里不一": "反差萌", "爹系": "年上感",
    "弟系": "少年感", "少年感": "少年感", "色气系": "色气",
    "脆弱感": "脆弱感", "天才": "精英感", "强者": "强者感",
    "热血": "热血", "热血汉": "热血",
}
ROMANCE_MAP = {
    "直球": "直球主动", "拉扯型": "高拉扯", "保护者": "强守护",
    "忠犬": "高奉献", "纯爱战士": "高奉献", "克制型": "低表达",
    "慢热": "慢热", "日久生情": "慢热", "焦虑型依恋": "高依赖",
    "高亲密需求": "高依赖", "陪伴型": "陪伴成长", "从朋友到恋人": "陪伴成长",
    "宿命": "宿命感", "灵魂伴侣": "宿命感", "欢喜冤家": "欢喜冤家",
    "救赎": "救赎感", "救赎型": "救赎感", "相爱相杀": "刺激型",
    "敌对恋爱": "刺激型", "禁断感": "刺激型", "安全型恋爱": "稳定恋爱",
    "成年人恋爱": "稳定恋爱", "琴瑟和鸣": "稳定恋爱",
    "强情绪浓度": "高情绪浓度", "并肩作战": "并肩恋爱", "双强": "并肩恋爱",
    "共犯": "并肩恋爱", "唯一例外": "唯一例外", "烂人真心": "唯一例外",
}
DISTINCTIVENESS = defaultdict(lambda: .78, {
    "成熟可靠": .58, "并肩恋爱": .55, "年上感": .60, "低表达": .68,
    "温柔": .68, "稳定恋爱": .68, "高拉扯": .85, "危险系": .90,
    "疯感": .92, "反差萌": .90, "热血": .90, "毒舌": .88,
    "腹黑": .86, "非人感": .88, "强占有": .90, "控制型": .90,
})

ANCHOR_OVERRIDES = {
    "柳爱时": ("成熟可靠", "温柔", "稳定恋爱"),
    "杨": ("危险系", "疯感", "高拉扯"),
    "榎本峰雄": ("阳光", "热血", "直球主动"),
    "鴻上滉": ("冷感", "神秘系", "慢热"),
    "Crius Castlerock": ("成熟可靠", "腹黑", "高依赖"),
}


def _add(store, tag, evidence, basis):
    current = store.setdefault(tag, {"evidence": 0.0, "basis": set()})
    current["evidence"] = max(current["evidence"], evidence)
    current["basis"].add(basis)


def rank_candidates(row: Mapping[str, str], dictionary: Mapping[str, Mapping[str, str]],
                    prior_frequency: Mapping[str, int]) -> list[dict[str, object]]:
    raw = {}
    all_old = {tag for field in ("visual_vibe_tags", "personality_tags", "age_position_tags",
        "relationship_trope_tags", "archetype_tags", "romance_tags") for tag in split_tags(row.get(field))}
    for old in all_old:
        if old in SELF_MAP:
            _add(raw, SELF_MAP[old], .88, "existing_tag")
        if old in ROMANCE_MAP:
            _add(raw, ROMANCE_MAP[old], .88, "existing_tag")
    if "可靠系" in all_old and ({"沉稳", "责任感强"} & all_old):
        _add(raw, "成熟可靠", .95, "reviewed_identity_pattern")
    if "年上" in all_old and ("爹系" in all_old or float(row["warmth"]) >= 4.5):
        _add(raw, "年上感", .82, "strong_age_appeal")
    if "人外" in all_old or {"神明", "妖怪", "幽灵", "机器人"} & all_old:
        _add(raw, "非人感", .88, "existing_tag")
    # “热血”只接受明确的燃系角色证据。阳光、外向、高表达和行动力的
    # 数值组合仍然过宽，会把认真、可靠或关键时刻肯行动的人误判为热血。
    numeric = (
        ("danger_level", 4.5, "危险系"), ("mystery_level", 4.5, "神秘系"),
        ("gap_moe", 4.5, "反差萌"), ("initiative", 4.5, "直球主动"),
        ("push_pull", 4.5, "高拉扯"), ("protectiveness", 4.5, "强守护"),
        ("devotion", 4.5, "高奉献"), ("dependence", 4.5, "高依赖"),
        ("possessiveness", 4.5, "强占有"), ("jealousy", 4.5, "强嫉妒"),
        ("control", 4.5, "控制型"),
    )
    for field, threshold, tag in numeric:
        if float(row[field]) >= threshold:
            _add(raw, tag, .72, "extreme_numeric_pattern")
    if float(row["emotional_expression"]) <= 2 and "克制型" in all_old:
        _add(raw, "低表达", .85, "low_expression_confirmed")
    n = 90
    ranked = []
    for tag, detail in raw.items():
        if tag not in dictionary:
            continue
        category = dictionary[tag]["category"]
        relevance = .88 if category.startswith(SELF_PREFIXES) else 1.0
        frequency_penalty = min(.08, math.log1p(prior_frequency.get(tag, 0)) * .018)
        redundancy = .08 if tag in {"成熟可靠", "年上感"} and len(raw) > 4 else 0
        score = DISTINCTIVENESS[tag] * detail["evidence"] * relevance - frequency_penalty - redundancy
        ranked.append({"tag": tag, "category": category, "distinctiveness_score": DISTINCTIVENESS[tag],
            "evidence_score": detail["evidence"], "romantic_relevance_score": relevance,
            "redundancy_penalty": redundancy, "frequency_penalty": round(frequency_penalty, 4),
            "final_score": round(score, 4), "source_basis": "+".join(sorted(detail["basis"]))})
    return sorted(ranked, key=lambda item: (-item["final_score"], item["tag"]))[:6]


def select_tags(name: str, candidates: list[dict[str, object]]) -> list[str]:
    if name in ANCHOR_OVERRIDES:
        return list(ANCHOR_OVERRIDES[name])
    self_tags = [item for item in candidates if str(item["category"]).startswith(SELF_PREFIXES)]
    romance = [item for item in candidates if str(item["category"]).startswith(ROMANCE_PREFIXES)]
    selected = [str(item["tag"]) for item in self_tags[:2]]
    if romance:
        selected.append(str(romance[0]["tag"]))
    for item in candidates:
        if len(selected) >= 3:
            break
        if item["tag"] not in selected and float(item["final_score"]) >= .5:
            selected.append(str(item["tag"]))
    return selected[:3]


def migrate(rows: Iterable[Mapping[str, str]], dictionary: Mapping[str, Mapping[str, str]],
            prior_frequency: Mapping[str, int]) -> list[dict[str, str]]:
    output = []
    for row in rows:
        candidates = rank_candidates(row, dictionary, prior_frequency)
        final = select_tags(row["character_name"], candidates)
        by_tag = {item["tag"]: item for item in candidates}
        output.append({"character_id": row["character_id"], "character": row["character_name"],
            "game": row["game"], "candidate_tags": ";".join(str(item["tag"]) for item in candidates),
            "candidate_ranking": "|".join(f"{item['tag']}:{item['final_score']}" for item in candidates),
            "final_core_tags": ";".join(final),
            "composition": f"{sum(dictionary[tag]['category'].startswith(SELF_PREFIXES) for tag in final)}_SELF+{sum(dictionary[tag]['category'].startswith(ROMANCE_PREFIXES) for tag in final)}_ROMANCE",
            "confidence": "A" if row["character_name"] in ANCHOR_OVERRIDES else "B",
            "source_basis": "combined" if any("existing" in str(by_tag.get(tag, {}).get("source_basis", "")) for tag in final) else "numeric_legacy"})
    return output


def combination_stats(rows: Iterable[Mapping[str, str]]) -> dict[str, object]:
    rows = list(rows)
    combinations = Counter(";".join(sorted(split_tags(row["final_core_tags"]))) for row in rows)
    frequencies = Counter(tag for row in rows for tag in split_tags(row["final_core_tags"]))
    entropy = []
    total = sum(frequencies.values())
    for row in rows:
        entropy.append(sum(-frequencies[tag] / total * math.log2(frequencies[tag] / total) for tag in split_tags(row["final_core_tags"])))
    duplicate = {combo: count for combo, count in combinations.items() if count > 1}
    return {"tag_frequency": dict(frequencies.most_common()), "unique_tag_combinations": len(combinations),
        "exact_duplicate_combinations": len(duplicate), "largest_duplicate_count": max(combinations.values()),
        "largest_duplicate_combination": combinations.most_common(1)[0][0],
        "average_tag_entropy": round(sum(entropy) / len(entropy), 4)}
