from types import SimpleNamespace

from utils.share_card_v6 import build_share_svg


def test_share_card_contains_all_ten_names_and_stays_portable():
    selected = [SimpleNamespace(character_name=f"测试角色{i}") for i in range(1, 11)]
    result = SimpleNamespace(
        heart_signals=[SimpleNamespace(title="温柔而坚定"), SimpleNamespace(title="宿命般的靠近")],
        xp_personality="你容易被温柔、坚定又带有一点距离感的人吸引，也珍惜彼此理解之后自然建立的信任。",
    )

    svg = build_share_svg(result, selected).decode("utf-8")

    assert 'width="1080" height="1440"' in svg
    assert "我的乙游心动讯号" in svg
    assert "<foreignObject" not in svg
    assert svg.count('class="oshi-chip"') == 10
    assert svg.count('y="770"') == 2
    assert svg.count('class="signal" text-anchor="middle"') == 2
    assert '<text x="86" y="730" class="label">心动关键词</text>' in svg
    assert '<rect x="86" y="367" width="440" height="50"' in svg
    assert 'class="summary" text-anchor="middle"' in svg
    assert '.summary{font-size:27px;font-weight:700;fill:#765063}' in svg
    for item in selected:
        assert item.character_name in svg


def test_share_card_escapes_dynamic_text():
    selected = [SimpleNamespace(character_name="A&B <角色>")]
    result = SimpleNamespace(
        heart_signals=[SimpleNamespace(title="甜蜜 & 拉扯")],
        xp_personality="喜欢 <特别> 的人",
    )

    svg = build_share_svg(result, selected).decode("utf-8")

    assert "A&amp;B &lt;角色&gt;" in svg
    assert "甜蜜 &amp; 拉扯" in svg
    assert "喜欢 &lt;特别&gt; 的人" in svg
