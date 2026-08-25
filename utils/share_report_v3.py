"""AOMatch v3.0 spoiler-safe Share Report assembly and PNG rendering。"""

from __future__ import annotations

from io import BytesIO
from pathlib import Path
from typing import Mapping, Sequence

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from utils.preview_v2 import (
    branch_rescue_display,
    candidate_pool_percentile,
    match_level,
)


SPOILER_MARKERS = (
    "spoiler_sensitive",
    "spoiler",
    "隐藏身份",
    "未来身份",
    "剧情真相",
)


class ChineseFontUnavailableError(RuntimeError):
    """Raised instead of silently exporting Chinese text with missing glyphs."""


def is_spoiler_safe_text(value: object) -> bool:
    text = str(value or "")
    folded = text.casefold()
    return bool(text.strip()) and not any(marker in folded for marker in SPOILER_MARKERS)


def _safe_text(value: object, fallback: str | None = None) -> str | None:
    text = str(value or "").strip()
    return text if is_spoiler_safe_text(text) else fallback


def _shorten(text: str, limit: int = 86) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip("，。； ") + "…"


def assemble_share_report(
    hero: Mapping[str, object],
    branch_groups: Mapping[str, Sequence[Mapping[str, object]]],
    recommendations: pd.DataFrame | Sequence[Mapping[str, object]],
    candidate_pool_size: int,
    selected_total: int,
    flexible_preferences: Sequence[str] | None = None,
) -> dict:
    """Assemble a strict user-visible whitelist; no tags/debug fields are read."""
    preferences = []
    for item in hero.get("representative_preferences", [])[:3]:
        label = _safe_text(item.get("short_label") or item.get("label"))
        if label:
            preferences.append(label)

    branches = []
    # Hidden/singleton branches are deliberately never read into the report.
    for branch in branch_groups.get("primary", [])[:2]:
        if int(branch.get("support_count", 0)) < 2:
            continue
        label = _safe_text(branch.get("label"))
        explanation = _safe_text(branch.get("explanation"))
        if label and explanation:
            branches.append({"label": label, "explanation": _shorten(explanation, 58)})

    rows = (
        recommendations.to_dict("records")
        if isinstance(recommendations, pd.DataFrame)
        else list(recommendations)
    )
    report_recommendations = []
    for row in rows:
        if len(report_recommendations) == 3:
            break
        character_name = _safe_text(row.get("character_name"))
        game = _safe_text(row.get("game"))
        if not character_name or not game:
            continue
        rank = int(row.get("final_rank", len(report_recommendations) + 1))
        percentile = candidate_pool_percentile(rank, candidate_pool_size)
        evidence = float(row.get("coverage_adjusted_match_score", 0.0))
        coverage = float(row.get("overall_data_coverage", 0.0))
        branch = branch_rescue_display(
            bool(row.get("branch_rescued", False)),
            _safe_text(row.get("matched_branch_name")),
            int(row.get("branch_member_count", 0) or 0),
        )
        report_recommendations.append({
            "character_name": character_name,
            "game": game,
            "match_level": match_level(percentile, evidence, coverage),
            "matched_branch": branch,
        })

    title = _safe_text(hero.get("title"), "多面心动型")
    summary = _safe_text(
        hero.get("summary"),
        "你的心动类型比较多元，每一种喜欢都有自己的理由。",
    )
    return {
        "brand": "AOMatch",
        "brand_subtitle": "Otome XP Profile",
        "heading": "你的日乙 XP",
        "core_title": title,
        "summary": _shorten(summary),
        "preferences": preferences,
        "branches": branches,
        "flexible_preferences": [
            text for item in (flexible_preferences or [])[:3]
            if (text := _safe_text(item))
        ],
        "recommendations": report_recommendations,
        "evidence": f"由 {selected_total} 位本命生成",
        "positioning": "偏好结构报告 · 推荐用于探索，不代表一定会喜欢",
    }


def find_cjk_font() -> Path:
    candidates = (
        Path("C:/Windows/Fonts/msyh.ttc"),
        Path("C:/Windows/Fonts/simhei.ttf"),
        Path("C:/Windows/Fonts/simsun.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc"),
        Path("/System/Library/Fonts/PingFang.ttc"),
    )
    for path in candidates:
        if path.is_file():
            return path
    raise ChineseFontUnavailableError(
        "未找到可用于 PNG 导出的中文字体（Microsoft YaHei / SimHei / Noto CJK / PingFang）。"
    )


def _font(path: Path, size: int):
    try:
        return ImageFont.truetype(str(path), size=size)
    except OSError as exc:
        raise ChineseFontUnavailableError(f"无法加载中文字体：{path}") from exc


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    lines = []
    current = ""
    for character in text:
        proposed = current + character
        if current and draw.textbbox((0, 0), proposed, font=font)[2] > max_width:
            lines.append(current)
            current = character
        else:
            current = proposed
    if current:
        lines.append(current)
    return lines or [""]


