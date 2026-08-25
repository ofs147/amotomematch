from pathlib import Path

from utils.tag_recommender_v6 import (
    CharacterTags,
    HeartSignal,
    build_fallback_result,
    build_heart_signals,
    compute_idf,
    ensure_unique_signal_titles,
    load_tag_characters,
    retrieve_candidates,
    select_diverse_heart_signals,
)

ROOT = Path(__file__).resolve().parents[1]


def _characters():
    return load_tag_characters(
        ROOT / "data" / "core_xp_tags_v6.csv",
        ROOT / "data" / "core_xp_tags_v6_2_review.csv",
    )


def test_production_pool_and_retrieval_are_tag_only():
    characters = _characters()
    selected = characters[:5]
    result = build_fallback_result(selected, characters)
    assert len(characters) == 478
    assert len(result.debug["retrieved"]) == 20
    assert not ({item.character_id for item in selected} & {item["character_id"] for item in result.debug["retrieved"]})
    selected_games = {item.game_title for item in selected}
    assert not (selected_games & {item["game_title"] for item in result.debug["retrieved"]})
    assert not (
        selected_games
        & {item.game_title for item in [*result.high_matches, *result.explorations]}
    )


def test_existing_chinese_display_name_mapping_is_applied():
    characters = {item.character_id: item for item in _characters()}
    assert characters["C044"].character_name == "天草四郎时贞"
    assert characters["C092"].character_name == "亨利·兰伯特"
    assert characters["C077"].character_name == "五月女光基"
    assert characters["C011"].game_title == "冷然之天秤"
    assert characters["C026"].game_title == "共鸣之吻"
    assert characters["C077"].game_title == "共鸣之吻"
    assert characters["C014"].game_title == "Code:Realize"
    code_realize = [
        item for item in characters.values()
        if item.game_title == "Code:Realize"
    ]
    assert len(code_realize) == 5
    assert {item.character_name for item in code_realize} == {
        "因倍·巴比康",
        "维克多·弗兰肯斯坦",
        "圣·日耳曼",
        "亚伯拉罕·凡赫辛",
        "亚森·鲁邦",
    }
    amnesia = [item for item in characters.values() if item.game_title == "失忆症"]
    assert len(amnesia) == 5
    assert {item.character_name for item in amnesia} == {"Shin", "Toma", "Ukyo", "Ikki", "Kent"}
    hyakka = [item for item in characters.values() if item.game_title == "百花百狼 ～战国忍法帖～"]
    assert {item.character_name for item in hyakka} == {
        "月下丸", "黑雪", "百地蝶治郎", "石川五右卫门", "服部半藏",
    }
    mistonia = [item for item in characters.values() if item.game_title == "米斯托尼亚的翅望"]
    assert {item.character_name for item in mistonia} == {
        "阿尔弗雷德·克雷斯韦尔", "卢卡斯·沙利文", "亚斯科特·林德尔",
        "约翰", "莱纳斯·沃德", "爱德华·伯恩斯坦",
    }
    hana_awase = [item for item in characters.values() if item.game_title == "花合朔"]
    assert {item.character_name for item in hana_awase} == {
        "姬空木", "蛟", "唐红", "宇津都", "伊吕波",
    }
    angelique = [
        item for item in characters.values()
        if item.game_title == "安琪莉可 Luminarise"
    ]
    assert {item.character_name for item in angelique} == {
        "犹月", "诺亚", "维吉尔", "奏太", "舒里",
        "米兰", "杰诺", "菲利克斯", "罗伦佐",
    }
    brothers_conflict = [
        item for item in characters.values() if item.game_title == "兄弟战争"
    ]
    assert {item.character_name for item in brothers_conflict} == {
        "朝日奈雅臣", "朝日奈右京", "朝日奈要", "朝日奈光", "朝日奈椿",
        "朝日奈梓", "朝日奈枣", "朝日奈琉生", "朝日奈昴", "朝日奈祈织",
        "朝日奈侑介", "朝日奈风斗", "朝日奈弥",
    }
    klap = [item for item in characters.values() if item.game_title == "KLAP!!"]
    assert {item.character_name for item in klap} == {
        "美作灯真", "周防壮介", "骏河明人",
        "卡米尔·赛谢林", "播磨奏", "出云紫苑",
    }
    unlogical = [
        item for item in characters.values() if item.game_title == "UN:LOGICAL"
    ]
    assert {item.character_name for item in unlogical} == {
        "雅火", "宗像戒", "永守蓝", "弥坂奏壹", "尤里",
    }


def test_same_series_entries_are_grouped_under_the_main_title():
    characters = _characters()
    expected_series_sizes = {
        "冷然之天秤": 6,
        "大正×对称爱丽丝": 7,
        "幸运之杖": 7,
        "CLOCK ZERO": 6,
        "花合朔": 5,
        "薄樱鬼": 12,
        "七罪绯红": 5,
        "毘卢遮那战姬": 9,
        "虔诚之花的晚钟": 6,
        "百密一疏少女心": 4,
        "终远的威尔修": 6,
        "魔鬼恋人": 10,
        "共生丘比特": 7,
        "共鸣之吻": 7,
        "三国恋战记": 10,
    }
    for title, expected_size in expected_series_sizes.items():
        assert sum(item.game_title == title for item in characters) == expected_size
    assert {
        item.character_name for item in characters if item.game_title == "三国恋战记"
    } == {"刘玄德", "关云长", "张翼德", "赵子龙", "曹孟德", "荀文若", "孙仲谋", "周公瑾", "诸葛孔明", "早安"}


