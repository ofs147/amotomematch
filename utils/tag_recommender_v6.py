"""Deterministic Tag-first profile, retrieval, and recommendation for v6.4."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import math
from pathlib import Path
import re
from typing import Iterable, Mapping, Sequence

import pandas as pd

from utils.result_copy_v6 import (
    TAG_HEART_TITLES,
    fallback_heart_title,
    heart_title_candidates,
    heart_title_concept,
)

GENERIC_TAGS = {"成熟可靠", "温柔", "稳定恋爱", "陪伴成长", "理性沉稳", "少年感"}
ANCHOR_IDS = {"C001", "C004", "C005", "C011", "C012"}
CANONICAL_NAME_STYLE_GAMES: set[str] = set()
# 宿命感 is a particularly strong relationship-identity signal.  The boost is
# deliberately moderate: it wins ties and close calls, but cannot manufacture
# evidence or outrank a tag supported by substantially more selected characters.
HEART_SIGNAL_TAG_PRIORITY = {"宿命感": 1.4}


def _heart_signal_priority(tag: str) -> float:
    return HEART_SIGNAL_TAG_PRIORITY.get(tag, 1.0)


@dataclass(frozen=True)
class CharacterTags:
    character_id: str
    character_name: str
    game_title: str
    tags: tuple[str, ...]


@dataclass
class HeartSignal:
    signal_id: str
    title: str
    tags: list[str]
    supporting_character_ids: list[str]
    support_details: dict[str, list[str]]
    explanation: str


@dataclass
class RetrievedCandidate:
    character: CharacterTags
    score: float
    matched_tags: list[str]
    branch_hits: list[str]
    rarity_score: float
    combination_score: float


@dataclass
class RecommendationCard:
    character_id: str
    character_name: str
    game_title: str
    tags: list[str]
    heart_signal_id: str
    heart_signal_title: str
    reason: str
    familiar_tags: list[str] = field(default_factory=list)
    new_tags: list[str] = field(default_factory=list)


@dataclass
class TagResult:
    xp_personality: str
    heart_signals: list[HeartSignal]
    high_matches: list[RecommendationCard]
    explorations: list[RecommendationCard]
    mode: str
    debug: dict[str, object] = field(default_factory=dict)


def load_tag_characters(
    tag_path: Path,
    review_path: Path,
    display_names_path: Path | None = None,
    series_names_path: Path | None = None,
) -> list[CharacterTags]:
    """Load canonical Tag rows and apply the existing UI-only Chinese labels."""
    tags = pd.read_csv(tag_path, dtype=str, keep_default_na=False)
    review = pd.read_csv(review_path, dtype=str, keep_default_na=False)
    names = review.set_index("character_id")[["character_name", "game"]].to_dict("index")
    expansion_path = review_path.parent / "core_xp_tags_v6_5_expansion_draft.csv"
    if expansion_path.exists():
        expansion = pd.read_csv(expansion_path, dtype=str, keep_default_na=False)
        approved = expansion[expansion["status"].isin({"AUTO_PASS", "HUMAN_CALIBRATED"})]
        # The primary review file is authoritative.  Expansion drafts only fill
        # identities that have not yet been promoted, never overwrite them.
        for character_id, identity in approved.set_index("character_id")[["character_name", "game"]].to_dict("index").items():
            names.setdefault(character_id, identity)
    display_names_path = display_names_path or review_path.parent / "character_display_names_zh.csv"
    series_names_path = series_names_path or review_path.parent / "series_display_names_zh.csv"
    display_names: dict[str, str] = {}
    series_names: dict[str, str] = {}
    if display_names_path.exists():
        display_rows = pd.read_csv(display_names_path, dtype=str, keep_default_na=False)
        display_names = dict(zip(display_rows["character_id"], display_rows["display_name_zh"]))
    if series_names_path.exists():
        series_rows = pd.read_csv(series_names_path, dtype=str, keep_default_na=False)
        series_names = dict(zip(series_rows["source_series"], series_rows["display_title"]))
    characters = []
    for row in tags.to_dict("records"):
        character_id = row["character_id"]
        if character_id not in names:
            raise ValueError(f"Missing reviewed identity for {character_id}")
        core_tags = tuple(value for value in (row["core_tag_1"], row["core_tag_2"], row["core_tag_3"]) if value)
        canonical_name = names[character_id]["character_name"]
        canonical_game = names[character_id]["game"]
        display_game = series_names.get(canonical_game, canonical_game)
        display_name = (
            canonical_name
            if display_game in CANONICAL_NAME_STYLE_GAMES
            else display_names.get(character_id) or canonical_name
        )
        characters.append(
            CharacterTags(
                character_id,
                display_name,
                display_game,
                core_tags,
            )
        )
    if len(characters) != len({item.character_id for item in characters}):
        raise ValueError("Duplicate character_id in Tag-first pool")
    return characters


def compute_idf(characters: Sequence[CharacterTags]) -> dict[str, float]:
    document_frequency = Counter(tag for character in characters for tag in set(character.tags))
    total = len(characters)
    return {tag: math.log((total + 1) / (count + 1)) + 1 for tag, count in document_frequency.items()}


def _tag_support(selected: Sequence[CharacterTags]) -> dict[str, set[str]]:
    support: dict[str, set[str]] = defaultdict(set)
    for character in selected:
        for tag in character.tags:
            support[tag].add(character.character_id)
    return support


def normalize_signal_tags(tags: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({tag.strip() for tag in tags if tag and tag.strip()}))


def normalize_signal_title(title: str) -> str:
    """Normalize cosmetic punctuation/spacing before title uniqueness checks."""
    normalized = re.sub(r"\s+", "", title.strip())
    return re.sub(r"[，,。.!！?？、；;：:·—_]+", "", normalized)


def _overlap(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / min(len(left), len(right))


def _jaccard(left: set[str], right: set[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


def select_diverse_heart_signals(
    candidates: Sequence[tuple[HeartSignal, float]],
    maximum: int = 3,
    debug: dict[str, object] | None = None,
) -> list[HeartSignal]:
    """Rank, exact-deduplicate, and filter evidence-level near duplicates."""
    ordered = sorted(
        candidates,
        key=lambda item: (
            -item[1],
            -len(item[0].supporting_character_ids),
            normalize_signal_tags(item[0].tags),
        ),
    )
    exact_seen: set[tuple[str, ...]] = set()
    retained: list[tuple[HeartSignal, float]] = []
    decisions: list[dict[str, object]] = []
    comparisons: list[dict[str, object]] = []
    for signal, strength in ordered:
        normalized_tags = normalize_signal_tags(signal.tags)
        if normalized_tags in exact_seen:
            decisions.append({"signal_id": signal.signal_id, "action": "DROP", "reason": "EXACT_TAG_SET", "normalized_tags": normalized_tags})
            continue
        exact_seen.add(normalized_tags)
        duplicate_of = None
        for kept, kept_strength in retained:
            tag_overlap = _overlap(set(normalized_tags), set(normalize_signal_tags(kept.tags)))
            supporter_overlap = _jaccard(set(signal.supporting_character_ids), set(kept.supporting_character_ids))
            comparison = {
                "left": signal.signal_id,
                "right": kept.signal_id,
                "tag_overlap": round(tag_overlap, 3),
                "supporter_overlap": round(supporter_overlap, 3),
            }
            comparisons.append(comparison)
            # Three of four tags (or all tags) plus nearly identical evidence is
            # one attraction reason. Two-of-three overlap alone remains allowed.
            if tag_overlap >= 0.75 and supporter_overlap >= 0.75:
                duplicate_of = kept.signal_id
                break
        if duplicate_of:
            decisions.append({"signal_id": signal.signal_id, "action": "DROP", "reason": "NEAR_DUPLICATE", "duplicate_of": duplicate_of, "normalized_tags": normalized_tags})
            continue
        retained.append((signal, strength))
        decisions.append({"signal_id": signal.signal_id, "action": "KEEP", "reason": "DISTINCT", "normalized_tags": normalized_tags})
    final = [signal for signal, _ in retained[:maximum]]
    if debug is not None:
        debug["candidate_heart_signals"] = [
            {
                "signal_id": signal.signal_id,
                "tags": signal.tags,
                "normalized_tags": normalize_signal_tags(signal.tags),
                "supporting_character_ids": signal.supporting_character_ids,
                "strength": round(strength, 4),
            }
            for signal, strength in ordered
        ]
        debug["heart_signal_overlap"] = comparisons
        debug["heart_signal_dedup"] = decisions
        debug["final_heart_signals"] = [signal.signal_id for signal in final]
    return final


def ensure_unique_signal_titles(signals: Sequence[HeartSignal]) -> list[HeartSignal]:
    """Give every branch distinct wording and a distinct semantic headline."""
    used: set[str] = set()
    used_concepts: set[str] = set()
    result = []
    for index, signal in enumerate(signals):
        title = signal.title.strip()
        normalized = normalize_signal_title(title)
        concept = heart_title_concept(title, signal.tags)
        if normalized in used or (concept is not None and concept in used_concepts):
            unused_tag = next(
                (tag for tag in signal.tags if tag not in used_concepts and tag in TAG_HEART_TITLES),
                None,
            )
            alternatives = heart_title_candidates(signal.tags, index)
            if unused_tag:
                title = TAG_HEART_TITLES[unused_tag]
                concept = unused_tag
            else:
                title = next(
                    (candidate for candidate in alternatives if normalize_signal_title(candidate) not in used),
                    f"{'与'.join(signal.tags)}，构成了另一种心动",
                )
                concept = heart_title_concept(title, signal.tags)
            normalized = normalize_signal_title(title)
        used.add(normalized)
        if concept:
            used_concepts.add(concept)
        signal.title = title
        result.append(signal)
    return result


def build_heart_signals(
    selected: Sequence[CharacterTags], idf: Mapping[str, float], maximum: int = 3,
    debug: dict[str, object] | None = None,
) -> list[HeartSignal]:
    """Build evidence-backed signals; single-character patterns are not promoted."""
    support = _tag_support(selected)
    seeds = sorted(
        (tag for tag, ids in support.items() if len(ids) >= 2),
        key=lambda tag: (
            -(len(support[tag]) * _heart_signal_priority(tag)),
            -len(support[tag]),
            -idf.get(tag, 1.0),
            tag,
        ),
    )
    candidates: list[tuple[HeartSignal, float]] = []
    for seed in seeds:
        supporters = support[seed]
        related = Counter()
        for character in selected:
            if character.character_id in supporters:
                for tag in character.tags:
                    if tag != seed:
                        related[tag] += 1
        additions = sorted(
            related,
            key=lambda tag: (-related[tag], -idf.get(tag, 1.0), tag),
        )[:3]
        signal_tags = [seed, *additions]
        signal_tags.sort(
            key=lambda tag: (
                -(len(support.get(tag, set())) * _heart_signal_priority(tag)),
                -len(support.get(tag, set())),
                -idf.get(tag, 1.0),
                tag,
            )
        )
        support_ids = sorted(set().union(*(support.get(tag, set()) for tag in signal_tags)))
        details = {
            character.character_id: [tag for tag in character.tags if tag in signal_tags]
            for character in selected
            if character.character_id in support_ids
        }
        index = len(candidates)
        title = fallback_heart_title(signal_tags, index)
        tag_phrase = "、".join(signal_tags[:2])
        explanation_templates = (
            f"{tag_phrase}在你的选择里同时出现了好几次。比起某一种固定外形，你更容易被这种相处气质持续吸引。",
            f"把这些人放在一起看，{tag_phrase}是最清楚的共同点。它像你的心动开关，一出现就很难忽略。",
            f"你选中的角色看似不同，却都把{tag_phrase}放在了关系体验的中心。这更像稳定偏好，而不是临时起意。",
            f"{tag_phrase}反复连接起你喜欢的角色。你在意的不只是角色设定，更是他们带来的这类情绪体验。",
            f"这组选择共同指向{tag_phrase}：角色可以来自不同世界，但踩中这两个点时，你的注意力会明显停留。",
        )
        explanation = explanation_templates[index % len(explanation_templates)]
        signal = HeartSignal(f"signal_candidate_{index + 1}", title, signal_tags[:4], support_ids, details, explanation)
        cooccurrence_strength = sum(related[tag] for tag in additions)
        priority_bonus = (HEART_SIGNAL_TAG_PRIORITY.get(seed, 1.0) - 1.0) * 3
        strength = len(supporters) * 3 + cooccurrence_strength + sum(idf.get(tag, 1.0) for tag in signal.tags) + priority_bonus
        candidates.append((signal, strength))
    retained = select_diverse_heart_signals(candidates, maximum, debug)
    for index, signal in enumerate(retained, 1):
        signal.signal_id = f"signal_{index}"
    if debug is not None:
        debug["final_heart_signals"] = [
            {
                "signal_id": signal.signal_id,
                "tags": signal.tags,
                "supporting_character_ids": signal.supporting_character_ids,
            }
            for signal in retained
        ]
    return ensure_unique_signal_titles(retained)


def retrieve_candidates(
    selected: Sequence[CharacterTags], eligible: Sequence[CharacterTags], signals: Sequence[HeartSignal], limit: int = 20
) -> list[RetrievedCandidate]:
    if not 15 <= limit <= 20:
        raise ValueError("Retrieval limit must be between 15 and 20")
    selected_ids = {item.character_id for item in selected}
    selected_games = {item.game_title for item in selected}
    selected_tags = Counter(tag for item in selected for tag in item.tags)
    idf = compute_idf(eligible)
    selected_pairs = Counter(
        tuple(sorted((left, right)))
        for item in selected
        for index, left in enumerate(item.tags)
        for right in item.tags[index + 1 :]
    )
    ranked: list[RetrievedCandidate] = []
    for character in eligible:
        if character.character_id in selected_ids or character.game_title in selected_games:
            continue
        matched = [tag for tag in character.tags if tag in selected_tags]
        rarity = sum(idf[tag] * (1 + math.log1p(selected_tags[tag])) for tag in matched)
        generic_penalty = sum(0.22 for tag in matched if tag in GENERIC_TAGS)
        pair_score = sum(
            0.45 * selected_pairs.get(tuple(sorted((left, right))), 0)
            for index, left in enumerate(character.tags)
            for right in character.tags[index + 1 :]
        )
        hits = []
        branch_bonus = 0.0
        for signal in signals:
            overlap = set(character.tags) & set(signal.tags)
            if overlap:
                hits.append(signal.signal_id)
                branch_bonus += 1.15 * len(overlap) + (1.3 if len(overlap) >= 2 else 0)
        score = rarity + pair_score + branch_bonus - generic_penalty
        ranked.append(RetrievedCandidate(character, round(score, 5), matched, hits, round(rarity, 5), round(pair_score, 5)))
    ranked.sort(key=lambda item: (-item.score, -len(item.matched_tags), item.character.character_id))
    result = ranked[: min(limit, len(ranked))]
    selected_tag_set = set(selected_tags)
    def exploration_viable(item: RetrievedCandidate) -> bool:
        familiar = [tag for tag in item.character.tags if tag in selected_tag_set]
        novel = [tag for tag in item.character.tags if tag not in selected_tag_set]
        return bool(familiar and novel)
    viable_in_result = [item for item in result if exploration_viable(item)]
    if len(viable_in_result) < 3:
        additions = [item for item in ranked[len(result) :] if exploration_viable(item)]
        needed = min(3 - len(viable_in_result), len(additions))
        if needed:
            result[-needed:] = additions[:needed]
            result.sort(key=lambda item: (-item.score, -len(item.matched_tags), item.character.character_id))
    return result


def _signal_for(candidate: RetrievedCandidate, signals: Sequence[HeartSignal]) -> HeartSignal | None:
    return max(signals, key=lambda signal: (len(set(candidate.character.tags) & set(signal.tags)), -signals.index(signal)), default=None)


def _high_match_cards(pool: Sequence[RetrievedCandidate], signals: Sequence[HeartSignal], count: int = 5) -> list[RecommendationCard]:
    chosen: list[RetrievedCandidate] = []
    remaining = list(pool)
    # Give each evidence-backed branch its best full/partial hit before filling
    # remaining slots. This prevents a broad generic cluster from taking all cards.
    for signal in signals:
        aligned = [item for item in remaining if set(item.character.tags) & set(signal.tags)]
        if not aligned or len(chosen) >= count:
            continue
        candidate = max(
            aligned,
            key=lambda item: (len(set(item.character.tags) & set(signal.tags)), item.score, item.character.character_id),
        )
        chosen.append(candidate)
        remaining.remove(candidate)
    while remaining and len(chosen) < count:
        candidate = max(remaining, key=lambda item: (item.score, len(item.matched_tags), item.character.character_id))
        chosen.append(candidate)
        remaining.remove(candidate)
    cards = []
    for candidate in chosen:
        signal = _signal_for(candidate, signals)
        matched = candidate.matched_tags[:3]
        reason = (
            f"{'、'.join(matched)}刚好踩中你的心动讯号，角色魅力落点鲜明，不需要面面俱到也足够让人记住。"
            if matched else "他的标签组合和你的主要心动支线靠得很近，可能会是意料之外却很顺眼的一位。"
        )
        cards.append(RecommendationCard(candidate.character.character_id, candidate.character.character_name, candidate.character.game_title, list(candidate.character.tags), signal.signal_id if signal else "", signal.title if signal else "相邻心动支线", reason))
    return cards


def _exploration_cards(
    pool: Sequence[RetrievedCandidate], excluded_ids: set[str], selected_tags: set[str], signals: Sequence[HeartSignal], count: int = 3
) -> list[RecommendationCard]:
    viable = []
    for candidate in pool:
        if candidate.character.character_id in excluded_ids:
            continue
        familiar = [tag for tag in candidate.character.tags if tag in selected_tags][:2]
        new = [tag for tag in candidate.character.tags if tag not in selected_tags][:2]
        if 1 <= len(familiar) <= 2 and 1 <= len(new) <= 2:
            viable.append((candidate, familiar, new))
    viable.sort(key=lambda item: (-len(item[1]), -item[0].score, -sum(compute_idf([x.character for x in pool]).get(tag, 1) for tag in item[2]), item[0].character.character_id))
    cards = []
    for candidate, familiar, new in viable[:count]:
        signal = _signal_for(candidate, signals)
        reason = f"保留了你熟悉的{'、'.join(familiar)}，又带来{'、'.join(new)}，像一条值得试试的新支线。"
        cards.append(RecommendationCard(candidate.character.character_id, candidate.character.character_name, candidate.character.game_title, list(candidate.character.tags), signal.signal_id if signal else "", signal.title if signal else "相邻心动支线", reason, familiar, new))
    return cards


def fallback_xp_personality(selected: Sequence[CharacterTags], signals: Sequence[HeartSignal]) -> str:
    if signals:
        branch_text = "，也会被".join("、".join(signal.tags[:2]) for signal in signals)
        return (
            f"你其实不只固定吃一种男人。{branch_text}这样的关系气质都能戳到你。"
            "比起标准答案，你更在意一个角色谈起恋爱时有没有鲜明存在感。"
            "只要某条心动支线踩得够准，你就很愿意跟着感觉走。"
        )
    common = Counter(tag for item in selected for tag in item.tags).most_common(3)
    tags = "、".join(tag for tag, _ in common)
    return f"你选中的人暂时没有暴露出一条重复到足够明显的主线，但{tags}已经悄悄留下痕迹。你的 XP 更像多条支线并行，宁可保留复杂，也不急着被一个标签概括。"


def build_fallback_result(selected: Sequence[CharacterTags], eligible: Sequence[CharacterTags], retrieval_limit: int = 20) -> TagResult:
    idf = compute_idf(eligible)
    signal_debug: dict[str, object] = {}
    signals = build_heart_signals(selected, idf, debug=signal_debug)
    pool = retrieve_candidates(selected, eligible, signals, retrieval_limit)
    high = _high_match_cards(pool, signals, 5)
    selected_tags = {tag for item in selected for tag in item.tags}
    explorations = _exploration_cards(pool, {card.character_id for card in high}, selected_tags, signals, 3)
    return TagResult(
        fallback_xp_personality(selected, signals), signals, high, explorations, "FALLBACK",
        {
            "tag_frequency": dict(Counter(tag for item in selected for tag in item.tags)),
            "idf": {tag: round(value, 4) for tag, value in idf.items()},
            "retrieved": [
                {"character_id": item.character.character_id, "game_title": item.character.game_title, "score": item.score, "matched_tags": item.matched_tags, "branch_hits": item.branch_hits}
                for item in pool
            ],
            "excluded_selected_games": sorted({item.game_title for item in selected}),
            "heart_signal_support": {signal.signal_id: len(signal.supporting_character_ids) for signal in signals},
            **signal_debug,
        },
    )
