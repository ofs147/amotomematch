"""Offline-only Tag-first XP migration, profile, and recommendation prototype."""
from __future__ import annotations

import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

NUMERIC_RULES = (
    ("danger_level", ">=", 4, "危险系"), ("mystery_level", ">=", 4, "神秘系"),
    ("gap_moe", ">=", 4, "反差萌"), ("warmth", ">=", 4, "温柔"),
    ("initiative", ">=", 4, "直球主动"), ("push_pull", ">=", 4, "高拉扯"),
    ("protectiveness", ">=", 4, "强守护"), ("devotion", ">=", 4, "高奉献"),
    ("dependence", ">=", 4, "高依赖"), ("possessiveness", ">=", 4, "强占有"),
    ("jealousy", ">=", 4, "强嫉妒"), ("control", ">=", 4, "控制型"),
    ("emotional_expression", "<=", 2.5, "低表达"),
)

EXISTING_MAP = {
    "阳光": "阳光", "直球": "直球主动", "清冷": "冷感", "温柔": "温柔",
    "毒舌": "毒舌", "腹黑": "腹黑", "笑面虎": "腹黑", "天然": "天然",
    "沉稳": "成熟可靠", "责任感强": "成熟可靠", "可靠系": "成熟可靠",
    "理性": "理性沉稳", "傲娇": "傲娇", "嘴硬心软": "傲娇", "疯批": "疯感",
    "危险系": "危险系", "神秘系": "神秘系", "白切黑": "反差萌",
    "黑切白": "反差萌", "表里不一": "反差萌", "年上": "年上感",
    "爹系": "年上感", "弟系": "少年感", "少年感": "少年感",
    "色气系": "色气", "色气": "色气", "人外": "非人感", "神明": "非人感",
    "妖怪": "非人感", "幽灵": "非人感", "机器人": "非人感",
    "天才": "精英感", "强者": "强者感", "脆弱感": "脆弱感",
    "保护者": "强守护", "忠犬": "高奉献", "纯爱战士": "高奉献",
    "拉扯型": "高拉扯", "慢热": "慢热", "日久生情": "慢热",
    "克制型": "低表达", "焦虑型依恋": "高依赖", "高亲密需求": "高依赖",
    "陪伴型": "陪伴成长", "从朋友到恋人": "陪伴成长", "宿命": "宿命感",
    "灵魂伴侣": "宿命感", "欢喜冤家": "欢喜冤家", "救赎": "救赎感",
    "救赎型": "救赎感", "相爱相杀": "刺激型", "敌对恋爱": "刺激型",
    "禁断感": "刺激型", "安全型恋爱": "稳定恋爱", "成年人恋爱": "稳定恋爱",
    "琴瑟和鸣": "稳定恋爱", "强情绪浓度": "高情绪浓度",
    "并肩作战": "并肩恋爱", "双强": "并肩恋爱", "共犯": "并肩恋爱",
    "唯一例外": "唯一例外", "烂人真心": "唯一例外",
}

TAG_FIELDS = ("visual_vibe_tags", "personality_tags", "age_position_tags",
              "role_fantasy_tags", "relationship_trope_tags", "archetype_tags", "romance_tags")


def split_tags(value: object) -> list[str]:
    return [tag.strip() for tag in str(value or "").split(";") if tag.strip()]


