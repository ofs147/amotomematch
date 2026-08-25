"""AOMatch v6.4 Tag-first + AI reranking result experience preview."""
from pathlib import Path
import hashlib
import re
from functools import lru_cache
from io import BytesIO

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from utils.ai_xp_interpreter_v6 import MockAIProvider, fallback_as_ai_response, generate_result
from utils.result_ui_v6 import render_result
from utils.share_card_v6 import build_share_svg

try:
    from utils.share_card_v6 import build_share_png
except ImportError:  # Keep the site bootable during an interrupted multi-file deploy.
    build_share_png = None
from utils.aoprofile_ui import render_aoprofile_editor
from utils.tag_recommender_v6 import build_fallback_result, load_tag_characters

BASE_DIR = Path(__file__).resolve().parent
TAG_FILE = BASE_DIR / "data" / "core_xp_tags_v6.csv"
REVIEW_FILE = BASE_DIR / "data" / "core_xp_tags_v6_2_review.csv"
DICTIONARY_FILE = BASE_DIR / "data" / "core_xp_tag_dictionary_v6.csv"
DISPLAY_NAMES_FILE = BASE_DIR / "data" / "character_display_names_zh.csv"
SERIES_DISPLAY_NAMES_FILE = BASE_DIR / "data" / "series_display_names_zh.csv"
TAG_SOURCE_LABEL = "data/core_xp_tags_v6.csv"


