"""AOMatch Character Database v2 的集中式 Schema 配置。

当前线上 MVP v1.1 不读取本文件。后续 v2 Profile 和推荐算法应统一从这里
取得字段、显示名和权重，避免配置散落在不同模块中。
"""

LOOK = "LOOK"
PERSONALITY = "PERSONALITY"
ARCHETYPE = "ARCHETYPE"
ROMANCE = "ROMANCE"

LAYERS = (LOOK, PERSONALITY, ARCHETYPE, ROMANCE)

LAYER_DISPLAY_NAMES = {
    LOOK: "Appearance / LOOK XP",
    PERSONALITY: "Character Personality / PERSONALITY XP",
    ARCHETYPE: "Appeal / Archetype / ARCHETYPE XP",
    ROMANCE: "Romance Dynamics / ROMANCE XP",
}

LAYER_WEIGHTS = {
    LOOK: 0.15,
    PERSONALITY: 0.25,
    ARCHETYPE: 0.25,
    ROMANCE: 0.35,
}

# Hybrid Matching 中每层的 Numeric / Tag 子权重。
MATCH_COMPONENT_WEIGHTS = {
    LOOK: {"numeric": 0.35, "tag": 0.65},
    PERSONALITY: {"numeric": 0.75, "tag": 0.25},
    ARCHETYPE: {"numeric": 0.35, "tag": 0.65},
    ROMANCE: {"numeric": 0.80, "tag": 0.20},
}

NUMERIC_FEATURES_BY_LAYER = {
    LOOK: ("visual_maturity", "physical_presence"),
    PERSONALITY: (
        "warmth",
        "extroversion",
        "emotional_expression",
        "personality_maturity",
        "humor",
        "cunning",
        "emotional_stability",
    ),
    ARCHETYPE: ("danger_level", "mystery_level", "gap_moe"),
    ROMANCE: (
        "initiative",
        "possessiveness",
        "protectiveness",
        "dependence",
        "jealousy",
        "push_pull",
        "devotion",
        "control",
    ),
}

NUMERIC_FEATURES = tuple(
    feature
    for layer in LAYERS
    for feature in NUMERIC_FEATURES_BY_LAYER[layer]
)

NUMERIC_DISPLAY_NAMES = {
    "visual_maturity": "视觉成熟感",
    "physical_presence": "身体存在感",
    "warmth": "温柔度",
    "extroversion": "外向度",
    "emotional_expression": "情绪表达程度",
    "personality_maturity": "心理成熟度",
    "humor": "幽默 / 玩心",
    "cunning": "腹黑 / 心机程度",
    "emotional_stability": "情绪稳定度",
    "danger_level": "危险感",
    "mystery_level": "神秘感",
    "gap_moe": "反差萌",
    "initiative": "恋爱主动程度",
    "possessiveness": "占有欲",
    "protectiveness": "保护欲",
    "dependence": "情感依赖程度",
    "jealousy": "吃醋程度",
    "push_pull": "暧昧 / 拉扯感",
    "devotion": "奉献 / 深情程度",
    "control": "控制欲",
}

FEATURE_LAYERS = {
    feature: layer
    for layer, features in NUMERIC_FEATURES_BY_LAYER.items()
    for feature in features
}

BASIC_FIELDS = (
    "character_id",
    "character_name",
    "game",
    "series",
    "route_type",
)

REQUIRED_BASIC_FIELDS = BASIC_FIELDS

TAG_FIELDS_BY_LAYER = {
    LOOK: (
        "hair_length",
        "hair_color",
        "eye_tags",
        "appearance_details",
        "visual_vibe_tags",
    ),
    PERSONALITY: ("personality_tags",),
    ARCHETYPE: (
        "age_position_tags",
        "role_fantasy_tags",
        "relationship_trope_tags",
        "archetype_tags",
    ),
    ROMANCE: ("romance_tags",),
}

# keywords 是自由展示标签，不参与固定词典校验，也不应默认参与推荐计分。
DICTIONARY_TAG_FIELDS = tuple(
    field for layer in LAYERS for field in TAG_FIELDS_BY_LAYER[layer]
)
FREE_TAG_FIELDS = ("keywords",)
TAG_FIELDS = DICTIONARY_TAG_FIELDS + FREE_TAG_FIELDS

TAG_FIELD_LAYERS = {
    field: layer
    for layer, fields in TAG_FIELDS_BY_LAYER.items()
    for field in fields
}