def load_dictionary(path: Path) -> tuple[list[dict[str, str]], dict[str, dict[str, str]]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, {row["canonical_tag"]: row for row in rows}


def candidate_tags(row: Mapping[str, str], dictionary: Mapping[str, Mapping[str, str]]) -> list[dict[str, object]]:
    scores: dict[str, float] = defaultdict(float)
    bases: dict[str, set[str]] = defaultdict(set)
    for field in TAG_FIELDS:
        for old in split_tags(row.get(field)):
            tag = EXISTING_MAP.get(old)
            if tag in dictionary:
                scores[tag] += 3
                bases[tag].add("existing_tag")
    for field, op, threshold, tag in NUMERIC_RULES:
        value = float(row[field])
        if (op == ">=" and value >= threshold) or (op == "<=" and value <= threshold):
            scores[tag] += 2 + abs(value - threshold) * .2
            bases[tag].add("numeric_legacy")
    if float(row["personality_maturity"]) >= 4 and float(row["emotional_stability"]) >= 4:
        scores["成熟可靠"] += 2.5
        bases["成熟可靠"].add("numeric_legacy")
    # Candidate generation is intentionally broader than final selection.
    # Borderline rules fill the reviewer shortlist but stay below the score
    # required by ``select_core_tags``, so they never force a weak third tag.
    soft_rules = (
        ("extroversion", 3.5, "阳光"), ("initiative", 3.5, "直球主动"),
        ("gap_moe", 3.5, "反差萌"), ("push_pull", 3.5, "高拉扯"),
        ("devotion", 3.5, "高奉献"),
    )
    for field, threshold, tag in soft_rules:
        if float(row[field]) >= threshold and tag not in scores:
            scores[tag] = 1.2
            bases[tag].add("numeric_legacy_candidate_only")
    ordered = sorted(scores, key=lambda tag: (-scores[tag], tag))[:6]
    return [{"tag": tag, "score": round(scores[tag], 3), "category": dictionary[tag]["category"],
             "source_basis": "+".join(sorted(bases[tag]))} for tag in ordered]


def select_core_tags(candidates: list[dict[str, object]], limit: int = 3) -> list[dict[str, object]]:
    selected, categories = [], Counter()
    for item in candidates:
        category = str(item["category"])
        adjusted = float(item["score"]) - categories[category] * 1.25
        if adjusted < 2:
            continue
        selected.append(item)
        categories[category] += 1
        if len(selected) == limit:
            break
    return selected


def migrate(rows: Iterable[Mapping[str, str]], dictionary: Mapping[str, Mapping[str, str]]) -> list[dict[str, str]]:
    output = []
    protected = {"柳爱时", "杨", "榎本峰雄", "鴻上滉", "Crius Castlerock"}
    for row in rows:
        candidates = candidate_tags(row, dictionary)
        final = select_core_tags(candidates)
        bases = {part for item in final for part in str(item["source_basis"]).split("+")}
        output.append({
            "character_id": row["character_id"], "name": row["character_name"], "game": row["game"],
            "candidate_tags": ";".join(str(item["tag"]) for item in candidates),
            "final_core_tags": ";".join(str(item["tag"]) for item in final),
            "tag_categories": ";".join(str(item["category"]) for item in final),
            "confidence": "A" if row["character_name"] in protected else "B",
            "source_basis": "combined" if len(bases) > 1 else next(iter(bases), "unresolved"),
        })
    return output


def idf_weights(migrated: list[Mapping[str, str]]) -> dict[str, float]:
    frequency = Counter(tag for row in migrated for tag in split_tags(row["final_core_tags"]))
    n = len(migrated)
    return {tag: math.log((n + 1) / (count + 1)) + 1 for tag, count in frequency.items()}


def build_tag_profile(liked_ids: Iterable[str], migrated: list[Mapping[str, str]]) -> dict[str, object]:
    liked = set(liked_ids)
    selected = [row for row in migrated if row["character_id"] in liked]
    frequencies = Counter(tag for row in selected for tag in split_tags(row["final_core_tags"]))
    weights = idf_weights(migrated)
    core = sorted(frequencies, key=lambda tag: (-frequencies[tag] * weights[tag], tag))[:5]
    pairs = Counter(tuple(sorted(pair)) for row in selected for pair in _pairs(split_tags(row["final_core_tags"])))
    branches = [{"tags": list(pair), "support": support} for pair, support in pairs.most_common(3)]
    secondary = [tag for tag in frequencies if tag not in core]
    return {"core_xp_tags": core, "xp_branches": branches, "secondary_preferences": secondary}


def _pairs(tags: list[str]):
    for i, left in enumerate(tags):
        for right in tags[i + 1:]:
            yield left, right


def recommend(liked_ids: Iterable[str], migrated: list[Mapping[str, str]], top_n: int = 10) -> list[dict[str, object]]:
    liked = set(liked_ids)
    profile = build_tag_profile(liked, migrated)
    desired = set(profile["core_xp_tags"])
    branches = {tuple(item["tags"]) for item in profile["xp_branches"]}
    weights = idf_weights(migrated)
    scored = []
    for row in migrated:
        if row["character_id"] in liked:
            continue
        tags = set(split_tags(row["final_core_tags"]))
        overlap = sum(weights[tag] for tag in tags & desired)
        branch_bonus = sum(1.5 for pair in branches if set(pair) <= tags)
        scored.append({"character_id": row["character_id"], "name": row["name"],
                       "score": round(overlap + branch_bonus, 4),
                       "matched_tags": sorted(tags & desired)})
    return sorted(scored, key=lambda item: (-item["score"], item["character_id"]))[:top_n]


def write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0])
        writer.writeheader(); writer.writerows(rows)


def run(project: Path) -> dict[str, object]:
    dictionary_rows, dictionary = load_dictionary(project / "data" / "core_xp_tag_dictionary_v6.csv")
    with (project / "data" / "characters_v2_candidate.csv").open(encoding="utf-8-sig", newline="") as handle:
        legacy = list(csv.DictReader(handle))
    migrated = migrate(legacy, dictionary)
    write_csv(project / "data" / "core_xp_tags_v6_migration_draft.csv", migrated)
    counts = Counter(tag for row in migrated for tag in split_tags(row["final_core_tags"]))
    stats = {"controlled_tag_count": len(dictionary_rows), "category_distribution": dict(Counter(row["category"] for row in dictionary_rows)),
             "migration": {"characters": len(migrated), "two_tags": sum(len(split_tags(row["final_core_tags"])) == 2 for row in migrated), "three_tags": sum(len(split_tags(row["final_core_tags"])) == 3 for row in migrated), "unresolved": sum(not split_tags(row["final_core_tags"]) for row in migrated)},
             "tag_frequency": dict(counts.most_common()), "production_write": False}
    (project / "data" / "core_xp_tag_stats_v6.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return stats


if __name__ == "__main__":
    root = Path.cwd() if (Path.cwd() / "data").is_dir() else Path(__file__).resolve().parents[1]
    print(json.dumps(run(root), ensure_ascii=False, indent=2))