def test_demo_produces_three_evidence_backed_signals_and_recommendations():
    characters = _characters()
    demo_ids = {"C001", "C004", "C005", "C044", "C077", "C087"}
    selected = [item for item in characters if item.character_id in demo_ids]
    result = build_fallback_result(selected, characters)
    assert len(result.heart_signals) == 3
    assert all(len(signal.supporting_character_ids) >= 2 for signal in result.heart_signals)
    assert len(result.high_matches) == 5
    # Exploration is best-effort: the diversity filters may leave one valid card.
    assert 1 <= len(result.explorations) <= 3
    cards = [*result.high_matches, *result.explorations]
    assert len({item.character_id for item in cards}) == len(cards) >= 6
    assert all(1 <= len(item.familiar_tags) <= 2 for item in result.explorations)
    assert all(1 <= len(item.new_tags) <= 2 for item in result.explorations)


def test_retrieval_limit_is_guarded():
    characters = _characters()
    selected = characters[:3]
    try:
        retrieve_candidates(selected, characters, [], limit=14)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected invalid retrieval limit to fail")


def _signal(signal_id, tags, supporters, title="同一个标题"):
    return HeartSignal(signal_id, title, tags, supporters, {}, "解释")


def test_three_distinct_signals_survive_diversity_filter():
    candidates = [
        (_signal("danger", ["危险系", "疯感", "高拉扯"], ["A", "B"]), 10),
        (_signal("steady", ["成熟可靠", "温柔", "稳定恋爱"], ["C", "D"]), 9),
        (_signal("sunny", ["阳光", "热血", "直球主动"], ["E", "F"]), 8),
    ]
    assert len(select_diverse_heart_signals(candidates)) == 3


def test_exact_tag_duplicates_keep_only_stronger_signal():
    candidates = [
        (_signal("strong", ["危险系", "疯感", "高拉扯"], ["A", "B", "C"]), 12),
        (_signal("weak", ["高拉扯", "危险系", "疯感"], ["A", "B"]), 8),
    ]
    result = select_diverse_heart_signals(candidates)
    assert [item.signal_id for item in result] == ["strong"]


def test_same_title_on_distinct_branches_is_made_unique():
    signals = [
        _signal("one", ["危险系", "高拉扯"], ["A", "B"]),
        _signal("two", ["成熟可靠", "稳定恋爱"], ["C", "D"]),
    ]
    result = ensure_unique_signal_titles(signals)
    assert len({item.title for item in result}) == 2
    assert all("再栽一次" not in item.title for item in result)
    assert all("·2" not in item.title for item in result)


def test_repeated_titles_are_rewritten_with_different_semantic_copy():
    signals = [
        _signal("one", ["热血", "阳光"], ["A", "B"]),
        _signal("two", ["热血", "直球主动"], ["C", "D"]),
        _signal("three", ["热血", "少年感"], ["E", "F"]),
    ]

    result = ensure_unique_signal_titles(signals)

    assert len({item.title for item in result}) == 3
    assert all("再栽一次" not in item.title and "这条支线" not in item.title for item in result)


def test_two_belly_black_headlines_are_semantically_deduplicated():
    signals = [
        _signal("one", ["腹黑", "神秘系", "高拉扯"], ["A", "B"], "明知他有心眼，我还是想靠近"),
        _signal("two", ["腹黑", "神秘系", "宿命感"], ["C", "D"], "心眼藏得深，我偏想拆穿"),
    ]

    result = ensure_unique_signal_titles(signals)

    assert result[0].title == "明知他有心眼，我还是想靠近"
    assert result[1].title != "心眼藏得深，我偏想拆穿"
    assert result[1].title == "看不透的那一面，最让我好奇"


def test_fate_signal_wins_close_evidence_and_becomes_primary_tag():
    selected = [
        CharacterTags("A", "甲", "作品", ("宿命感", "温柔", "慢热")),
        CharacterTags("B", "乙", "作品", ("宿命感", "温柔", "治愈系")),
        CharacterTags("C", "丙", "作品", ("阳光", "直球主动", "陪伴成长")),
    ]

    signals = build_heart_signals(selected, compute_idf(selected), maximum=1)

    assert signals[0].tags[0] == "宿命感"
    assert "命中注定" in signals[0].title


def test_high_tag_and_supporter_overlap_is_deduplicated():
    candidates = [
        (_signal("one", ["危险系", "疯感", "高拉扯", "色气"], ["A", "B", "C"]), 12),
        (_signal("two", ["危险系", "疯感", "高拉扯", "腹黑"], ["A", "B", "C"]), 10),
    ]
    assert len(select_diverse_heart_signals(candidates)) == 1


def test_high_tag_overlap_with_different_supporters_may_coexist():
    candidates = [
        (_signal("one", ["危险系", "疯感", "高拉扯", "色气"], ["A", "B"]), 12),
        (_signal("two", ["危险系", "疯感", "高拉扯", "腹黑"], ["C", "D"]), 10),
    ]
    assert len(select_diverse_heart_signals(candidates)) == 2


def test_one_and_two_signal_results_keep_five_plus_three_recommendations():
    characters = _characters()
    by_id = {item.character_id: item for item in characters}
    one_signal = build_fallback_result([by_id[item] for item in ("C005", "C087", "C001")], characters)
    two_signals = build_fallback_result([by_id[item] for item in ("C005", "C087", "C001", "C077", "C004")], characters)
    assert len(one_signal.heart_signals) == 1
    assert len(two_signals.heart_signals) == 2
    assert (len(one_signal.high_matches), len(one_signal.explorations)) == (5, 3)
    assert (len(two_signals.high_matches), len(two_signals.explorations)) == (5, 3)
