"""Shared AOProfile editor UI for the main app and optional page route."""

from io import BytesIO

import streamlit as st

from utils.aoprofile_v1 import (
    MAX_CN, MAX_CONTACT, MAX_FAVORITE_GAMES, MAX_NOTE, MAX_OSHI, MAX_TURN_OFFS,
    build_profile_data, representative_xp_tags,
)
from utils.aoprofile_renderer_v3 import (
    BUNDLED_FONT_PATH, CARD_SIZE, RENDERER_BUILD, render_profile_png,
)


AOPROFILE_STYLE = """
<style>
:root{color-scheme:light!important}
html,body,[data-testid="stAppViewContainer"],.stApp,.stMain,[data-testid="stMain"]{
  background:#fff9fc!important;color:#493f46!important;color-scheme:light!important;
}
[data-testid="stHeader"]{background:rgba(255,249,252,.94)!important}
[data-testid="stSidebar"]{background:#f7faff!important}
h1,h2,h3,p,label,.stMarkdown,.stCaption,span{color:#493f46}
[data-baseweb="input"]>div,[data-baseweb="textarea"]>div,[data-baseweb="select"]>div{
  background:#fff!important;border-color:#e8dce2!important;border-radius:14px!important;color:#493f46!important;
}
[data-baseweb="input"] input,[data-baseweb="textarea"] textarea,[data-baseweb="select"] input{
  background:#fff!important;color:#493f46!important;-webkit-text-fill-color:#493f46!important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"],
.stMultiSelect [data-baseweb="tag"]{
  background-color:#f7e4ec!important;background-image:none!important;
  border:1px solid #e6bfd0!important;color:#754e60!important;
}
[class*="st-key-aop_games"] [data-baseweb="tag"]{
  background-color:#eaf3fa!important;border-color:#cddfeb!important;color:#526f82!important;
}
[class*="st-key-aop_oshi"] [data-baseweb="tag"]{
  background-color:#f7e4ec!important;border-color:#e6bfd0!important;color:#754e60!important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] *,
.stMultiSelect [data-baseweb="tag"] *{
  background-color:transparent!important;background-image:none!important;
  color:inherit!important;-webkit-text-fill-color:currentColor!important;fill:currentColor!important;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] button,
.stMultiSelect [data-baseweb="tag"] button{
  border:0!important;box-shadow:none!important;
}
[role="listbox"],[role="option"]{background:#fff!important;color:#493f46!important}
[role="option"]:hover,[aria-selected="true"]{background:#f8e9ef!important}
[data-testid="stFileUploaderDropzone"]{background:#fff!important;border-color:#e8dce2!important;border-radius:18px}
.stButton>button,.stDownloadButton>button{
  border-radius:999px!important;border:1px solid #ddb8c7!important;
  background:#f8e7ee!important;color:#754e60!important;-webkit-text-fill-color:#754e60!important;
}
.stButton>button:hover,.stDownloadButton>button:hover{background:#f2d8e3!important;border-color:#cfa5b6!important}
@media (max-width:700px){
  [class*="st-key-aop_games"] [data-baseweb="tag"],
  [class*="st-key-aop_games"] [data-baseweb="tag"]:hover{
    background-color:#eaf3fa!important;border-color:#cddfeb!important;color:#526f82!important;
  }
  [class*="st-key-aop_oshi"] [data-baseweb="tag"],
  [class*="st-key-aop_oshi"] [data-baseweb="tag"]:hover{
    background-color:#f7e4ec!important;border-color:#e6bfd0!important;color:#754e60!important;
  }
}
/* Final AOProfile chip override: BaseWeb uses different tag wrappers on mobile builds. */
[class*="st-key-aop_games"] :is(span,div)[data-baseweb="tag"],
[class*="st-key-aop_games"] [data-tag],
[class*="st-key-aop_games"] [data-testid="stMultiSelect"] :is(span,div)[data-baseweb="tag"]{
  background:#e8f3fb!important;background-color:#e8f3fb!important;background-image:none!important;
  border:1px solid #c8deed!important;box-shadow:none!important;
  color:#4f7087!important;-webkit-text-fill-color:#4f7087!important;
}
[class*="st-key-aop_oshi"] :is(span,div)[data-baseweb="tag"],
[class*="st-key-aop_oshi"] [data-tag],
[class*="st-key-aop_oshi"] [data-testid="stMultiSelect"] :is(span,div)[data-baseweb="tag"]{
  background:#f8e5ed!important;background-color:#f8e5ed!important;background-image:none!important;
  border:1px solid #e8bfd0!important;box-shadow:none!important;
  color:#7b5264!important;-webkit-text-fill-color:#7b5264!important;
}
[class*="st-key-aop_games"] :is(span,div)[data-baseweb="tag"] *,
[class*="st-key-aop_games"] [data-tag] *,
[class*="st-key-aop_oshi"] [data-tag] *,
[class*="st-key-aop_oshi"] :is(span,div)[data-baseweb="tag"] *{
  background:transparent!important;background-color:transparent!important;background-image:none!important;
  color:inherit!important;-webkit-text-fill-color:currentColor!important;fill:currentColor!important;
  box-shadow:none!important;
}
</style>
"""


