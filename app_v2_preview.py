"""AOMatch v6.4 Tag-first + AI reranking result experience preview."""
from pathlib import Path
import base64
import re

import pandas as pd
import streamlit as st

from utils.ai_xp_interpreter_v6 import MockAIProvider, fallback_as_ai_response, generate_result
from utils.result_ui_v6 import render_result
from utils.share_card_v6 import build_share_svg
from utils.aoprofile_ui import render_aoprofile_editor
from utils.tag_recommender_v6 import build_fallback_result, load_tag_characters

BASE_DIR = Path(__file__).resolve().parent
TAG_FILE = BASE_DIR / "data" / "core_xp_tags_v6.csv"
REVIEW_FILE = BASE_DIR / "data" / "core_xp_tags_v6_2_review.csv"
DICTIONARY_FILE = BASE_DIR / "data" / "core_xp_tag_dictionary_v6.csv"
DISPLAY_NAMES_FILE = BASE_DIR / "data" / "character_display_names_zh.csv"
SERIES_DISPLAY_NAMES_FILE = BASE_DIR / "data" / "series_display_names_zh.csv"
TAG_SOURCE_LABEL = "data/core_xp_tags_v6.csv"
# Keep this key aligned with the roster/tag dataset so Streamlit cannot reuse
# a character list cached before a production expansion.
DISPLAY_DATA_VERSION = "6.7.53-wataju-expansion"

CHINESE_TITLE_FIRST_PINYIN = {
    "安": "an", "奥": "ao", "百": "bai", "毘": "bi", "薄": "bo",
    "大": "da", "第": "di", "蝶": "die", "冬": "dong", "歌": "ge",
    "共": "gong", "黑": "hei", "花": "hua", "幻": "huan", "灰": "hui",
    "剑": "jian", "冷": "leng", "璃": "li", "米": "mi", "明": "ming",
    "茉": "mo", "魔": "mo", "虔": "qian", "如": "ru", "失": "shi",
    "十": "shi", "提": "ti", "天": "tian", "心": "xin", "幸": "xing",
    "绚": "xuan", "遥": "yao", "灾": "zai", "终": "zhong",
}

