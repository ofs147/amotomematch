"""Renderers for the compact, downloadable AOMatch result card."""

from html import escape as xml_escape
from functools import lru_cache
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont


FONT_PATH = Path(__file__).resolve().parents[1] / "assets" / "fonts" / "NotoSansSC-VF.ttf"


def _text_width(text: str, *, wide: int = 30, narrow: int = 17) -> int:
    return sum(wide if ord(char) > 255 else narrow for char in text)


def _truncate(text: str, max_width: int) -> str:
    if _text_width(text) <= max_width:
        return text
    output = ""
    for char in text:
        if _text_width(output + char + "…") > max_width:
            break
        output += char
    return output + "…"


def _wrap(text: str, max_width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        if current and _text_width(current + char) > max_width:
            lines.append(current)
            current = char
            if len(lines) == max_lines:
                break
        else:
            current += char
    if len(lines) < max_lines and current:
        lines.append(current)
    consumed = "".join(lines)
    if len(consumed) < len(text.strip()) and lines:
        lines[-1] = _truncate(lines[-1] + "…", max_width)
    return lines


def _text_lines(
    lines: list[str], *, x: int, y: int, gap: int, css_class: str,
    text_anchor: str | None = None,
) -> str:
    anchor = f' text-anchor="{text_anchor}"' if text_anchor else ""
    return "".join(
        f'<text x="{x}" y="{y + index * gap}" class="{css_class}"{anchor}>{xml_escape(line)}</text>'
        for index, line in enumerate(lines)
    )


def _name_chips(selected) -> str:
    """Lay out all selectable characters in a stable two-column grid."""
    left = 86
    chip_width = 440
    column_gap = 28
    # Leave a clearer visual break between the section label and the names.
    first_y = 405
    row_height = 64
    chunks: list[str] = []
    for index, item in enumerate(selected[:10]):
        name = _truncate(item.character_name, 340)
        column = index % 2
        row = index // 2
        x = left + column * (chip_width + column_gap)
        y = first_y + row * row_height
        chunks.append(
            f'<g class="oshi-chip"><rect x="{x}" y="{y - 38}" width="{chip_width}" height="50" '
            f'rx="25"/><text x="{x + chip_width / 2:.1f}" y="{y - 4}" text-anchor="middle">'
            f'{xml_escape(name)}</text></g>'
        )
    return "".join(chunks)


def build_share_svg(result, selected) -> bytes:
    """Build a 3:4 share card that remains bounded with all 3–10 selections."""
    signals = [item.title for item in result.heart_signals[:3]] or ["多线心动型"]
    signal_count = len(signals)
    signal_gap = 18
    signal_width = (908 - signal_gap * (signal_count - 1)) / signal_count
    signal_rows = "".join(
        f'<g class="signal-card"><rect x="{86 + index * (signal_width + signal_gap):.1f}" y="770" '
        f'width="{signal_width:.1f}" height="148" rx="25"/>'
        f'<text x="{86 + signal_width / 2 + index * (signal_width + signal_gap):.1f}" y="814" text-anchor="middle">♡</text>'
        + _text_lines(
            _wrap(title, max(150, int(signal_width - 58)), 2),
            x=int(86 + signal_width / 2 + index * (signal_width + signal_gap)),
            y=862,
            gap=35,
            css_class="signal",
            text_anchor="middle",
        )
        + '</g>'
        for index, title in enumerate(signals)
    )
    summary_lines = _wrap(result.xp_personality, 820, 4)
    summary_svg = _text_lines(
        summary_lines,
        x=540,
        y=1049,
        gap=47,
        css_class="summary",
        text_anchor="middle",
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1080" height="1440" viewBox="0 0 1080 1440">
    <defs>
      <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff5f8"/><stop offset="0.52" stop-color="#fffdfb"/><stop offset="1" stop-color="#eef7ff"/></linearGradient>
      <filter id="shadow" x="-10%" y="-10%" width="120%" height="130%"><feDropShadow dx="0" dy="12" stdDeviation="18" flood-color="#b88aa0" flood-opacity=".16"/></filter>
    </defs>
    <rect width="1080" height="1440" fill="url(#bg)"/>
    <circle cx="1010" cy="110" r="185" fill="#f7dbe7" opacity=".52"/><circle cx="48" cy="1330" r="210" fill="#dfefff" opacity=".64"/>
    <rect x="48" y="48" width="984" height="1344" rx="48" fill="#fffdfd" stroke="#efdce5" stroke-width="2" filter="url(#shadow)"/>
    <style>
      text{{font-family:'Microsoft YaHei','PingFang SC','Noto Sans CJK SC',sans-serif;fill:#493b45}}
      .brand{{font-size:25px;letter-spacing:6px;fill:#b2768d;font-weight:700}}
      .title{{font-size:64px;font-weight:800;fill:#463640}}
      .subtitle{{font-size:27px;fill:#937c88}}
      .label{{font-size:24px;fill:#aa8394;font-weight:700;letter-spacing:3px}}
      .oshi-chip rect{{fill:#fff2f6;stroke:#efcbd9;stroke-width:2}}
      .oshi-chip text{{font-size:25px;font-weight:650;fill:#754f60}}
      .signal-card rect{{fill:#f9f5f8;stroke:#eee2e8;stroke-width:2}}
      .signal-card>text:first-of-type{{font-size:34px;fill:#db789d}}
      .signal{{font-size:27px;font-weight:700;fill:#765063}}
      .summary{{font-size:27px;font-weight:700;fill:#765063}}
      .footer{{font-size:23px;fill:#a18491}}
    </style>
    <text x="86" y="126" class="brand">AOMATCH</text>
    <text x="86" y="226" class="title">我的乙游心动讯号</text>
    <text x="88" y="277" class="subtitle">原来，我会反复为这样的角色心动。</text>
    <text x="86" y="337" class="label">这次选择</text>
    {_name_chips(selected)}
    <text x="86" y="730" class="label">心动关键词</text>
    {signal_rows}
    <text x="86" y="985" class="label">我的心动画像</text>
    {summary_svg}
    <line x1="86" y1="1310" x2="994" y2="1310" stroke="#eadde3" stroke-width="2"/>
    <text x="86" y="1354" class="footer">保存这张图，分享给懂你的人 ♡</text>
    <text x="994" y="1354" text-anchor="end" class="footer">AOMatch 心动速配</text>
    </svg>'''.encode("utf-8")


@lru_cache(maxsize=24)
def _png_font(size: int, bold: bool = False):
    font = ImageFont.truetype(str(FONT_PATH), size)
    if hasattr(font, "set_variation_by_name"):
        font.set_variation_by_name(b"Bold" if bold else b"Regular")
    return font


def _png_wrap(draw, text: str, font, max_width: int, max_lines: int) -> list[str]:
    lines: list[str] = []
    current = ""
    for char in text.strip():
        candidate = current + char
        width = draw.textbbox((0, 0), candidate, font=font)[2]
        if current and width > max_width:
            lines.append(current)
            current = char
            if len(lines) == max_lines:
                break
        else:
            current = candidate
    if len(lines) < max_lines and current:
        lines.append(current)
    consumed = "".join(lines)
    if len(consumed) < len(text.strip()) and lines:
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "…", font=font)[2] > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _png_centered_text(draw, box, text: str, font, fill: str) -> None:
    left, top, right, bottom = box
    bounds = draw.textbbox((0, 0), text, font=font)
    width = bounds[2] - bounds[0]
    height = bounds[3] - bounds[1]
    draw.text(
        ((left + right - width) / 2, (top + bottom - height) / 2 - bounds[1]),
        text,
        font=font,
        fill=fill,
    )


def _png_original_background() -> Image.Image:
    """Rasterize the original SVG's pink-white-blue wash and soft card shadow."""
    swatches = Image.new("RGB", (64, 64))
    pixels = swatches.load()
    pink, white, blue = (255, 245, 248), (255, 253, 251), (238, 247, 255)
    for y in range(64):
        for x in range(64):
            progress = (x / 63 + y / 63) / 2
            if progress <= 0.52:
                ratio = progress / 0.52
                start, end = pink, white
            else:
                ratio = (progress - 0.52) / 0.48
                start, end = white, blue
            pixels[x, y] = tuple(round(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3))
    image = swatches.resize((1080, 1440), Image.Resampling.BICUBIC).convert("RGBA")
    decoration = Image.new("RGBA", image.size, (0, 0, 0, 0))
    decoration_draw = ImageDraw.Draw(decoration)
    decoration_draw.ellipse((825, -75, 1195, 295), fill=(247, 219, 231, 133))
    decoration_draw.ellipse((-165, 1120, 255, 1540), fill=(223, 239, 255, 163))
    image = Image.alpha_composite(image, decoration)
    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((48, 60, 1032, 1404), radius=48, fill=(184, 138, 160, 41))
    image = Image.alpha_composite(image, shadow.filter(ImageFilter.GaussianBlur(18)))
    return image.convert("RGB")


def build_share_png(result, selected) -> bytes:
    """Build a real PNG while preserving the original SVG visual design."""
    image = _png_original_background()
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((48, 48, 1032, 1392), radius=48, fill="#fffdfd", outline="#efdce5", width=3)

    draw.text((86, 89), "AOMATCH", font=_png_font(25, True), fill="#b2768d")
    draw.text((86, 170), "我的乙游心动讯号", font=_png_font(64, True), fill="#463640")
    draw.text((88, 254), "原来，我会反复为这样的角色心动。", font=_png_font(27), fill="#937c88")
    label_font = _png_font(24, True)
    draw.text((86, 309), "这次选择", font=label_font, fill="#aa8394")

    chip_font = _png_font(25, True)
    for index, item in enumerate(selected[:10]):
        column, row = index % 2, index // 2
        x = 86 + column * 468
        y = 367 + row * 64
        box = (x, y, x + 440, y + 50)
        draw.rounded_rectangle(box, radius=25, fill="#fff2f6", outline="#efcbd9", width=2)
        name = item.character_name
        while name and draw.textbbox((0, 0), name, font=chip_font)[2] > 350:
            name = name[:-1]
        if name != item.character_name:
            name = name.rstrip() + "…"
        _png_centered_text(draw, box, name, chip_font, "#754f60")

    draw.text((86, 702), "心动关键词", font=label_font, fill="#aa8394")
    signals = [item.title for item in result.heart_signals[:3]] or ["多线心动型"]
    gap = 18
    width = int((908 - gap * (len(signals) - 1)) / len(signals))
    signal_font = _png_font(27, True)
    for index, title in enumerate(signals):
        x = 86 + index * (width + gap)
        box = (x, 750, x + width, 918)
        draw.rounded_rectangle(box, radius=25, fill="#f9f5f8", outline="#eee2e8", width=2)
        _png_centered_text(draw, (x, 763, x + width, 811), "♡", _png_font(34), "#db789d")
        lines = _png_wrap(draw, title, signal_font, width - 54, 2)
        for line_index, line in enumerate(lines):
            _png_centered_text(draw, (x + 18, 820 + line_index * 36, x + width - 18, 856 + line_index * 36), line, signal_font, "#765063")

    draw.text((86, 963), "我的心动画像", font=label_font, fill="#aa8394")
    summary_font = _png_font(27, True)
    summary_lines = _png_wrap(draw, result.xp_personality, summary_font, 820, 4)
    for index, line in enumerate(summary_lines):
        _png_centered_text(draw, (110, 1023 + index * 47, 970, 1068 + index * 47), line, summary_font, "#765063")

    draw.line((86, 1310, 994, 1310), fill="#eadde3", width=2)
    footer_font = _png_font(23)
    draw.text((86, 1330), "保存这张图，分享给懂你的人 ♡", font=footer_font, fill="#a18491")
    footer = "AOtomeMatch 心动速配"
    footer_width = draw.textbbox((0, 0), footer, font=footer_font)[2]
    draw.text((994 - footer_width, 1330), footer, font=footer_font, fill="#a18491")

    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
