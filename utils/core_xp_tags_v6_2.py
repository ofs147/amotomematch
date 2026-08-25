"""Offline review-queue and human-calibration helpers for v6.2."""
from __future__ import annotations

from typing import Iterable, Mapping

from utils.core_xp_tags_v6 import split_tags

ANCHORS = {"柳爱时", "杨", "榎本峰雄", "鴻上滉", "Crius Castlerock"}
GENERIC_TAGS = {"成熟可靠", "温柔", "年上感", "稳定恋爱", "低表达", "并肩恋爱"}
TEMPLATE_COMBINATION = frozenset({"阳光", "热血", "直球主动"})


def review_reasons(row: Mapping[str, str]) -> list[str]:
    tags = split_tags(row.get("final_core_tags"))
    reasons = []
    if row.get("character") in ANCHORS:
        reasons.append("ANCHOR_AWAITING_HUMAN_CONFIRMATION")
    if row.get("composition") != "2_SELF+1_ROMANCE":
        reasons.append("COMPOSITION_EXCEPTION")
    if len(set(tags) & GENERIC_TAGS) >= 2:
        reasons.append("GENERIC_TAG_DOMINANCE")
    if frozenset(tags) == TEMPLATE_COMBINATION:
        reasons.append("TEMPLATE_COMBINATION_CHECK")
    return reasons


def review_status(row: Mapping[str, str]) -> str:
    return "REVIEW_REQUIRED" if review_reasons(row) else "AUTO_MIGRATION_READY"


def apply_reviewer_action(tags: Iterable[str], action: str, note: str,
                          controlled_tags: set[str]) -> tuple[list[str], bool]:
    """Apply one small structured edit; arbitrary prose remains for human handling."""
    result = list(tags)
    normalized = action.strip().upper()
    if normalized in {"", "KEEP", "KEEP ALL"}:
        return result, normalized in {"KEEP", "KEEP ALL"}
    if normalized == "REMOVE":
        if note not in result:
            raise ValueError("REMOVE target is not a current tag")
        result.remove(note)
    elif normalized == "ADD":
        if note not in controlled_tags:
            raise ValueError("ADD target is not controlled")
        if note not in result:
            result.append(note)
    elif normalized == "REPLACE":
        separator = "→" if "→" in note else "->"
        if separator not in note:
            raise ValueError("REPLACE note must be old → new")
        old, new = (part.strip() for part in note.split(separator, 1))
        if old not in result or new not in controlled_tags:
            raise ValueError("invalid REPLACE tags")
        result[result.index(old)] = new
    else:
        raise ValueError("unsupported review action")
    if not 2 <= len(result) <= 3 or len(set(result)) != len(result):
        raise ValueError("review result must contain 2–3 unique tags")
    return result, True


def future_annotation_status(candidate_count: int, final_tags: Iterable[str],
                             self_count: int, romance_count: int,
                             ambiguous_slots: int) -> str:
    tags = list(final_tags)
    if candidate_count < 4 or len(tags) < 2:
        return "INSUFFICIENT_EVIDENCE"
    if ambiguous_slots == 0 and len(tags) in {2, 3} and self_count >= 1 and romance_count >= 1:
        return "AUTO_PASS"
    return "REVIEW_REQUIRED"
