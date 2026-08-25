from pathlib import Path

from utils.result_ui_v6 import build_result_html
from utils.tag_recommender_v6 import build_fallback_result, load_tag_characters

ROOT = Path(__file__).resolve().parents[1]


def test_result_html_has_responsive_swipe_inline_expansion_and_consistent_cards():
    characters = load_tag_characters(ROOT / "data" / "core_xp_tags_v6.csv", ROOT / "data" / "core_xp_tags_v6_2_review.csv")
    selected = [item for item in characters if item.character_id in {"C001", "C004", "C005", "C044", "C077", "C087"}]
    html = build_result_html(build_fallback_result(selected, characters), selected)
    assert "你的乙游 XP 人格" in html
    assert "这些人，我有预感" in html
    assert "这些人，我有点好奇" in html
    assert "这位，很对劲" not in html
    assert "这位，有点偏，但偏得刚刚好" not in html
    assert ".v6-grid.two {grid-template-columns: repeat(3, minmax(0, 1fr));}" in html
    assert "scroll-snap-type:x mandatory" in html
    assert "<details class=\"v6-heart-card\">" in html
    assert 'class="v6-card pink"' in html
    assert 'class="v6-card blue"' in html
    assert "v6-familiar-label" in html
    assert "v6-new-label" in html


def test_one_and_two_signal_layouts_have_no_empty_placeholder():
    characters = load_tag_characters(ROOT / "data" / "core_xp_tags_v6.csv", ROOT / "data" / "core_xp_tags_v6_2_review.csv")
    by_id = {item.character_id: item for item in characters}
    for ids, expected in [(("C005", "C087", "C001"), 1), (("C005", "C087", "C001", "C077", "C004"), 2)]:
        selected = [by_id[item] for item in ids]
        html = build_result_html(build_fallback_result(selected, characters), selected)
        assert f"signal-count-{expected}" in html
        assert "empty-placeholder" not in html
