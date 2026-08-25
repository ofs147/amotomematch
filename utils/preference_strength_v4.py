"""Centralized preference-strength configuration for AOMatch v4.0."""

from __future__ import annotations

from typing import Mapping

import pandas as pd


PREFERENCE_STRENGTH_COLUMN = "preference_strength"
PREFERENCE_STRENGTHS = {
    "本命 / 非常喜欢": 1.3,
    "很喜欢": 1.0,
    "有好感": 0.7,
}
DEFAULT_PREFERENCE_STRENGTH = 1.0
MIN_SELECTED_CHARACTERS = 3
MAX_SELECTED_CHARACTERS = 10
RECOMMENDED_SELECTION_RANGE = (5, 8)


def validate_selection_count(count: int) -> None:
    if not MIN_SELECTED_CHARACTERS <= count <= MAX_SELECTED_CHARACTERS:
        raise ValueError("请选择 3～10 位喜欢的角色")


def profile_stage_label(count: int) -> str:
    validate_selection_count(count)
    return "初步画像" if count <= 4 else "完整画像"


def preference_strength_value(value: object) -> float:
    """Normalize labels, numeric values and legacy missing values."""
    if value is None or (not isinstance(value, str) and pd.isna(value)):
        return DEFAULT_PREFERENCE_STRENGTH
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return DEFAULT_PREFERENCE_STRENGTH
        if stripped in PREFERENCE_STRENGTHS:
            return PREFERENCE_STRENGTHS[stripped]
        value = stripped
    numeric = float(value)
    if numeric not in PREFERENCE_STRENGTHS.values():
        raise ValueError(f"unsupported preference strength: {value}")
    return numeric


def apply_preference_strengths(
    selected: pd.DataFrame,
    strengths_by_id: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    """Return a copy carrying one normalized weight per selected character."""
    output = selected.copy()
    mapping = strengths_by_id or {}
    output[PREFERENCE_STRENGTH_COLUMN] = [
        preference_strength_value(mapping.get(str(character_id)))
        for character_id in output["character_id"]
    ]
    return output


def unweighted_selection(selected: pd.DataFrame) -> pd.DataFrame:
    """Remove weights for frozen recommendation/ranking calculations."""
    return selected.drop(columns=[PREFERENCE_STRENGTH_COLUMN], errors="ignore")