# 每个标准标签只归属于一个字段，避免 Hybrid Matching 重复计分。
TAG_DICTIONARY = {
    "hair_length": ("短发", "中长发", "长发"),
    "hair_color": (
        "黑发", "白发", "银发", "金发", "棕发", "红发",
        "蓝发", "紫发", "粉发", "绿发", "特殊发色",
    ),
    "eye_tags": (
        "垂眼", "吊眼", "桃花眼", "圆眼", "细长眼", "异瞳",
        "猫系眼", "无机质眼神", "温柔眼", "锐利眼",
    ),
    "appearance_details": (
        "眼镜", "眼罩", "泪痣", "伤疤", "绷带", "耳饰", "虎牙",
        "兽耳", "兽尾", "黑皮", "冷白皮", "卷发", "护目镜",
    ),
    "visual_vibe_tags": (
        "清冷感", "清爽", "柔和感", "美人系", "精英感", "少年感", "成年人感",
        "病弱感", "野性", "贵气", "色气", "禁欲感", "危险感",
        "无害感", "神秘感",
    ),
    "personality_tags": (
        "傲娇", "毒舌", "天然", "闷骚", "直球", "温柔", "清冷", "腹黑", "疯批",
        "乖巧", "恋爱脑", "笑面虎", "中二", "老实人", "社恐",
        "社牛", "纯情", "钓系", "偏执", "强势", "沉稳", "阳光",
        "阴郁", "理性", "感性", "责任感强", "自卑", "自信",
        "嘴硬心软", "表里不一",
    ),
    "age_position_tags": (
        "年上", "年下", "同龄", "前辈", "后辈", "上司", "下属",
        "师父", "徒弟", "主人", "护卫",
    ),
    "role_fantasy_tags": (
        "王子", "皇族", "贵族", "骑士", "军人", "警察", "医生",
        "学者", "教师", "艺术家", "偶像", "商人", "黑道", "组织首领", "杀手",
        "怪盗", "神职人员", "执事", "侦探", "普通社会人", "学生",
        "人外", "神明", "妖怪", "幽灵", "机器人", "黑客", "自警团",
        "工程师", "程序员", "审讯官", "经营者", "侍从",
    ),
    "relationship_trope_tags": (
        "青梅竹马", "天降", "欢喜冤家", "相爱相杀", "敌对恋爱",
        "久别重逢", "双向暗恋", "单向暗恋", "先婚后爱", "契约关系",
        "主仆", "师徒", "禁忌之恋", "伪骨科", "宿命", "救赎",
        "共犯", "并肩作战", "保护者×被保护者", "从朋友到恋人",
        "从敌人到恋人",
    ),
    "archetype_tags": (
        "猫系", "犬系", "忠犬", "白切黑", "黑切白", "高岭之花",
        "禁欲系", "病娇", "神秘系", "危险系", "可靠系",
        "保护者", "天才", "病弱", "战损", "纯爱战士", "人夫感",
        "爹系", "弟系", "色气系", "清冷系", "救赎系", "强者",
        "脆弱感", "表面轻浮实则认真",
    ),
    "romance_tags": (
        "安全型恋爱", "焦虑型依恋", "回避型依恋", "陪伴型", "救赎型",
        "拉扯型", "克制型", "双强", "慢热", "一见钟情", "日久生情", "柏拉图",
        "高亲密需求", "灵魂伴侣", "琴瑟和鸣", "烂人真心",
        "唯一例外", "成年人恋爱", "纯爱", "禁断感", "强情绪浓度",
    ),
}

CSV_COLUMNS = (
    *BASIC_FIELDS,
    "visual_maturity",
    "physical_presence",
    "hair_length",
    "hair_color",
    "eye_tags",
    "appearance_details",
    "visual_vibe_tags",
    "warmth",
    "extroversion",
    "emotional_expression",
    "personality_maturity",
    "humor",
    "cunning",
    "emotional_stability",
    "personality_tags",
    "danger_level",
    "mystery_level",
    "gap_moe",
    "age_position_tags",
    "role_fantasy_tags",
    "relationship_trope_tags",
    "archetype_tags",
    "initiative",
    "possessiveness",
    "protectiveness",
    "dependence",
    "jealousy",
    "push_pull",
    "devotion",
    "control",
    "romance_tags",
    "keywords",
)
