"""Centralized user-facing copy for the v6 Tag-first preview."""

XP_PERSONALITY_HEADING = "你的乙游 XP 人格"
HEART_SIGNALS_HEADING = "心动讯号"
HIGH_MATCH_HEADING = "这些人，我有预感"
EXPLORATION_HEADING = "这些人，我有点好奇"

HEART_TITLE_RULES = (
    ({"危险系", "疯感", "高拉扯"}, "带刺的玫瑰，我偏要惹"),
    ({"冷感", "神秘系", "慢热"}, "冰山美人，但我是火山"),
    ({"阳光", "热血", "直球主动"}, "球都砸我脸上了，还躲什么"),
    ({"强占有", "控制型", "高拉扯"}, "红灯都亮成这样了，我还往里冲"),
    ({"成熟可靠", "温柔", "稳定恋爱"}, "稳稳接住我，这谁扛得住"),
    ({"腹黑", "神秘系", "高拉扯"}, "心眼藏得深，我偏想拆穿"),
    ({"少年感", "阳光", "陪伴成长"}, "少年迎着光，我先心软了"),
    ({"冷感", "低表达", "慢热"}, "嘴上不说，我就等你露馅"),
)

TAG_HEART_TITLES = {
    "阳光": "他一笑，我的阴天就结束了",
    "冷感": "越是淡淡的，越让我移不开眼",
    "温柔": "被好好接住的瞬间最要命",
    "毒舌": "嘴上不饶人，偏偏让我惦记",
    "腹黑": "明知他有心眼，我还是想靠近",
    "天然": "毫无防备的可爱最让人心软",
    "成熟可靠": "有人稳稳托底，我就放心沦陷",
    "傲娇": "口是心非里藏着我的心动答案",
    "疯感": "越不按常理出牌，越让人上头",
    "理性沉稳": "克制与清醒，也能让心跳失控",
    "热血": "认真燃烧的人，总让我跟着心动",
    "危险系": "危险预警响了，我却还想靠近",
    "神秘系": "看不透的那一面，最让我好奇",
    "反差萌": "反差揭开的瞬间，我彻底投降",
    "年上感": "从容靠近时，我已经无处可逃",
    "少年感": "鲜活的少年气，一眼就让人心软",
    "色气": "若有若无的撩拨，才最难招架",
    "非人感": "越不像人间来客，越让我着迷",
    "精英感": "游刃有余的人，偏偏最有吸引力",
    "脆弱感": "看见他的破碎，我就舍不得走",
    "强者感": "强大到耀眼的人，让目光无处躲藏",
    "直球主动": "真心迎面而来，我根本躲不开",
    "慢热": "一点点靠近，反而让心动更久",
    "高拉扯": "进退之间，心跳早就乱了节奏",
    "强守护": "被坚定选择，是我最难抵抗的浪漫",
    "高奉献": "有人把真心捧来，我怎么舍得推开",
    "高依赖": "被需要的感觉，让关系越陷越深",
    "强占有": "偏爱写得太明显，我反而无法拒绝",
    "强嫉妒": "藏不住的在意，最容易泄露真心",
    "控制型": "步步落进他的节奏，竟然也会上瘾",
    "低表达": "话那么少，心意却让我反复猜想",
    "治愈系": "和他在一起，连疲惫都有了去处",
    "宿命感": "像是命中注定，绕多远都会相遇",
    "欢喜冤家": "一边斗嘴，一边偷偷把心交出去",
    "陪伴成长": "一起走过的路，本身就是浪漫",
    "救赎感": "在彼此最暗的时刻，成为那束光",
    "刺激型": "心跳被推到最高点，才叫真正上头",
    "稳定恋爱": "细水长流的偏爱，比烟花更动人",
    "高情绪浓度": "爱意浓到失控，连呼吸都被牵动",
    "并肩恋爱": "站在彼此身边，比被保护更浪漫",
    "唯一例外": "所有原则之外，他是唯一的答案",
}


def heart_title_candidates(tags: list[str], index: int = 0) -> list[str]:
    """Return semantic alternatives without counters or system-like suffixes."""
    tag_set = set(tags)
    matched_rules = sorted(
        (item for item in HEART_TITLE_RULES if tag_set & item[0]),
        key=lambda item: (-len(tag_set & item[0]), HEART_TITLE_RULES.index(item)),
    )
    # A combination headline should only win when the signal actually matches
    # the combination, not merely one incidental tag inside it.
    titles = [title for rule, title in matched_rules if len(tag_set & rule) >= 2]
    titles.extend(TAG_HEART_TITLES[tag] for tag in tags if tag in TAG_HEART_TITLES)
    titles.extend(title for rule, title in matched_rules if len(tag_set & rule) < 2)
    if tags:
        titles.append(f"{'与'.join(tags[:3])}，拼出了我的心动轮廓")
    return list(dict.fromkeys(titles))


def heart_title_concept(title: str, tags: list[str]) -> str | None:
    """Identify the controlled-tag concept represented by deterministic copy."""
    for tag, copy in TAG_HEART_TITLES.items():
        if title == copy:
            return tag
    for rule, copy in HEART_TITLE_RULES:
        if title == copy:
            return next((tag for tag in tags if tag in rule), None)
    return None


def fallback_heart_title(tags: list[str], index: int) -> str:
    candidates = heart_title_candidates(tags, index)
    return candidates[0] if candidates else "这份心动，有它独特的方向"