PAGE_STYLE = """
<style>
:root {color-scheme: light;}
html, body, [data-testid="stAppViewContainer"], .stApp {
  background: #fffaf8 !important; color: #443941 !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif;
}
[data-testid="stHeader"] {background: rgba(255,250,248,.92) !important;}
[data-testid="stSidebar"] {background: #f7faff !important; border-right: 1px solid #e4edf5;}
[data-testid="stSidebar"] * {color: #4c4650;}
.stMarkdown, .stCaption, label, p, h1, h2, h3 {color: #443941 !important;}
.stCaption, [data-testid="stCaptionContainer"] {color: #746b72 !important;}
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-testid="stSelectbox"] > div > div {
  background: #fffefe !important; border-color: #dfd8dc !important; color: #443941 !important;
  border-radius: 14px !important;
}
[data-baseweb="select"] *, [data-baseweb="input"] *,
[data-testid="stSelectbox"] input {
  color: #443941 !important; caret-color: #a16e81 !important;
}
[data-testid="stSelectbox"] input,
[data-baseweb="select"] input,
[data-baseweb="input"] input {
  background-color: #fffefe !important;
  -webkit-text-fill-color: #443941 !important;
}
[data-testid="stSelectbox"] input::placeholder,
[data-baseweb="select"] input::placeholder {color: #91868d !important; opacity: 1 !important;}
[data-baseweb="popover"], [data-baseweb="menu"], [role="listbox"],
[data-baseweb="popover"] > div, [data-baseweb="menu"] > div {
  background-color: #fffefe !important; color: #443941 !important;
}
[data-baseweb="popover"] li, [data-baseweb="menu"] li, [role="option"] {
  background-color: #fffefe !important; color: #443941 !important;
}
[role="option"]:hover, [aria-selected="true"] {background: #f8e9ef !important;}
.stButton > button, .stFormSubmitButton > button, .stDownloadButton > button {
  border-radius: 999px !important; border: 1px solid #ddb8c7 !important;
  background: #f9e8ef !important; color: #754e60 !important; min-height: 2.55rem;
  box-shadow: none !important; font-weight: 650 !important;
}
.stButton > button:hover, .stDownloadButton > button:hover {background: #f4dce6 !important; border-color: #cfa5b6 !important; color: #694355 !important;}
.stButton > button:focus, .stDownloadButton > button:focus {box-shadow: 0 0 0 3px rgba(213,169,188,.22) !important;}
.stDownloadButton > button *, .stDownloadButton > button:hover * {
  color: inherit !important; -webkit-text-fill-color: currentColor !important;
}
.stButton > button:disabled {background: #f3f0f2 !important; border-color: #e2dde0 !important; color: #9c9298 !important;}
button[kind="primary"] {background: #dca9bc !important; border-color: #d39caf !important; color: #fff !important;}
[class*="st-key-add_"] button,
[class*="st-key-add_"] button:hover,
[class*="st-key-add_"] button:focus,
[class*="st-key-add_"] button:active {
  background: transparent !important;
  border: 0 !important;
  color: #c26385 !important;
  -webkit-text-fill-color: #c26385 !important;
  box-shadow: none !important;
  min-height: 2.35rem !important;
  padding: 0 !important;
  font-size: 1.95rem !important;
  line-height: 1 !important;
}
[class*="st-key-add_"] button p {
  font-family: "Segoe UI Symbol", "Arial Unicode MS", sans-serif !important;
  font-size: 1.95rem !important;
  line-height: 1 !important;
  margin: 0 !important;
}
[class*="st-key-add_"] button[kind="primary"] p {font-size: 2.2rem !important;}
[class*="st-key-remove_"] button,
[class*="st-key-remove_"] button:hover,
[class*="st-key-remove_"] button:focus,
[class*="st-key-remove_"] button:active {
  background: transparent !important;
  border: 0 !important;
  color: #c26385 !important;
  -webkit-text-fill-color: #c26385 !important;
  box-shadow: none !important;
  min-height: 2.35rem !important;
  padding: 0 !important;
}
[class*="st-key-remove_"] button p {
  font-family: "Segoe UI Symbol", "Arial Unicode MS", sans-serif !important;
  font-size: 2.2rem !important;
  line-height: 1 !important;
  margin: 0 !important;
}
[class*="st-key-add_"] button:disabled {
  background: transparent !important;
  border: 0 !important;
  color: #b9a5ad !important;
  -webkit-text-fill-color: #b9a5ad !important;
}
[class*="st-key-character_card_"] {position: relative !important;}
[class*="st-key-character_card_"] .stMarkdown {padding-right: 2.25rem !important;}
[class*="st-key-character_card_"] [class*="st-key-add_"] {
  position: absolute !important; right: .32rem !important; top: .08rem !important; width: 2.65rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {border-color: #eadfe4 !important; border-radius: 18px !important; background: #fffdfc !important;}
.v6-step {font-size: .78rem; letter-spacing: .08em; color: #a16e81; margin: 1.2rem 0 .25rem;}
.v6-full-name {margin: -.55rem 0 .85rem .12rem; color: #ad8293; font-size: .78rem; letter-spacing: .16em; font-weight: 600;}
.v6-guidance {padding: .85rem 1rem; border-radius: 16px; background: #f8f3f5; color: #685d64; margin: .5rem 0 1rem;}
.v6-selection-summary {margin: .7rem 0 1rem; color: #776b72;}
.v6-tag-preview {display:flex; flex-wrap:wrap; gap:.32rem; margin:.4rem 0 .15rem;}
.v6-tag-preview span {font-size:.74rem; background:#f8e9ef; color:#80586a; border-radius:999px; padding:.18rem .48rem;}
@media (max-width: 700px) {
  .block-container {padding-left: 1rem !important; padding-right: 1rem !important;}
  [class*="st-key-character_row_"] [data-testid="stHorizontalBlock"] {
    flex-wrap: nowrap !important; gap: .42rem !important;
  }
  [class*="st-key-character_row_"] > div > div > [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: calc(50% - .21rem) !important; min-width: 0 !important; flex: 0 0 calc(50% - .21rem) !important;
  }
  [class*="st-key-character_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    padding: .34rem .48rem !important; border-radius: 11px !important;
  }
  [class*="st-key-character_card_"] [data-testid="stVerticalBlock"] {gap: .12rem !important;}
  [class*="st-key-character_card_"] p {font-size: .86rem !important; margin: 0 !important; line-height: 1.2 !important;}
  [class*="st-key-character_card_"] .stButton > button {
    min-height: 2.55rem !important; padding: 0 !important;
  }
  [class*="st-key-character_card_"] {margin-bottom: -.35rem !important;}
}
</style>
"""

