"""Optional direct AOProfile route; the main app uses an embedded view."""

from pathlib import Path

import streamlit as st

from utils.aoprofile_ui import render_aoprofile_editor
from utils.tag_recommender_v6 import load_tag_characters


BASE_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BASE_DIR / "data"

st.set_page_config(page_title="AOProfile", page_icon="♡", layout="centered")


@st.cache_data(show_spinner=False)
def load_catalog():
    return load_tag_characters(
        DATA_DIR / "core_xp_tags_v6.csv",
        DATA_DIR / "core_xp_tags_v6_2_review.csv",
    )


render_aoprofile_editor(
    load_catalog(),
    st.session_state.get("v6_selected_ids", []),
    embedded=False,
)
