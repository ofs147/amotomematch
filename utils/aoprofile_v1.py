"""AOProfile v1 preview data shaping and portrait PNG rendering."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from typing import Iterable, Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps

from utils.tag_recommender_v6 import CharacterTags

MAX_CN = 30
MAX_CONTACT = 100
MAX_FAVORITE_GAMES = 6
MAX_OSHI = 10
MAX_TURN_OFFS = 120
MAX_NOTE = 200
CARD_SIZE = (1080, 1620)


def _draw_heart(draw: ImageDraw.ImageDraw, x: int, y: int, size: int, fill: str) -> None:
    """Draw a font-independent heart so exports never show a tofu square."""
    radius = max(2, size // 4)
    draw.ellipse((x - size // 2, y - size // 3, x, y - size // 3 + radius * 2), fill=fill)
    draw.ellipse((x, y - size // 3, x + size // 2, y - size // 3 + radius * 2), fill=fill)
    draw.polygon(((x - size // 2, y), (x + size // 2, y), (x, y + size // 2)), fill=fill)


def _draw_text_with_heart(
    draw: ImageDraw.ImageDraw,
    position: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    text_fill: str,
    heart_fill: str,
    heart_size: int,
    gap: int,
    anchor: str | None = None,
) -> None:
    """Place a vector heart from the rendered text bounds, not fixed guesses."""
    draw.text(position, text, font=font, fill=text_fill, anchor=anchor)
    bounds = draw.textbbox(position, text, font=font, anchor=anchor)
    visual_center_y = (bounds[1] + bounds[3]) // 2
    # _draw_heart extends slightly farther below its input centre.
    heart_y = visual_center_y - heart_size // 12
    _draw_heart(draw, bounds[2] + gap + heart_size // 2, heart_y, heart_size, heart_fill)


@dataclass(frozen=True)
class AOProfileData:
    cn: str
    contact: str
    favorite_games: tuple[str, ...]
    xp_tags: tuple[str, ...]
    oshi_names: tuple[str, ...]
    turn_offs: str
    note: str


def representative_xp_tags(selected: Sequence[CharacterTags], minimum: int = 4, maximum: int = 6) -> tuple[str, ...]:
    """Inherit representative tags from the selected liked characters."""
    counts: Counter[str] = Counter()
    first_seen: dict[str, int] = {}
    for character in selected:
        for tag in character.tags:
            counts[tag] += 1
            first_seen.setdefault(tag, len(first_seen))
    ranked = sorted(counts, key=lambda tag: (-counts[tag], first_seen[tag]))
    target = min(maximum, max(minimum, len(ranked)))
    return tuple(ranked[:target])


def build_profile_data(
    cn: str,
    contact: str,
    favorite_games: Iterable[str],
    xp_tags: Iterable[str],
    oshi_names: Iterable[str],
    turn_offs: str,
    note: str,
) -> AOProfileData:
    games = tuple(dict.fromkeys(game for game in favorite_games if game))
    tags = tuple(dict.fromkeys(tag for tag in xp_tags if tag))[:6]
    oshi = tuple(dict.fromkeys(name for name in oshi_names if name))
    if not cn.strip():
        raise ValueError("请填写 CN")
    if len(cn) > MAX_CN or len(contact) > MAX_CONTACT or len(turn_offs) > MAX_TURN_OFFS or len(note) > MAX_NOTE:
        raise ValueError("文字长度超过卡片限制")
    if not 1 <= len(games) <= MAX_FAVORITE_GAMES:
        raise ValueError("Favorite Games 请选择 1–6 部")
    if not tags:
        raise ValueError("My XP 必须继承至少一个标签")
    if not 1 <= len(oshi) <= MAX_OSHI:
        raise ValueError("My Oshi 请保留 1–10 位")
    return AOProfileData(cn.strip(), contact.strip(), games, tags, oshi, turn_offs.strip(), note.strip())


def serialize_profile(profile: AOProfileData) -> dict[str, object]:
    return asdict(profile)


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/msyhbd.ttc" if bold else "C:/Windows/Fonts/msyh.ttc"),
        Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit_text(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    if not text:
        return ""
    probe = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if probe.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text
    result = text
    while result and probe.textbbox((0, 0), result + "…", font=font)[2] > max_width:
        result = result[:-1]
    return result + "…"


def _chips(draw: ImageDraw.ImageDraw, values: Sequence[str], y: int, fill: str, max_rows: int = 2) -> int:
    font = _font(24)
    x, row, height = 70, 0, 48
    for value in values:
        label = _fit_text(value, font, 300)
        width = draw.textbbox((0, 0), label, font=font)[2] + 34
        if x + width > 830:
            row += 1
            if row >= max_rows:
                break
            x, y = 70, y + 58
        draw.rounded_rectangle((x, y, x + width, y + height), radius=24, fill=fill)
        draw.text((x + 17, y + 9), label, font=font, fill="#554a52")
        x += width + 12
    return y + height


def _avatar(image_bytes: bytes | None, size: int = 168) -> Image.Image:
    if not image_bytes:
        avatar = Image.new("RGBA", (size, size), "#f2e9ed")
        draw = ImageDraw.Draw(avatar)
        draw.ellipse((0, 0, size - 1, size - 1), fill="#f2e9ed", outline="#e5cfd8", width=3)
        _draw_heart(draw, size // 2, size // 2 - 5, 48, "#c897aa")
        return avatar
    with Image.open(BytesIO(image_bytes)) as source:
        source = ImageOps.exif_transpose(source).convert("RGB")
        fitted = ImageOps.fit(source, (size, size), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    avatar = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    avatar.paste(fitted, (0, 0), mask)
    return avatar


def render_profile_png(profile: AOProfileData, avatar_bytes: bytes | None = None) -> bytes:
    """Render the standalone 3:4 AOProfile card as PNG."""
    canvas = Image.new("RGB", CARD_SIZE, "#fff9fc")
    draw = ImageDraw.Draw(canvas)
    # A very soft pink-to-blue wash keeps the card airy without looking flat.
    start, end = (255, 247, 251), (242, 248, 255)
    for line_y in range(CARD_SIZE[1]):
        ratio = line_y / (CARD_SIZE[1] - 1)
        color = tuple(round(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3))
        draw.line((0, line_y, CARD_SIZE[0], line_y), fill=color)
    draw.ellipse((650, -105, 985, 230), fill="#e9f4fc")
    draw.ellipse((-145, 900, 205, 1250), fill="#f8e7ef")
    draw.ellipse((745, 1015, 940, 1210), outline="#dfedf8", width=3)
    # Layered border creates a restrained shadow that also exports reliably.
    for offset, fill in ((12, "#eadfe8"), (7, "#f0e7ed"), (3, "#f7f0f4")):
        draw.rounded_rectangle((32 + offset, 32 + offset, 868 + offset, 1168 + offset), radius=44, fill=fill)
    draw.rounded_rectangle((32, 32, 868, 1168), radius=44, fill="#fffdfd", outline="#e6d5de", width=3)

    # Header has its own quiet panel, avatar ring and small identity badge.
    draw.rounded_rectangle((56, 126, 844, 329), radius=31, fill="#fbf5f8", outline="#efe2e8", width=2)
    draw.rounded_rectangle((620, 72, 825, 112), radius=20, fill="#edf5fb")
    draw.text((722, 92), "OTOME PLAYER CARD", font=_font(15, True), fill="#738a9d", anchor="mm")
    _draw_text_with_heart(
        draw, (70, 72), "AOProfile", _font(43, True), "#7d5969", "#d39ab1", 22, 10
    )
    draw.ellipse((62, 137, 246, 321), fill="#fff", outline="#dfb9c9", width=4)
    avatar = _avatar(avatar_bytes)
    canvas.paste(avatar, (70, 145), avatar)
    draw.text((275, 160), "CN / 昵称", font=_font(18, True), fill="#a07889")
    draw.text((275, 194), _fit_text(profile.cn, _font(35, True), 540), font=_font(35, True), fill="#463c43")
    if profile.contact:
        draw.text((275, 252), "ID", font=_font(18, True), fill="#7d91a4")
        contact = profile.contact.replace("\r", " ").replace("\n", " · ")
        draw.text((275, 286), _fit_text(contact, _font(23), 540), font=_font(23), fill="#5e555b")

    y = 365
    draw.rounded_rectangle((58, y - 9, 842, y + 35), radius=18, fill="#fbf1f5")
    _draw_heart(draw, 79, y + 13, 18, "#d39ab1")
    draw.text((101, y), "喜欢的作品", font=_font(24, True), fill="#8c6374")
    y = _chips(draw, profile.favorite_games, y + 44, "#f8e8ef", 2) + 38
    draw.rounded_rectangle((58, y - 9, 842, y + 35), radius=18, fill="#f0f7fc")
    _draw_heart(draw, 79, y + 13, 18, "#8fb3cc")
    draw.text((101, y), "XP", font=_font(24, True), fill="#637f98")
    y = _chips(draw, profile.xp_tags, y + 44, "#eaf3fa", 2) + 38
    draw.rounded_rectangle((58, y - 9, 842, y + 35), radius=18, fill="#fbf1f5")
    _draw_heart(draw, 79, y + 13, 18, "#d39ab1")
    draw.text((101, y), "推 / 推し", font=_font(24, True), fill="#8c6374")
    y = _chips(draw, profile.oshi_names, y + 44, "#f7edf1", 2) + 38
    if profile.turn_offs:
        draw.rounded_rectangle((58, y - 9, 842, y + 35), radius=18, fill="#f0f7fc")
        _draw_heart(draw, 79, y + 13, 18, "#8fb3cc")
        draw.text((101, y), "雷点", font=_font(24, True), fill="#637f98")
        turn_offs = profile.turn_offs.replace("\r", " ").replace("\n", "  ")
        y += 39
        draw.text((70, y), _fit_text(turn_offs, _font(23), 750), font=_font(23), fill="#5e555b")
        y += 54
    if profile.note:
        draw.rounded_rectangle((58, y - 9, 842, y + 35), radius=18, fill="#fbf1f5")
        _draw_heart(draw, 79, y + 13, 18, "#d39ab1")
        draw.text((101, y), "留言板", font=_font(24, True), fill="#8c6374")
        note = profile.note.replace("\r", " ").replace("\n", "  ")
        words, lines, current = list(note), [], ""
        for char in words:
            if draw.textbbox((0, 0), current + char, font=_font(23))[2] > 750:
                lines.append(current)
                current = char
            else:
                current += char
        if current:
            lines.append(current)
        for line in lines[:2]:
            y += 35
            draw.text((70, y), line, font=_font(23), fill="#5e555b")

    draw.line((92, 1092, 808, 1092), fill="#eadde4", width=2)
    draw.ellipse((76, 1087, 86, 1097), fill="#dca9bc")
    draw.ellipse((814, 1087, 824, 1097), fill="#b9d5e8")
    _draw_text_with_heart(
        draw, (440, 1124), "Made with AOMatch", _font(18), "#a88d9a", "#d39ab1", 14, 7, "mm"
    )
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _wrap_card_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, width: int, lines: int = 2) -> list[str]:
    """Wrap CJK/Latin display names without prematurely replacing them with ellipses."""
    normalized = " ".join(str(text).split())
    if not normalized:
        return [""]
    wrapped: list[str] = []
    current = ""
    for character in normalized:
        candidate = current + character
        if current and draw.textbbox((0, 0), candidate, font=font)[2] > width:
            wrapped.append(current)
            current = character
        else:
            current = candidate
    if current:
        wrapped.append(current)
    if len(wrapped) <= lines:
        return wrapped
    kept = wrapped[:lines]
    overflow = "".join(wrapped[lines - 1 :])
    while overflow and draw.textbbox((0, 0), overflow + "…", font=font)[2] > width:
        overflow = overflow[:-1]
    kept[-1] = overflow + "…"
    return kept


def _profile_section(draw: ImageDraw.ImageDraw, y: int, title: str, tone: str) -> int:
    palette = {
        "pink": ("#fbf0f5", "#8c6374", "#d39ab1"),
        "blue": ("#edf6fc", "#58788f", "#8fb3cc"),
    }
    background, text_color, heart_color = palette[tone]
    draw.rounded_rectangle((68, y, 1012, y + 54), radius=22, fill=background)
    _draw_heart(draw, 94, y + 27, 21, heart_color)
    draw.text((124, y + 8), title, font=_font(30, True), fill=text_color)
    return y + 68


def _profile_grid(
    draw: ImageDraw.ImageDraw,
    values: Sequence[str],
    y: int,
    *,
    columns: int,
    fill: str,
    outline: str,
    font_size: int,
    row_height: int,
    max_lines: int = 1,
) -> int:
    gap = 14
    left, right = 76, 1004
    width = (right - left - gap * (columns - 1)) // columns
    font = _font(font_size, True)
    rows = (len(values) + columns - 1) // columns
    for index, value in enumerate(values):
        row, column = divmod(index, columns)
        x = left + column * (width + gap)
        top = y + row * (row_height + 12)
        draw.rounded_rectangle((x, top, x + width, top + row_height), radius=22, fill=fill, outline=outline, width=2)
        lines = _wrap_card_text(draw, value, font, width - 34, max_lines)
        line_height = font_size + 7
        text_height = len(lines) * line_height
        text_y = top + (row_height - text_height) // 2
        for line in lines:
            draw.text((x + 17, text_y), line, font=font, fill="#514850")
            text_y += line_height
    return y + rows * (row_height + 12)


def render_profile_png(profile: AOProfileData, avatar_bytes: bytes | None = None) -> bytes:
    """Render a phone-readable AOProfile card without dropping long game names."""
    canvas = Image.new("RGB", CARD_SIZE, "#fff8fc")
    draw = ImageDraw.Draw(canvas)
    start, end = (255, 247, 251), (239, 247, 254)
    for line_y in range(CARD_SIZE[1]):
        ratio = line_y / (CARD_SIZE[1] - 1)
        color = tuple(round(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3))
        draw.line((0, line_y, CARD_SIZE[0], line_y), fill=color)
    draw.ellipse((770, -130, 1160, 260), fill="#e7f3fb")
    draw.ellipse((-170, 1290, 210, 1670), fill="#f7e5ee")
    draw.rounded_rectangle((38, 38, 1042, 1582), radius=52, fill="#fffdfd", outline="#e5d4dd", width=3)

    _draw_text_with_heart(draw, (74, 72), "AOProfile", _font(54, True), "#765463", "#d39ab1", 26, 13)
    draw.rounded_rectangle((764, 76, 1004, 122), radius=23, fill="#edf5fb")
    draw.text((884, 99), "OTOME PLAYER CARD", font=_font(18, True), fill="#6d8799", anchor="mm")

    draw.rounded_rectangle((68, 148, 1012, 350), radius=34, fill="#fbf4f8", outline="#eedfe7", width=2)
    draw.ellipse((84, 161, 276, 353), fill="#fff", outline="#dfb9c9", width=4)
    avatar = _avatar(avatar_bytes, 176)
    canvas.paste(avatar, (92, 169), avatar)
    draw.text((310, 174), "CN / 昵称", font=_font(24, True), fill="#9a7182")
    cn_lines = _wrap_card_text(draw, profile.cn, _font(42, True), 650, 1)
    draw.text((310, 213), cn_lines[0], font=_font(42, True), fill="#443b41")
    if profile.contact:
        draw.text((310, 278), "ID", font=_font(22, True), fill="#71899b")
        contact = profile.contact.replace("\r", " ").replace("\n", " · ")
        contact_line = _wrap_card_text(draw, contact, _font(27), 650, 1)[0]
        draw.text((352, 273), contact_line, font=_font(27), fill="#5c5459")

    y = 382
    y = _profile_section(draw, y, "喜欢的作品", "pink")
    y = _profile_grid(draw, profile.favorite_games, y, columns=2, fill="#f9e9f0", outline="#ebcbd8", font_size=27, row_height=82, max_lines=2) + 12
    y = _profile_section(draw, y, "XP", "blue")
    y = _profile_grid(draw, profile.xp_tags, y, columns=3, fill="#eaf3fa", outline="#cfe1ee", font_size=28, row_height=58) + 12
    y = _profile_section(draw, y, "推 / 推し", "pink")
    y = _profile_grid(draw, profile.oshi_names, y, columns=2, fill="#f7eaf0", outline="#e9cbd7", font_size=29, row_height=60) + 10

    if profile.turn_offs:
        y = _profile_section(draw, y, "雷点", "blue")
        for line in _wrap_card_text(draw, profile.turn_offs, _font(27, True), 900, 2):
            draw.text((82, y), line, font=_font(27, True), fill="#514850")
            y += 37
        y += 8
    if profile.note and y < 1470:
        y = _profile_section(draw, y, "留言板", "pink")
        for line in _wrap_card_text(draw, profile.note, _font(27, True), 900, 2):
            draw.text((82, y), line, font=_font(27, True), fill="#514850")
            y += 37

    footer_y = 1540
    draw.line((106, footer_y - 22, 974, footer_y - 22), fill="#eadde4", width=2)
    _draw_text_with_heart(draw, (540, footer_y), "Made with AOtomeMatch", _font(22, True), "#9b7d8b", "#d39ab1", 16, 9, "mm")
    output = BytesIO()
    canvas.save(output, format="PNG", optimize=True)
    return output.getvalue()