def render_aoprofile_editor(characters, selected_ids, *, embedded: bool = True) -> None:
    """Render AOProfile while inheriting identities from the current session."""
    st.markdown(AOPROFILE_STYLE, unsafe_allow_html=True)
    if CARD_SIZE != (1080, 1620):
        st.error("AOProfile 高清渲染器尚未更新：请覆盖 utils/aoprofile_renderer_v3.py 后重启网站。")
        return
    if not BUNDLED_FONT_PATH.exists():
        st.error("AOProfile 云端字体缺失：请上传 assets/fonts/NotoSansSC-VF.ttf 后重启网站。")
        return
    by_id = {item.character_id: item for item in characters}
    selected = [by_id[cid] for cid in selected_ids if cid in by_id]

    if embedded and st.button("← 返回心动速配", key="aoprofile_back"):
        st.session_state.v6_view = "match"
        st.rerun()

    st.title("AOProfile")
    st.caption(f"分享图版本：{RENDERER_BUILD} · 喜欢的作品与推角均为一行三项")
    if not selected:
        st.info("请先返回心动速配选择角色并生成结果，再制作 AOProfile。")
        return

    xp_tags = representative_xp_tags(selected)
    inherited_names = [item.character_name for item in selected]
    games = sorted({item.game_title for item in characters})
    default_games = list(dict.fromkeys(item.game_title for item in selected))[:MAX_FAVORITE_GAMES]

    st.caption("已继承你刚才选择的角色和心动 XP，可以继续编辑自己的资料。")
    st.subheader("编辑资料")
    avatar = st.file_uploader("头像（可选）", type=["png", "jpg", "jpeg"], key="aop_avatar")
    cn = st.text_input("CN / 昵称", max_chars=MAX_CN, placeholder="你的常用名", key="aop_cn")
    contact = st.text_area("ID（可选）", max_chars=MAX_CONTACT, placeholder="小红书：xxxx\n微博：xxxx", height=85, key="aop_contact")
    favorite_games = st.multiselect("喜欢的作品（最多 6 部）", games, default=default_games, max_selections=MAX_FAVORITE_GAMES, key="aop_games")
    st.text_input("XP（自动继承）", value=" / ".join(xp_tags), disabled=True, key="aop_xp")
    oshi_names = st.multiselect("推 / 推し（自动继承，可移除）", options=inherited_names, default=inherited_names[:MAX_OSHI], max_selections=MAX_OSHI, key="aop_oshi")
    turn_offs = st.text_area("雷点（可选）", max_chars=MAX_TURN_OFFS, height=80, key="aop_turn_offs")
    note = st.text_area("留言板（可选）", max_chars=MAX_NOTE, placeholder="同担大欢迎 ♡", height=100, key="aop_note")

    if st.button("生成 AOProfile 分享图 ♡", type="primary", use_container_width=True, key="aop_generate"):
        try:
            profile = build_profile_data(cn, contact, favorite_games, xp_tags, oshi_names, turn_offs, note)
        except ValueError as exc:
            st.session_state.pop("aop_generated_png", None)
            st.session_state.pop("aop_generated_png_v2", None)
            st.session_state.pop("aop_generated_png_v4", None)
            st.session_state.pop("aop_generated_png_v5", None)
            st.session_state.pop("aop_generated_png_v6", None)
            st.session_state.pop("aop_generated_png_v7", None)
            st.warning(str(exc))
        else:
            st.session_state.pop("aop_generated_png", None)
            st.session_state.pop("aop_generated_png_v2", None)
            st.session_state.pop("aop_generated_png_v4", None)
            st.session_state.pop("aop_generated_png_v5", None)
            st.session_state.pop("aop_generated_png_v6", None)
            st.session_state.aop_generated_png_v7 = render_profile_png(
                profile,
                avatar.getvalue() if avatar else None,
            )

    png = st.session_state.get("aop_generated_png_v7")
    if png:
        st.subheader("分享图预览")
        st.caption(f"高清分享图 · {RENDERER_BUILD} · 1080 宽 · 自适应高度")
        st.image(BytesIO(png), use_container_width=True)
        st.download_button(
            "保存 AOProfile PNG",
            data=png,
            file_name="AOProfile_HD.png",
            mime="image/png",
            use_container_width=True,
            key="aop_download",
        )
