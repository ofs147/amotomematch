"""Character Database v2 的通用数值与标签工具。"""

import math
from typing import Optional, Set, Union


NumericInput = Union[int, float, str, None]


def parse_tags(value: object) -> Set[str]:
    """将半角分号分隔的标签解析为集合；空值返回空集合。"""
    if value is None:
        return set()
    if isinstance(value, float) and math.isnan(value):
        return set()

    text = str(value).strip()
    if not text or text.upper() == "NA":
        return set()
    return {tag.strip() for tag in text.split(";") if tag.strip()}


def normalize_numeric_score(value: NumericInput) -> Optional[float]:
    """把 1～5 转换为 0～1；缺失值保持 None，绝不自动填成 3。"""
    if value is None:
        return None
    text = str(value).strip().upper()
    if not text or text in {"NA", "<NA>", "NAN"}:
        return None

    score = float(value)
    if math.isnan(score):
        return None
    if not 1 <= score <= 5:
        raise ValueError(f"Numeric score 必须在 1～5，收到：{value}")
    return (score - 1) / 4


def tag_similarity(left: object, right: object) -> float:
    """计算同一 Tag Field 内的 Jaccard similarity。

    调用方必须保证两边来自同一个字段，例如 personality_tags 只能与
    personality_tags 比较。两边都为空时没有匹配证据，返回 0.0。
    """
    left_tags = parse_tags(left)
    right_tags = parse_tags(right)
    union = left_tags | right_tags
    if not union:
        return 0.0
    return len(left_tags & right_tags) / len(union)
