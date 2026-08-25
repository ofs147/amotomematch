from pathlib import Path

import pytest
from PIL import Image
from io import BytesIO

from utils.aoprofile_v1 import (
    CARD_SIZE, build_profile_data, render_profile_png,
    representative_xp_tags, serialize_profile,
)
from utils.tag_recommender_v6 import load_tag_characters

ROOT = Path(__file__).resolve().parents[1]


def selected():
    return load_tag_characters(
        ROOT / "data" / "core_xp_tags_v6.csv",
        ROOT / "data" / "core_xp_tags_v6_2_review.csv",
    )[:6]


def test_xp_and_display_names_are_inherited():
    items = selected()
    tags = representative_xp_tags(items)
    assert 4 <= len(tags) <= 6
    assert all(item.character_name for item in items)


def test_limits_for_games_and_oshi():
    with pytest.raises(ValueError):
        build_profile_data("aoko", "", [str(i) for i in range(7)], ["温柔"], ["柳爱时"], "", "")
    with pytest.raises(ValueError):
        build_profile_data("aoko", "", ["作品"], ["温柔"], [str(i) for i in range(11)], "", "")


def test_empty_optional_fields_and_serialization():
    profile = build_profile_data("aoko", "", ["作品"], ["温柔", "慢热"], ["柳爱时"], "", "")
    payload = serialize_profile(profile)
    assert payload["contact"] == ""
    assert payload["turn_offs"] == ""
    assert payload["note"] == ""


def test_png_export_without_avatar_is_portrait():
    profile = build_profile_data("aoko", "", ["作品"], ["温柔", "慢热"], ["柳爱时"], "", "")
    png = render_profile_png(profile)
    image = Image.open(BytesIO(png))
    assert image.format == "PNG"
    assert image.size == CARD_SIZE
    assert image.getpixel((0, 0)) == (255, 247, 251)
    assert image.getpixel((540, 365)) == (255, 253, 253)


def test_profile_editor_has_explicit_share_image_action():
    source = (ROOT / "utils" / "aoprofile_ui.py").read_text(encoding="utf-8")
    assert "生成 AOProfile 分享图 ♡" in source
    assert "保存 AOProfile PNG" in source
    assert "喜欢的作品" in source
    assert "推 / 推し" in source


def test_export_uses_vector_hearts_and_bilingual_section_titles():
    source = (ROOT / "utils" / "aoprofile_v1.py").read_text(encoding="utf-8")
    assert "def _draw_heart" in source
    assert "喜欢的作品" in source
    assert 'draw.text((101, y), "XP"' in source
    assert "推 / 推し" in source
    assert "雷点" in source
    assert "留言板" in source
    assert 'draw.text((70, y), "♡' not in source
    assert 'draw.text((275, 252), "ID"' in source
    assert "def _draw_text_with_heart" in source
    assert 'draw.text((275, 160), "CN / 昵称"' in source
