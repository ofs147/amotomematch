"""Responsive, image-free result UI for the v6.4 Streamlit preview."""
from __future__ import annotations

from html import escape
import json
from typing import Mapping, Sequence

import streamlit as st

from utils.result_copy_v6 import (
    EXPLORATION_HEADING,
    HEART_SIGNALS_HEADING,
    HIGH_MATCH_HEADING,
    XP_PERSONALITY_HEADING,
)
from utils.tag_recommender_v6 import CharacterTags, HeartSignal, RecommendationCard, TagResult


STYLE = """
<style>
.v6-shell {max-width: 1120px; margin: 0 auto; color: #3f3540;}
.v6-hero {padding: 1.6rem 1.7rem; border: 1px solid #f1e5ea; border-radius: 24px;
  background: linear-gradient(125deg, #fffaf8 0%, #fff5f8 52%, #f5f9ff 100%);}
.v6-kicker {font-size: .78rem; letter-spacing: .12em; color: #a87386; text-transform: uppercase;}
.v6-hero h1 {font-size: clamp(1.65rem, 4vw, 2.35rem); margin: .35rem 0 .75rem;}
.v6-hero p {line-height: 1.85; margin: 0; max-width: 820px;}
.v6-section {margin-top: 2.15rem;}
.v6-section-title {font-size: 1.28rem; margin: 0 0 .9rem; color: #4d3d49;}
.v6-grid {display: grid; gap: 1rem; grid-template-columns: repeat(3, minmax(0, 1fr));}
.v6-grid.two {grid-template-columns: repeat(3, minmax(0, 1fr));}
.v6-grid.signal-count-1 {grid-template-columns: minmax(0, 420px);}
.v6-grid.signal-count-2 {grid-template-columns: repeat(2, minmax(0, 1fr)); max-width: 760px;}
.v6-grid.signal-count-3 {grid-template-columns: repeat(3, minmax(0, 1fr));}
.v6-card {box-sizing: border-box; min-height: 245px; padding: 1.15rem; border: 1px solid #eadde3;
  border-radius: 20px; background: #fffdfc; box-shadow: 0 7px 22px rgba(89,63,76,.055);}
.v6-card.pink {border-color: #ead5df; background: #fffafb;}
.v6-card.blue {border-color: #dce9f4; background: #fafdff;}
.v6-card h3 {font-size: 1.08rem; margin: .25rem 0 .15rem;}
.v6-game {font-size: .82rem; color: #8c7d86; margin-bottom: .8rem;}
.v6-signal-link {font-size: .82rem; color: #a5667c; margin: .72rem 0;}
.v6-reason {font-size: .93rem; line-height: 1.65;}
.v6-tags {display: flex; flex-wrap: wrap; gap: .42rem; margin: .7rem 0;}
.v6-pill {display: inline-block; padding: .25rem .58rem; border-radius: 999px;
  background: #f9e9ef; color: #87546a; font-size: .78rem; white-space: nowrap;}
.blue .v6-pill {background: #eaf3fb; color: #55748d;}
.v6-heart {color: #c9859d; font-size: .95rem;}
.v6-heart-card {min-height: 170px; padding: 1rem 1.05rem; border: 1px solid #eadfe7;
  border-radius: 19px; background: #fffafc;}
.v6-heart-card summary {cursor: pointer; list-style: none; font-weight: 650; line-height: 1.45;}
.v6-heart-card summary::-webkit-details-marker {display:none;}
.v6-evidence {border-top: 1px solid #f0e5ea; margin-top: .85rem; padding-top: .75rem;
  font-size: .86rem; line-height: 1.65;}
.v6-evidence-row {margin: .45rem 0;}
.v6-mini-title {font-weight: 650; color: #755664;}
.v6-expand-hint {margin: -.35rem 0 .85rem; color: #8c7d86; font-size: .86rem;}
.v6-open-cue {float:right; color:#a87386; font-size:.76rem; font-weight:500;}
.v6-fresh {margin-top: .75rem; padding-top: .65rem; border-top: 1px solid #e6eef5; font-size: .84rem;}
.v6-fresh-row {margin:.34rem 0; display:flex; align-items:center; gap:.45rem; flex-wrap:wrap;}
.v6-familiar-label, .v6-new-label {display:inline-block; border-radius:999px; padding:.18rem .5rem; font-weight:650; font-size:.76rem;}
.v6-familiar-label {background:#f8e6ed; color:#83576a;}
.v6-new-label {background:#e6f1fa; color:#52738d;}
.v6-bottom {margin: 2.2rem 0 1rem; padding: 1rem; border-radius: 18px; text-align: center;
  background: #f8f6f7; color: #756a71; font-size: .88rem;}
@media (max-width: 700px) {
  .v6-hero {padding: 1.25rem; border-radius: 20px;}
  .v6-grid, .v6-grid.two {display:flex; overflow-x:auto; scroll-snap-type:x mandatory;
    gap:.85rem; padding: .05rem 10vw .65rem 0; scrollbar-width:none;}
  .v6-grid::-webkit-scrollbar {display:none;}
  .v6-card, .v6-heart-card {flex: 0 0 86%; scroll-snap-align:start; min-height: 230px;}
  .v6-heart-card {min-height: 175px;}
}
</style>
"""


