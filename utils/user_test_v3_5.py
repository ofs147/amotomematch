"""Anonymous real-user-test logging and aggregation for AOMatch v3.5."""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Iterable, Mapping, Sequence


SESSION_FIELDS = (
    "tester_id", "session_id", "timestamp", "selected_character_ids",
    "selected_character_names", "preference_strengths", "core_xp_title", "branch_labels",
    "top5_character_ids", "top5_character_names", "ranking_mode",
    "candidate_pool_size",
)
PROFILE_FIELDS = (
    "tester_id", "session_id", "core_xp_rating", "branch_rating",
    "profile_comment",
)
RECOMMENDATION_FIELDS = (
    "tester_id", "session_id", "rank", "character_id", "character_name",
    "title", "match_level", "evidence_score", "candidate_percentile",
    "matched_branch", "relevance_rating", "familiarity", "would_try",
    "false_neighbor_reason", "positive_match_reason", "comment",
)

CSV_SCHEMAS = {
    "sessions.csv": SESSION_FIELDS,
    "profile_feedback.csv": PROFILE_FIELDS,
    "recommendation_feedback.csv": RECOMMENDATION_FIELDS,
}

FAMILIARITIES = (
    "已玩且喜欢", "已玩但不喜欢", "知道角色但没玩", "完全不了解",
)
WOULD_TRY_VALUES = ("yes", "maybe", "no")
FALSE_NEIGHBOR_REASONS = (
    "外貌不吃", "性格不吃", "人设不吃", "恋爱关系模式不吃", "太控制",
    "太依赖", "太危险", "太平淡", "情绪浓度不对", "推荐理由与角色实际不符", "其他",
)
POSITIVE_MATCH_REASONS = (
    "外貌", "性格", "人设", "恋爱关系模式", "命中某条XP支线",
    "推荐理由说得准", "其他",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def next_anonymous_ids(data_dir: Path) -> tuple[str, str]:
    """Create anonymous sequential tester/session IDs without personal data."""
    sessions = read_csv_rows(data_dir / "sessions.csv")
    tester_numbers = []
    for row in sessions:
        value = row.get("tester_id", "")
        if value.startswith("tester_") and value[7:].isdigit():
            tester_numbers.append(int(value[7:]))
    tester_id = f"tester_{max(tester_numbers, default=0) + 1:03d}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return tester_id, f"session_{stamp}_{tester_id}"


def read_csv_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def ensure_user_test_files(data_dir: Path) -> None:
    """Create the data directory and all three UTF-8-SIG CSV headers."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for filename, fields in CSV_SCHEMAS.items():
        path = data_dir / filename
        if not path.exists() or path.stat().st_size == 0:
            with path.open("w", encoding="utf-8-sig", newline="") as handle:
                csv.DictWriter(handle, fieldnames=fields).writeheader()
            continue
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            old_fields = tuple(reader.fieldnames or ())
            old_rows = list(reader)
        if old_fields != tuple(fields):
            normalizer = {
                "sessions.csv": _normalize_session,
                "profile_feedback.csv": _normalize_profile,
                "recommendation_feedback.csv": _normalize_recommendation,
            }[filename]
            temporary = path.with_suffix(".csv.tmp")
            with temporary.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(normalizer(row) for row in old_rows)
            temporary.replace(path)


def _append_row(path: Path, fields: Sequence[str], row: Mapping) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({field: row.get(field, "") for field in fields})


def _validate_rating(value: object, field: str, minimum: int, maximum: int) -> int:
    try:
        rating = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} must be an integer") from error
    if not minimum <= rating <= maximum:
        raise ValueError(f"{field} must be between {minimum} and {maximum}")
    return rating


def save_user_test_session(
    data_dir: Path,
    session: Mapping,
    profile_feedback: Mapping,
    recommendation_feedback: Sequence[Mapping],
) -> None:
    """Validate and append one complete session to the three public CSV logs."""
    if not session.get("tester_id") or not session.get("session_id"):
        raise ValueError("tester_id and session_id are required")
    ensure_user_test_files(data_dir)
    existing = read_csv_rows(data_dir / "sessions.csv")
    if any(row["session_id"] == session["session_id"] for row in existing):
        raise ValueError("session_id already saved")

    profile = dict(profile_feedback)
    profile["core_xp_rating"] = _validate_rating(
        profile.get("core_xp_rating"), "core_xp_rating", 1, 5
    )
    profile["branch_rating"] = _validate_rating(
        profile.get("branch_rating"), "branch_rating", 1, 5
    )
    validated = []
    for source in recommendation_feedback:
        row = dict(source)
        row["relevance_rating"] = _validate_rating(
            row.get("relevance_rating"), "relevance_rating", 0, 3
        )
        if row.get("familiarity") not in FAMILIARITIES:
            raise ValueError("invalid familiarity")
        if row.get("would_try") not in WOULD_TRY_VALUES:
            raise ValueError("invalid would_try")
        row["false_neighbor_reason"] = _join_values(
            row.get("false_neighbor_reason", row.get("false_neighbor_reasons", ""))
        )
        row["positive_match_reason"] = _join_values(
            row.get("positive_match_reason", row.get("why_match", ""))
        )
        if row["relevance_rating"] <= 1:
            row["positive_match_reason"] = ""
        else:
            row["false_neighbor_reason"] = ""
        validated.append(row)

    expected_recommendations = len(_split_values(_join_values(
        session.get("top5_character_ids", "")
    )))
    if not 0 <= len(validated) <= 5:
        raise ValueError("recommendation_feedback must contain at most five rows")
    if expected_recommendations and len(validated) != expected_recommendations:
        raise ValueError("recommendation rows must match the saved Top5 snapshot")
    ranks = [int(row.get("rank", 0)) for row in validated]
    if len(ranks) != len(set(ranks)):
        raise ValueError("recommendation ranks must be unique within a session")

    common = {
        "tester_id": session["tester_id"],
        "session_id": session["session_id"],
    }
    session_row = dict(session)
    session_row.setdefault(
        "timestamp",
        session_row.get("completed_at") or session_row.get("started_at") or utc_now(),
    )
    for field in (
        "selected_character_ids", "selected_character_names", "preference_strengths", "branch_labels",
        "top5_character_ids", "top5_character_names",
    ):
        session_row[field] = _join_values(session_row.get(field, ""))
    profile.setdefault(
        "profile_comment", profile.get("least_accurate_text", "")
    )
    _append_row(data_dir / "sessions.csv", SESSION_FIELDS, session_row)
    _append_row(
        data_dir / "profile_feedback.csv", PROFILE_FIELDS, common | profile
    )
    for row in validated:
        _append_row(
            data_dir / "recommendation_feedback.csv",
            RECOMMENDATION_FIELDS,
            common | row,
        )


def export_user_test_zip(data_dir: Path) -> bytes:
    """Return a ZIP containing all three logs, including empty header-only files."""
    ensure_user_test_files(data_dir)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for filename in CSV_SCHEMAS:
            archive.writestr(filename, (data_dir / filename).read_bytes())
    return output.getvalue()


def load_user_test_audit_data(data_dir: Path) -> dict[str, list[dict[str, str]]]:
    """Load v3.5.1 logs using the canonical field names expected by v3.6."""
    ensure_user_test_files(data_dir)
    sessions = [_normalize_session(row) for row in read_csv_rows(data_dir / "sessions.csv")]
    profiles = [_normalize_profile(row) for row in read_csv_rows(data_dir / "profile_feedback.csv")]
    recommendations = [
        _normalize_recommendation(row)
        for row in read_csv_rows(data_dir / "recommendation_feedback.csv")
    ]
    return {
        "sessions": sessions,
        "profile_feedback": profiles,
        "recommendation_feedback": recommendations,
    }


def _normalize_session(row: Mapping[str, str]) -> dict[str, str]:
    normalized = dict(row)
    normalized["timestamp"] = (
        row.get("timestamp") or row.get("completed_at") or row.get("started_at", "")
    )
    if not row.get("preference_strengths"):
        selected_count = len(_split_values(row.get("selected_character_ids", "")))
        normalized["preference_strengths"] = _join_values(
            ["1.0"] * selected_count
        )
    return {field: normalized.get(field, "") for field in SESSION_FIELDS}


def _normalize_profile(row: Mapping[str, str]) -> dict[str, str]:
    normalized = dict(row)
    normalized["profile_comment"] = (
        row.get("profile_comment") or row.get("least_accurate_text", "")
    )
    return {field: normalized.get(field, "") for field in PROFILE_FIELDS}


def _normalize_recommendation(row: Mapping[str, str]) -> dict[str, str]:
    normalized = dict(row)
    normalized["title"] = row.get("title") or row.get("game", "")
    normalized["matched_branch"] = (
        row.get("matched_branch") or row.get("matched_branch_name", "")
    )
    normalized["false_neighbor_reason"] = (
        row.get("false_neighbor_reason") or row.get("false_neighbor_reasons", "")
    )
    normalized["positive_match_reason"] = (
        row.get("positive_match_reason") or row.get("why_match", "")
    )
    normalized["comment"] = (
        row.get("comment") or row.get("false_neighbor_text")
        or row.get("why_match_text", "")
    )
    return {field: normalized.get(field, "") for field in RECOMMENDATION_FIELDS}


def _join_values(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Iterable):
        return " | ".join(str(item) for item in value)
    return str(value or "")


def _split_values(value: str) -> list[str]:
    return [item.strip() for item in value.split("|") if item.strip()]


def familiarity_adjusted_signal(row: Mapping[str, str]) -> tuple[float, float]:
    """Return a 0..3 signal and evidence weight for one recommendation.

    Unknown characters combine first-impression relevance with willingness to try.
    A known dislike is higher-confidence evidence and gets a stronger weight.
    """
    rating = float(row["relevance_rating"])
    familiarity = row["familiarity"]
    if familiarity == "完全不了解":
        try_signal = {"yes": 3.0, "maybe": 1.5, "no": 0.0}[row["would_try"]]
        return (rating + try_signal) / 2.0, 0.75
    if familiarity == "已玩但不喜欢":
        return rating, 1.5
    if familiarity == "已玩且喜欢":
        return rating, 1.25
    return rating, 1.0


def summarize_user_tests(data_dir: Path) -> dict:
    audit_data = load_user_test_audit_data(data_dir)
    profiles = audit_data["profile_feedback"]
    recommendations = audit_data["recommendation_feedback"]
    sessions = audit_data["sessions"]
    false_reasons = Counter(
        reason for row in recommendations
        for reason in _split_values(row.get("false_neighbor_reason", ""))
    )
    positive_reasons = Counter(
        reason for row in recommendations
        for reason in _split_values(row.get("positive_match_reason", ""))
    )
    adjusted = [familiarity_adjusted_signal(row) for row in recommendations]
    adjusted_mean = (
        sum(signal * weight for signal, weight in adjusted)
        / sum(weight for _, weight in adjusted)
        if adjusted else None
    )
    ratings = [int(row["relevance_rating"]) for row in recommendations]
    return {
        "session_count": len(sessions),
        "recommendation_count": len(recommendations),
        "mean_core_xp_rating": _mean_field(profiles, "core_xp_rating"),
        "mean_branch_rating": _mean_field(profiles, "branch_rating"),
        "top5_mean_relevance": mean(ratings) if ratings else None,
        "relevant_at_5": mean(rating >= 2 for rating in ratings) if ratings else None,
        "strong_relevant_at_5": mean(rating == 3 for rating in ratings) if ratings else None,
        "would_try_at_5": mean(
            row["would_try"] in {"yes", "maybe"} for row in recommendations
        ) if recommendations else None,
        "familiarity_adjusted_relevance": adjusted_mean,
        "familiarity_breakdown": dict(Counter(
            row["familiarity"] for row in recommendations
        )),
        "false_neighbor_reasons": dict(false_reasons.most_common()),
        "positive_match_reasons": dict(positive_reasons.most_common()),
        "most_common_false_neighbor_reason": false_reasons.most_common(1),
        "most_common_positive_match_reason": positive_reasons.most_common(1),
    }


def _mean_field(rows: Sequence[Mapping[str, str]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field, "") != ""]
    return mean(values) if values else None


def write_summary(data_dir: Path, output: Path | None = None) -> dict:
    summary = summarize_user_tests(data_dir)
    target = output or data_dir / "summary.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return summary
