"""Independent AOProfile v1 preview. Does not alter the production app flow."""
from pathlib import Path
from io import BytesIO

import streamlit as st

from utils.aoprofile_v1 import (
    MAX_CN, MAX_CONTACT, MAX_FAVORITE_GAMES, MAX_NOTE, MAX_OSHI, MAX_TURN_OFFS,
    build_profile_data, render_profile_png, representative_xp_tags,
)
from utils.tag_recommender_v6 import load_tag_characters

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

st.set_page_config(page_title="AOProfile v1 Preview", page_icon="♡", layout="centered")
st.markdown("""
<style>
:root {color-scheme:light}.stApp{background:#fffaf7;color:#4b4147}
[data-testid="stHeader"]{background:rgba(255,250,247,.9)}
h1,h2,h3,p,label,.stMarkdown{color:#4b4147!important}
[data-baseweb="input"]>div,[data-baseweb="textarea"]>div,[data-baseweb="select"]>div{background:#fff!important;border-color:#e8dce2!important;border-radius:14px!important}
.stButton button,.stDownloadButton button{border-radius:999px;border:1px solid #ddb9c8;background:#f8e8ef;color:#724e5e;font-weight:650}
.stButton button:hover,.stDownloadButton button:hover{border-color:#cea5b6;background:#f4dce6;color:#654251}
[data-testid="stFileUploaderDropzone"]{background:#fff;border-color:#e8dce2;border-radius:18px}
</style>
""", unsafe_allow_html=True)

@st.cache_data(show_spinner=False)
def load_catalog():
    return load_tag_characters(DATA_DIR / "core_xp_tags_v6.csv", DATA_DIR / "core_xp_tags_v6_2_review.csv")

characters = load_catalog()
by_id = {item.character_id: item for item in characters}
games = sorted({item.game_title for item in characters})
demo_ids = [item.character_id for item in characters[:6]]

st.title("AOProfile")
st.caption("独立预览 · 将一次 AOMatch 结果整理成可保存的个人卡片")

with st.expander("预览输入：模拟本次 AOMatch 已选择的角色", expanded=False):
    demo_selected = st.multiselect(
        "已喜欢的角色",
        options=list(by_id),
        default=demo_ids,
        format_func=lambda cid: f"{by_id[cid].character_name}｜{by_id[cid].game_title}",
        max_selections=MAX_OSHI,
    )

selected = [by_id[cid] for cid in demo_selected]
xp_tags = representative_xp_tags(selected)
inherited_names = [item.character_name for item in selected]

st.subheader("编辑资料")
avatar = st.file_uploader("Avatar（可选）", type=["png", "jpg", "jpeg"])
cn = st.text_input("CN", max_chars=MAX_CN, placeholder="你的常用名")
contact = st.text_area("Contact（可选）", max_chars=MAX_CONTACT, placeholder="小红书：xxxx\n微博：xxxx", height=85)
favorite_games = st.multiselect("♡ Favorite Games（1–6 部）", games, max_selections=MAX_FAVORITE_GAMES)
st.text_input("♡ My XP（继承自结果，只读）", value=" / ".join(xp_tags), disabled=True)
oshi_names = st.multiselect(
    "♡ My Oshi（继承自本次选择，可移除）",
    options=inherited_names,
    default=inherited_names[:MAX_OSHI],
    max_selections=MAX_OSHI,
)
turn_offs = st.text_area("雷点（可选）", max_chars=MAX_TURN_OFFS, height=80)
note = st.text_area("♡ Note（可选）", max_chars=MAX_NOTE, placeholder="同担大欢迎 ♡", height=100)

if not selected:
    st.info("请在上方模拟输入中保留至少一位喜欢的角色。")
elif not xp_tags:
    st.info("当前结果没有可继承的 XP Tags。")

try:
    profile = build_profile_data(cn, contact, favorite_games, xp_tags, oshi_names, turn_offs, note)
except ValueError as exc:
    profile = None
    st.caption(str(exc))

if profile:
    avatar_bytes = avatar.getvalue() if avatar else None
    png = render_profile_png(profile, avatar_bytes)
    st.subheader("卡片预览")
    st.image(BytesIO(png), use_container_width=True)
    st.download_button(
        "保存 AOProfile PNG",
        data=png,
        file_name="AOProfile.png",
        mime="image/png",
        use_container_width=True,
    )