@lru_cache(maxsize=24)
def _emergency_share_font(size: int, bold: bool = False):
    """Return a usable font even when a cloud upload missed the bundled font."""
    candidates = (
        BASE_DIR / "assets" / "fonts" / "NotoSansSC-VF.ttf",
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("C:/Windows/Fonts/msyh.ttc"),
    )
    for candidate in candidates:
        if candidate.exists():
            try:
                font = ImageFont.truetype(str(candidate), size)
                if candidate == BASE_DIR / "assets" / "fonts" / "NotoSansSC-VF.ttf" and hasattr(font, "set_variation_by_name"):
                    font.set_variation_by_name(b"Bold" if bold else b"Regular")
                return font
            except OSError:
                continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _emergency_share_png(result, selected) -> bytes:
    """Pixel-identical fallback for partially synchronized cloud deploys."""
    swatches = Image.new("RGB", (64, 64))
    pixels = swatches.load()
    pink, white, blue = (255, 245, 248), (255, 253, 251), (238, 247, 255)
    for gradient_y in range(64):
        for gradient_x in range(64):
            progress = (gradient_x / 63 + gradient_y / 63) / 2
            if progress <= 0.52:
                ratio = progress / 0.52
                start, end = pink, white
            else:
                ratio = (progress - 0.52) / 0.48
                start, end = white, blue
            pixels[gradient_x, gradient_y] = tuple(
                round(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3)
            )
    image = swatches.resize((1080, 1440), Image.Resampling.BICUBIC).convert("RGBA")
    decoration = Image.new("RGBA", image.size, (0, 0, 0, 0))
    decoration_draw = ImageDraw.Draw(decoration)
    decoration_draw.ellipse((825, -75, 1195, 295), fill=(247, 219, 231, 133))
    decoration_draw.ellipse((-165, 1120, 255, 1540), fill=(223, 239, 255, 163))
    image = Image.alpha_composite(image, decoration)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((48, 60, 1032, 1404), radius=48, fill=(184, 138, 160, 41))
    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(18))).convert("RGB")
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 1032, 1392), radius=48, fill="#fffdfd", outline="#efdce5", width=3)

    def centered(box, text, font, color):
        left, top, right, bottom = box
        bounds = draw.textbbox((0, 0), text, font=font)
        width, height = bounds[2] - bounds[0], bounds[3] - bounds[1]
        draw.text(((left + right - width) / 2, (top + bottom - height) / 2 - bounds[1]), text, font=font, fill=color)

    def wrapped(text, font, max_width, max_lines):
        lines, current = [], ""
        for char in str(text).strip():
            candidate = current + char
            if current and draw.textbbox((0, 0), candidate, font=font)[2] > max_width:
                lines.append(current)
                current = char
                if len(lines) == max_lines:
                    break
            else:
                current = candidate
        if len(lines) < max_lines and current:
            lines.append(current)
        consumed = "".join(lines)
        if len(consumed) < len(str(text).strip()) and lines:
            while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=font)[2] > max_width:
                lines[-1] = lines[-1][:-1]
            lines[-1] += "…"
        return lines

    draw.text((86, 89), "AOMATCH", font=_emergency_share_font(25, True), fill="#b2768d")
    draw.text((86, 170), "我的乙游心动讯号", font=_emergency_share_font(64, True), fill="#463640")
    draw.text((88, 254), "原来，我会反复为这样的角色心动。", font=_emergency_share_font(27), fill="#937c88")
    label_font = _emergency_share_font(24, True)
    draw.text((86, 309), "这次选择", font=label_font, fill="#aa8394")

    name_font = _emergency_share_font(25, True)
    for index, item in enumerate(selected[:10]):
        column, row = index % 2, index // 2
        x, y = 86 + column * 468, 367 + row * 64
        box = (x, y, x + 440, y + 50)
        draw.rounded_rectangle(box, radius=25, fill="#fff2f6", outline="#efcbd9", width=2)
        name = item.character_name
        while name and draw.textbbox((0, 0), name, font=name_font)[2] > 350:
            name = name[:-1]
        if name != item.character_name:
            name = name.rstrip() + "…"
        centered(box, name, name_font, "#754f60")

    draw.text((86, 702), "心动关键词", font=label_font, fill="#aa8394")
    signals = [item.title for item in result.heart_signals[:3]] or ["多线心动型"]
    gap = 18
    card_width = int((908 - gap * (len(signals) - 1)) / len(signals))
    signal_font = _emergency_share_font(27, True)
    for index, title in enumerate(signals):
        x = 86 + index * (card_width + gap)
        box = (x, 750, x + card_width, 918)
        draw.rounded_rectangle(box, radius=25, fill="#f9f5f8", outline="#eee2e8", width=2)
        centered((x, 763, x + card_width, 811), "♡", _emergency_share_font(34), "#db789d")
        lines = wrapped(title, signal_font, card_width - 54, 2)
        for line_index, line in enumerate(lines):
            centered((x + 18, 820 + line_index * 36, x + card_width - 18, 856 + line_index * 36), line, signal_font, "#765063")

    draw.text((86, 963), "我的心动画像", font=label_font, fill="#aa8394")
    summary_font = _emergency_share_font(27, True)
    summary_lines = wrapped(result.xp_personality, summary_font, 820, 4)
    for index, line in enumerate(summary_lines):
        centered((110, 1023 + index * 47, 970, 1068 + index * 47), line, summary_font, "#765063")

    draw.line((86, 1310, 994, 1310), fill="#eadde3", width=2)
    footer_font = _emergency_share_font(23)
    draw.text((86, 1330), "保存这张图，分享给懂你的人 ♡", font=footer_font, fill="#a18491")
    footer = "AOtomeMatch 心动速配"
    footer_width = draw.textbbox((0, 0), footer, font=footer_font)[2]
    draw.text((994 - footer_width, 1330), footer, font=footer_font, fill="#a18491")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def display_data_version() -> str:
    """Invalidate Streamlit's data cache whenever a live catalog file changes."""
    digest = hashlib.sha256()
    for path in (
        TAG_FILE,
        REVIEW_FILE,
        DICTIONARY_FILE,
        DISPLAY_NAMES_FILE,
        SERIES_DISPLAY_NAMES_FILE,
    ):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()

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
[class*="st-key-character_card_"] [class*="st-key-add_"],
[class*="st-key-character_card_"] [class*="st-key-remove_"] {
  position: absolute !important; right: .32rem !important; top: .08rem !important; width: 2.65rem !important;
}
[data-testid="stVerticalBlockBorderWrapper"] {border-color: #eadfe4 !important; border-radius: 18px !important; background: #fffdfc !important;}
.v6-step {font-size: .78rem; letter-spacing: .08em; color: #a16e81; margin: 1.2rem 0 .25rem;}
.v6-full-name {margin: -.55rem 0 .85rem .12rem; color: #ad8293; font-size: .78rem; letter-spacing: .16em; font-weight: 600;}
.v6-guidance {padding: .85rem 1rem; border-radius: 16px; background: #f8f3f5; color: #685d64; margin: .5rem 0 1rem;}
.v6-selection-summary {margin: .7rem 0 1rem; color: #776b72;}
.v6-tag-preview {display:flex; flex-wrap:wrap; gap:.32rem; margin:.4rem 0 .15rem;}
.v6-tag-preview span {font-size:.74rem; background:#f8e9ef; color:#80586a; border-radius:999px; padding:.18rem .48rem;}
[class*="st-key-character_choice_"] button,
[class*="st-key-selected_choice_"] button{
  width:100%!important;min-height:2.5rem!important;padding:.32rem .55rem!important;
  border-radius:11px!important;background:#fffdfc!important;border:1px solid #eadfe4!important;
  color:#594c54!important;-webkit-text-fill-color:#594c54!important;box-shadow:none!important;
}
[class*="st-key-character_choice_"] button p,
[class*="st-key-selected_choice_"] button p{
  margin:0!important;font-size:.86rem!important;line-height:1.15!important;
  font-family:Arial,"Microsoft YaHei",sans-serif!important;font-variant-emoji:text!important;
}
[class*="st-key-character_choice_"] button::after,
[class*="st-key-selected_choice_"] button::after{
  content:"♡";display:inline-block;margin-left:.42rem;color:#c26385!important;
  -webkit-text-fill-color:#c26385!important;font-family:Arial,"Times New Roman",sans-serif!important;
  font-variant-emoji:text!important;font-size:1.48rem!important;line-height:1!important;
}
[class*="st-key-character_choice_selected_"] button::after,
[class*="st-key-selected_choice_"] button::after{
  content:"♥";font-size:1.72rem!important;color:#c26385!important;
  -webkit-text-fill-color:#c26385!important;
}
/* AOProfile mobile fallback: never allow the platform accent color onto selected chips. */
[class*="st-key-aop_games"] :is(span,div)[data-baseweb="tag"]{
  background:#e8f3fb!important;background-color:#e8f3fb!important;background-image:none!important;
  border-color:#c8deed!important;color:#4f7087!important;-webkit-text-fill-color:#4f7087!important;
}
[class*="st-key-aop_games"] [data-tag]{
  background:#e8f3fb!important;background-color:#e8f3fb!important;background-image:none!important;
  border:1px solid #c8deed!important;color:#4f7087!important;-webkit-text-fill-color:#4f7087!important;
}
[class*="st-key-aop_oshi"] :is(span,div)[data-baseweb="tag"]{
  background:#f8e5ed!important;background-color:#f8e5ed!important;background-image:none!important;
  border-color:#e8bfd0!important;color:#7b5264!important;-webkit-text-fill-color:#7b5264!important;
}
[class*="st-key-aop_oshi"] [data-tag]{
  background:#f8e5ed!important;background-color:#f8e5ed!important;background-image:none!important;
  border:1px solid #e8bfd0!important;color:#7b5264!important;-webkit-text-fill-color:#7b5264!important;
}
[class*="st-key-aop_games"] :is(span,div)[data-baseweb="tag"] *,
[class*="st-key-aop_games"] [data-tag] *,
[class*="st-key-aop_oshi"] [data-tag] *,
[class*="st-key-aop_oshi"] :is(span,div)[data-baseweb="tag"] *{
  background:transparent!important;background-color:transparent!important;color:inherit!important;
  -webkit-text-fill-color:currentColor!important;fill:currentColor!important;
}
@media (max-width: 700px) {
  .block-container {padding-left: 1rem !important; padding-right: 1rem !important;}
  [class*="st-key-character_row_"] [data-testid="stHorizontalBlock"] {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr) !important;
    column-gap: .42rem !important; row-gap: 0 !important;
  }
  [class*="st-key-character_row_"] [data-testid="stHorizontalBlock"] > [data-testid="stColumn"] {
    width: 100% !important; min-width: 0 !important; max-width: none !important;
    flex: none !important;
  }
  [class*="st-key-character_choice_"] button,
  [class*="st-key-selected_choice_"] button{
    height:2.35rem!important;min-height:2.35rem!important;padding:.18rem .34rem!important;
    display:flex!important;align-items:center!important;justify-content:center!important;
  }
  [class*="st-key-character_choice_"] button p,
  [class*="st-key-selected_choice_"] button p{
    font-size:.8rem!important;line-height:1.1!important;text-align:center!important;
  }
  [class*="st-key-character_card_"] [data-testid="stVerticalBlockBorderWrapper"] {
    height: 2.45rem !important; min-height: 2.45rem !important;
    padding: 0 !important; box-sizing: border-box !important;
    border-radius: 11px !important; overflow: hidden !important;
  }
  [class*="st-key-character_card_"] [data-testid="stVerticalBlock"] {
    height: 100% !important; min-height: 0 !important; gap: 0 !important;
  }
  [class*="st-key-character_card_"] .stMarkdown {
    position: absolute !important; left: .42rem !important; right: 2.1rem !important;
    top: 50% !important; transform: translateY(-50%) !important;
    min-height: 0 !important; padding: 0 !important;
  }
  [class*="st-key-character_card_"] .stMarkdown > div {width: 100% !important;}
  [class*="st-key-character_card_"] .stMarkdown p {
    min-height: 0 !important; font-size: .82rem !important;
    margin: 0 !important; line-height: 1.15 !important;
  }
  [class*="st-key-character_card_"] [class*="st-key-add_"],
  [class*="st-key-character_card_"] [class*="st-key-remove_"] {
    right: .28rem !important; top: 50% !important; width: 1.72rem !important;
    transform: translateY(-50%) !important;
  }
  [class*="st-key-character_card_"] .stButton > button {
    width: 1.72rem !important; min-height: 1.72rem !important; height: 1.72rem !important;
    padding: 0 !important;
  }
  [class*="st-key-character_card_"] [class*="st-key-add_"] button p,
  [class*="st-key-character_card_"] [class*="st-key-remove_"] button p {
    font-family: Arial, "Times New Roman", sans-serif !important;
    font-variant-emoji: text !important;
    font-size: 1.55rem !important; line-height: 1 !important;
  }
  [class*="st-key-character_card_"] [class*="st-key-add_"] button[kind="primary"] p,
  [class*="st-key-character_card_"] [class*="st-key-remove_"] button p {
    font-size: 1.72rem !important;
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


characters, controlled_tags = load_preview_data(display_data_version())
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
                    selected_already = character.character_id in st.session_state.v6_selected_ids
                    at_limit = len(st.session_state.v6_selected_ids) >= 10
                    if st.button(
                        character.character_name,
                        key=(f"character_choice_selected_{character.character_id}" if selected_already else f"character_choice_{character.character_id}"),
                        type="secondary",
                        disabled=at_limit and not selected_already,
                        help="取消选择" if selected_already else "选择角色",
                        use_container_width=True,
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
        with st.container(key=f"character_row_selected_{start}"):
            columns = st.columns(2)
            for column, character_id in zip(columns, selected_ids[start : start + 2]):
                character = by_id[character_id]
                with column:
                    if st.button(
                        character.character_name,
                        key=f"selected_choice_{character_id}",
                        type="secondary",
                        help="取消选择",
                        use_container_width=True,
                    ):
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
        try:
            if build_share_png is None:
                raise RuntimeError("cloud deploy is missing the current PNG renderer")
            share_png = build_share_png(st.session_state.v6_result, result_selected)
        except Exception:
            # A partial GitHub upload must never turn the share button into an
            # error page.  This renderer lives in app.py and produces a real
            # PNG without depending on the synchronized utility module.
            share_png = _emergency_share_png(st.session_state.v6_result, result_selected)
        st.image(share_png, use_container_width=True)
        st.download_button(
            "保存分享图片",
            data=share_png,
            file_name="AOtomeMatch_我的心动画像.png",
            mime="image/png",
            use_container_width=True,
        )