def render_share_report_png(report: Mapping[str, object], font_path: Path | None = None) -> bytes:
    """Render the same report model shown on-page into a vertical PNG."""
    font_path = font_path or find_cjk_font()
    image = Image.new("RGB", (1080, 1760), "#F7F3F0")
    draw = ImageDraw.Draw(image)
    colors = {
        "ink": "#40363C", "muted": "#786D73", "rose": "#84566A",
        "panel": "#FFFDFC", "line": "#DFD2D7", "accent": "#EEE3EB",
    }
    fonts = {
        "brand": _font(font_path, 34), "small": _font(font_path, 25),
        "heading": _font(font_path, 42), "hero": _font(font_path, 54),
        "body": _font(font_path, 30), "section": _font(font_path, 31),
    }
    x, width, y = 80, 920, 65
    draw.text((x, y), str(report["brand"]), font=fonts["brand"], fill=colors["rose"])
    draw.text((x, y + 45), str(report["brand_subtitle"]), font=fonts["small"], fill=colors["muted"])
    y += 125
    draw.rounded_rectangle((55, y, 1025, y + 345), radius=30, fill=colors["panel"], outline=colors["line"], width=2)
    draw.text((x, y + 35), str(report["heading"]), font=fonts["heading"], fill=colors["ink"])
    hero_lines = _wrap(draw, f"「{report['core_title']}」", fonts["hero"], width)
    hero_y = y + 95
    for line in hero_lines[:2]:
        draw.text((x, hero_y), line, font=fonts["hero"], fill=colors["rose"])
        hero_y += 70
    for line in _wrap(draw, str(report["summary"]), fonts["body"], width)[:3]:
        draw.text((x, hero_y + 8), line, font=fonts["body"], fill=colors["ink"])
        hero_y += 43
    y += 390

    draw.text((x, y), "CORE PREFERENCES", font=fonts["section"], fill=colors["rose"])
    y += 50
    preferences = list(report.get("preferences", [])) or ["心动类型仍在探索中"]
    for preference in preferences[:3]:
        draw.text((x + 8, y), f"♡  {preference}", font=fonts["body"], fill=colors["ink"])
        y += 46
    y += 25

    branches = list(report.get("branches", []))
    if branches:
        draw.text((x, y), "YOUR XP BRANCHES", font=fonts["section"], fill=colors["rose"])
        y += 50
        for index, branch in enumerate(branches[:2], 1):
            draw.text((x + 8, y), f"{index:02d}  {branch['label']}", font=fonts["body"], fill=colors["ink"])
            y += 42
            for line in _wrap(draw, str(branch["explanation"]), fonts["small"], width - 25)[:2]:
                draw.text((x + 58, y), line, font=fonts["small"], fill=colors["muted"])
                y += 35
            y += 12
        y += 15

    flexible = list(report.get("flexible_preferences", []))
    if flexible:
        draw.text((x, y), "FLEXIBLE PREFERENCES", font=fonts["section"], fill=colors["rose"])
        y += 50
        for preference in flexible[:3]:
            draw.text((x + 8, y), f"◇  {preference}", font=fonts["small"], fill=colors["ink"])
            y += 38
        y += 12

    draw.text((x, y), "EXPLORE YOUR XP", font=fonts["section"], fill=colors["rose"])
    y += 52
    recommendations = list(report.get("recommendations", []))
    if not recommendations:
        draw.text((x + 8, y), "更多心动角色正在等待发现", font=fonts["body"], fill=colors["muted"])
        y += 50
    for index, recommendation in enumerate(recommendations[:3], 1):
        line = f"{index}. {recommendation['character_name']} · {recommendation['match_level']}"
        draw.text((x + 8, y), line, font=fonts["body"], fill=colors["ink"])
        y += 40
        draw.text((x + 47, y), str(recommendation["game"]), font=fonts["small"], fill=colors["muted"])
        y += 34
        if recommendation.get("matched_branch"):
            draw.text((x + 47, y), str(recommendation["matched_branch"]), font=fonts["small"], fill=colors["rose"])
            y += 34
        y += 10

    footer_y = 1680
    draw.line((x, footer_y - 25, 1000, footer_y - 25), fill=colors["line"], width=2)
    draw.text((x, footer_y), str(report["evidence"]), font=fonts["small"], fill=colors["muted"])
    if report.get("positioning"):
        draw.text((x, footer_y + 34), str(report["positioning"]), font=fonts["small"], fill=colors["muted"])
    draw.text((790, footer_y), "AOMatch", font=fonts["small"], fill=colors["rose"])
    buffer = BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