st.set_page_config(page_title="AOMatch · 心动速配", page_icon="♡", layout="wide")
st.markdown(PAGE_STYLE, unsafe_allow_html=True)


@st.cache_data
def load_preview_data(display_data_version: str):
    characters = load_tag_characters(
        TAG_FILE,
        REVIEW_FILE,
        DISPLAY_NAMES_FILE,
        SERIES_DISPLAY_NAMES_FILE,
    )
    dictionary = pd.read_csv(DICTIONARY_FILE, dtype=str, keep_default_na=False)
    if len(dictionary) != 41 or len(set(dictionary["canonical_tag"])) != 41:
        raise ValueError("v6.4 preview requires the calibrated 41-tag dictionary")
    controlled = set(dictionary["canonical_tag"])
    for character in characters:
        if not 2 <= len(character.tags) <= 3 or any(tag not in controlled for tag in character.tags):
            raise ValueError(f"Invalid Tag-first character row: {character.character_id}")
    return characters, controlled


characters, controlled_tags = load_preview_data(DISPLAY_DATA_VERSION)
by_id = {item.character_id: item for item in characters}

if st.session_state.get("v6_view") == "profile":
    render_aoprofile_editor(characters, st.session_state.get("v6_selected_ids", []))
    st.stop()


def game_sort_key(title: str) -> tuple[int, bytes]:
    """Chinese-leading titles first by pinyin-like GBK order, then Latin titles."""
    first_meaningful = next(
        (character for character in title if re.match(r"[\u4e00-\u9fffA-Za-z0-9\u3040-\u30ff]", character)),
        "",
    )
    if re.match(r"[\u4e00-\u9fff]", first_meaningful):
        first_pinyin = CHINESE_TITLE_FIRST_PINYIN.get(first_meaningful, "zz_unknown")
        return 0, first_pinyin.encode("ascii") + b"\0" + title.encode("gbk", errors="replace")
    if re.match(r"[A-Za-z0-9]", first_meaningful):
        return 1, title.casefold().encode("utf-8")
    return 2, title.encode("utf-8")


def clear_generated_result() -> None:
    st.session_state.pop("v6_result", None)
    st.session_state.pop("v6_share_ready", None)


if "v6_selected_ids" not in st.session_state:
    st.session_state.v6_selected_ids = []
st.title("AOMatch · 心动速配")
st.markdown('<div class="v6-full-name">AOtomeMatch</div>', unsafe_allow_html=True)
st.markdown('<div class="v6-guidance">点击作品可选角色，可以随时切换到其他作品继续添加。<br>选择 3–10 位角色后，即可匹配你的心动讯号~</div>', unsafe_allow_html=True)

games = sorted({item.game_title for item in characters}, key=game_sort_key)
st.markdown('<div class="v6-step">STEP 1 · 选择作品</div>', unsafe_allow_html=True)
current_game = st.selectbox(
    "选择一部作品，查看其中的角色",
    options=games,
    index=None,
    placeholder="输入作品名搜索",
)
st.caption("这里一次展示一部作品；选中的角色会保留，所以你可以跨作品自由组合。")

if current_game:
    st.markdown('<div class="v6-step">STEP 2 · 加入角色</div>', unsafe_allow_html=True)
    game_characters = sorted(
        (item for item in characters if item.game_title == current_game),
        key=lambda item: item.character_name.casefold(),
    )
    for start in range(0, len(game_characters), 2):
        with st.container(key=f"character_row_{start}"):
            columns = st.columns(2)
            for column, character in zip(columns, game_characters[start : start + 2]):
                with column:
                    with st.container(border=True, key=f"character_card_{character.character_id}"):
                        selected_already = character.character_id in st.session_state.v6_selected_ids
                        at_limit = len(st.session_state.v6_selected_ids) >= 10
                        st.markdown(f"**{character.character_name}**")
                        if st.button(
                            "♥" if selected_already else "♡",
                            key=f"add_{character.character_id}",
                            type="secondary",
                            disabled=at_limit and not selected_already,
                            help="取消选择" if selected_already else "选择角色",
                        ):
                            if selected_already:
                                st.session_state.v6_selected_ids.remove(character.character_id)
                            else:
                                st.session_state.v6_selected_ids.append(character.character_id)
                            clear_generated_result()
                            st.rerun()