def _pills(tags: Sequence[str]) -> str:
    return '<div class="v6-tags">' + "".join(f'<span class="v6-pill">{escape(tag)}</span>' for tag in tags) + "</div>"


def heart_signal_html(signal: HeartSignal, selected_by_id: Mapping[str, CharacterTags]) -> str:
    evidence = []
    for character_id in signal.supporting_character_ids:
        character = selected_by_id[character_id]
        tags = signal.support_details.get(character_id, [])
        evidence.append(f'<div class="v6-evidence-row"><span class="v6-mini-title">{escape(character.character_name)}</span><br>{escape(" / ".join(tags))}</div>')
    return (
        '<details class="v6-heart-card">'
        f'<summary><span class="v6-heart">♡</span> {escape(signal.title)}<span class="v6-open-cue">点击展开 ↓</span>{_pills(signal.tags)}</summary>'
        '<div class="v6-evidence"><div class="v6-mini-title">这条心动讯号，是这些人一起暴露的 ♡</div>'
        + "".join(evidence)
        + f'<p>{escape(signal.explanation)}</p></div></details>'
    )


def recommendation_card_html(card: RecommendationCard, exploration: bool = False) -> str:
    extra = ""
    css = "v6-card blue" if exploration else "v6-card pink"
    reason = (
        card.reason
        .replace("这位，很对劲。", "")
        .replace("这位，很对劲", "")
        .replace("这位，有点偏，但偏得刚刚好。", "")
        .replace("这位，有点偏，但偏得刚刚好", "")
        .lstrip()
    )
    if exploration:
        extra = (
            '<div class="v6-fresh">'
            f'<div class="v6-fresh-row"><span class="v6-familiar-label">熟悉点</span>{escape(" / ".join(card.familiar_tags))}</div>'
            f'<div class="v6-fresh-row"><span class="v6-new-label">新鲜点</span>{escape(" / ".join(card.new_tags))}</div></div>'
        )
    return (
        f'<article class="{css}"><span class="v6-heart">♡</span>'
        f'<h3>{escape(card.character_name)}</h3><div class="v6-game">{escape(card.game_title)}</div>'
        f'{_pills(card.tags)}<div class="v6-signal-link">心动讯号｜{escape(card.heart_signal_title)}</div>'
        f'<div class="v6-reason">{escape(reason)}</div>{extra}</article>'
    )


def build_result_html(result: TagResult, selected: Sequence[CharacterTags]) -> str:
    selected_by_id = {item.character_id: item for item in selected}
    signals = "".join(heart_signal_html(item, selected_by_id) for item in result.heart_signals)
    high = "".join(recommendation_card_html(item) for item in result.high_matches)
    exploration = "".join(recommendation_card_html(item, True) for item in result.explorations)
    signal_section = (
        f'<section class="v6-section"><h2 class="v6-section-title">♡ {HEART_SIGNALS_HEADING}</h2>'
        '<p class="v6-expand-hint">点击任意一张心动讯号卡，查看是哪些角色共同暴露了这条偏好。</p>'
        f'<div class="v6-grid signal-count-{len(result.heart_signals)}">{signals}</div></section>' if signals else
        '<section class="v6-section"><h2 class="v6-section-title">♡ 心动讯号</h2><p>这次的选择很分散，还没有足够证据把你塞进固定支线。</p></section>'
    )
    return (
        STYLE + '<main class="v6-shell">'
        f'<section class="v6-hero"><div class="v6-kicker">AOMatch · Tag-first preview</div><h1>{XP_PERSONALITY_HEADING}</h1><p>{escape(result.xp_personality)}</p></section>'
        + signal_section
        + f'<section class="v6-section"><h2 class="v6-section-title">♡ {HIGH_MATCH_HEADING}</h2><div class="v6-grid">{high}</div></section>'
        + f'<section class="v6-section"><h2 class="v6-section-title">♡ {EXPLORATION_HEADING}</h2><div class="v6-grid two">{exploration}</div></section>'
        + '<div class="v6-bottom">喜欢结果的话，可以换一组心动角色再试一次。每次选择，都会暴露一点新的 XP ♡</div></main>'
    )


def render_result(result: TagResult, selected: Sequence[CharacterTags], debug: bool = False) -> None:
    st.markdown(build_result_html(result, selected), unsafe_allow_html=True)
    if debug:
        with st.expander("Debug · Tag-first pipeline"):
            st.caption(f"Mode: {result.mode}")
            st.json(result.debug)