st.markdown('<div class="v6-step">STEP 3 · 已选择的角色 ♡</div>', unsafe_allow_html=True)
selected_ids = [item for item in st.session_state.v6_selected_ids if item in by_id]
st.session_state.v6_selected_ids = selected_ids
if not selected_ids:
    st.caption("你选中的角色会出现在这里。可以来自同一部作品，也可以来自完全不同的作品。")
else:
    st.markdown(f'<div class="v6-selection-summary">已选择 {len(selected_ids)} / 10 位</div>', unsafe_allow_html=True)
    for start in range(0, len(selected_ids), 2):
        columns = st.columns(2)
        for column, character_id in zip(columns, selected_ids[start : start + 2]):
            character = by_id[character_id]
            with column:
                with st.container(border=True):
                    left, right = st.columns([4, 1])
                    with left:
                        st.markdown(f"**{character.character_name}**")
                        st.caption(character.game_title)
                    with right:
                        if st.button("♥", key=f"remove_{character_id}", type="secondary", help="取消选择"):
                            st.session_state.v6_selected_ids.remove(character_id)
                            clear_generated_result()
                            st.rerun()

with st.sidebar:
    st.header("Preview 设置")
    mode = st.radio("Interpretation mode", ["FALLBACK", "MOCK AI"], horizontal=False)
    show_debug = st.toggle("显示 Debug", value=False)
    st.caption("MOCK AI 只验证结构化 AI 路径，不调用网络或付费 API。")

if st.button("看看我的心动讯号", type="primary", use_container_width=True):
    if not 3 <= len(selected_ids) <= 10:
        st.warning("请选择 3–10 位喜欢的角色。")
    else:
        selected = [by_id[character_id] for character_id in selected_ids]
        provider = None
        if mode == "MOCK AI":
            deterministic = build_fallback_result(selected, characters)
            provider = MockAIProvider(fallback_as_ai_response(deterministic))
        result = generate_result(selected, characters, controlled_tags, provider=provider)
        result.debug["selected_identity"] = [
            {
                "character_id": item.character_id,
                "resolved_display_name": item.character_name,
                "game_id": item.game_title,
                "game_display_title": item.game_title,
            }
            for item in selected
        ]
        st.session_state.v6_result = result

if "v6_result" in st.session_state:
    result_selected = [by_id[character_id] for character_id in selected_ids]
    render_result(
        st.session_state.v6_result,
        result_selected,
        debug=show_debug,
    )
    st.markdown("### 制作我的 AOProfile")
    st.caption("把本次选择的角色和心动 XP 做成一张可以分享的个人资料卡。")
    if st.button("生成我的 AOProfile ♡", use_container_width=True):
        st.session_state.v6_view = "profile"
        st.rerun()
    st.markdown("### 分享我的心动画像")
    st.caption("生成一张不包含调试数据的结果卡片，可以保存后发给朋友。")
    if st.button("生成分享图 ♡", use_container_width=True):
        st.session_state.v6_share_ready = True
    if st.session_state.get("v6_share_ready"):
        share_svg = build_share_svg(st.session_state.v6_result, result_selected)
        share_preview = base64.b64encode(share_svg).decode("ascii")
        st.markdown(
            f'<img src="data:image/svg+xml;base64,{share_preview}" '
            'alt="AOMatch 心动画像分享图" style="display:block;width:100%;max-width:680px;margin:0 auto;border-radius:18px;">',
            unsafe_allow_html=True,
        )
        st.download_button(
            "保存分享图片",
            data=share_svg,
            file_name="AOMatch_我的心动画像.svg",
            mime="image/svg+xml",
            use_container_width=True,
        )
