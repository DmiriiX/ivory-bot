#!/usr/bin/env python3
"""Render the six-card Instagram Facts series and its editorial revisions."""
import json
import math
import random
import sys
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin-panel"))

from instagram_fact_layout import BODY_FONT, PARAGRAPH_GAP, fact_font, fact_text_pages, line_height
from instagram_facts import FACTS, FACT_SLIDE_COUNT, fact_slide_names, fact_slide_text

OUT = ROOT / "instagram-media" / "facts"
W, H = 1080, 1350
LEFT, RIGHT = 90, 990
IVORY = "#f2e3bc"
PAPER = "#f3ead7"
GOLD = "#cbb17e"
ACCENT = "#e7c98d"
MUTED = "#b7a894"
RULE = "#514635"
SERIF = "CormorantGaramond-Medium.otf"
ITALIC = "CormorantGaramond-Italic.otf"
LOGO = "Cinzel.ttf"


@lru_cache(maxsize=3)
def backdrop(strength):
    """Warm light and fine contours shared across the carousel."""
    width, height = 270, 338
    pixels = []
    for y in range(height):
        for x in range(width):
            xx, yy = x * 4, y * 4
            light = strength * math.exp(-(((xx - 960) / 510) ** 2 + ((yy - 580) / 630) ** 2))
            shade = 2.3 * math.exp(-(((xx - 180) / 800) ** 2 + ((yy - 320) / 1000) ** 2))
            pixels.append(tuple(round(base + shade + tone * light)
                                for base, tone in ((14, 12), (13, 8), (12, 4))))
    base = Image.new("RGB", (width, height))
    base.putdata(pixels)
    base = base.resize((W, H), Image.Resampling.BICUBIC)
    noise = Image.frombytes("L", (W, H), random.Random(11).randbytes(W * H))
    noise = noise.point(lambda value: 128 + (value - 128) * 0.022).convert("RGB")
    base = ImageChops.add(base, noise, offset=-128)

    lines = Image.new("RGBA", base.size)
    draw = ImageDraw.Draw(lines)
    for index in range(23):
        radius = 272 + index * 17
        points = []
        for step in range(161):
            angle = 0.52 + 1.9 * step / 160
            x = 1110 + radius * math.cos(angle)
            y = 265 + radius * 1.16 * math.sin(angle) + (x - 1110) * 0.29
            points.append((x, y))
        alpha = int(strength * (18 + 39 * math.sin(math.pi * (index + 1) / 24)))
        draw.line(points, fill=(182, 143, 88, alpha), width=2 if index % 5 == 0 else 1)
    return Image.alpha_composite(base.convert("RGBA"), lines).convert("RGB")


def text(draw, xy, value, face, size, colour=IVORY, anchor="lt"):
    font = fact_font(face, size)
    x1, y1, x2, y2 = draw.textbbox(xy, value, font=font, anchor=anchor)
    if not (LEFT - 5 <= x1 <= x2 <= RIGHT + 2 and 0 <= y1 <= y2 <= H):
        raise ValueError(f"Text is outside the carousel margins: {value!r}")
    draw.text(xy, value, font=font, fill=colour, anchor=anchor)


def tracked(draw, x, y, value, size, gap, colour=MUTED):
    face = fact_font(BODY_FONT, size)
    # A common baseline keeps the dot and hyphen in the natural positions.
    baseline = y - face.getbbox(value, anchor="ls")[1]
    for letter in value:
        draw.text((x, baseline), letter, font=face, fill=colour, anchor="ls")
        x += face.getlength(letter) + gap


def heading(draw, x, y, value, face, size, colour=IVORY):
    for font_size in range(size, 29, -1):
        start, _, end, _ = fact_font(face, font_size).getbbox(value, anchor="lt")
        origin = max(x, LEFT - 4 - start)
        if origin + end <= RIGHT:
            text(draw, (origin, y), value, face, font_size, colour)
            return
    raise ValueError(f"Title does not fit the carousel: {value!r}")


def frame(page, label, strength):
    image = backdrop(strength).copy()
    draw = ImageDraw.Draw(image)
    text(draw, (LEFT, 83), "IVORY-ART", LOGO, 48)
    tracked(draw, LEFT + 2, 141, "GALLERY", 17, 4)
    text(draw, (RIGHT, 105), label, BODY_FONT, 24, GOLD, anchor="rt")
    for y in (198, 1195):
        draw.line((LEFT, y, RIGHT, y), fill=RULE, width=2)
    text(draw, (RIGHT, 1230), f"{page} / {FACT_SLIDE_COUNT}", BODY_FONT, 24, MUTED, anchor="rt")
    return image, draw


def cover(number, record):
    image, draw = frame(1, f"ART FACTS   /   {number:02d}", 1.0)
    lines = record["en_title"]
    positions = {1: (459,), 2: (390, 526), 3: (332, 476, 605)}
    for i, (line, y) in enumerate(zip(lines, positions[len(lines)])):
        if i == len(lines) - 1:
            heading(draw, LEFT - 1, y, line, ITALIC, 190, ACCENT)
        else:
            heading(draw, LEFT, y, line, SERIF, 151)
    draw.line((LEFT, 849, 228, 849), fill=GOLD, width=3)
    heading(draw, LEFT, 908, record["ru_title"], SERIF, 66, PAPER)
    tracked(draw, LEFT, 1230, "IVORY-ART.COM", 22, 1.7)
    return image


def body(page, number, layout):
    image, draw = frame(page, f"ART FACTS   /   {number:02d}", 0.31)
    y = 282
    size = layout.font_size
    for paragraph in layout.paragraphs:
        for row in paragraph:
            if y + fact_font(BODY_FONT, size).getbbox(row, anchor="ls")[3] >= 1180:
                raise ValueError("Fact text reaches the carousel footer")
            text(draw, (LEFT, y), row, BODY_FONT, size, PAPER, anchor="ls")
            y += line_height(size)
        y += PARAGRAPH_GAP
    if layout.footer:
        text(draw, (LEFT, 1230), layout.footer, BODY_FONT, 24, GOLD)
    return image


def closing(number):
    image, draw = frame(FACT_SLIDE_COUNT, f"ART FACTS   /   {number:02d}", 0.76)
    text(draw, (LEFT, 390), "Explore", SERIF, 139)
    heading(draw, LEFT - 2, 524, "original paintings", ITALIC, 108, ACCENT)
    draw.line((LEFT, 702, 228, 702), fill=GOLD, width=3)
    text(draw, (LEFT, 772), "Смотреть картины", SERIF, 70, PAPER)
    tracked(draw, LEFT, 992, "IVORY-ART.COM", 32, 3, IVORY)
    return image


def render_carousel(fact, edit=None):
    number = int(fact["id"])
    en, ru = fact_slide_text(fact, edit)
    english = fact_text_pages(en)
    russian = fact_text_pages(ru)
    images = [
        cover(number, FACTS[str(number)]),
        body(2, number, english[0]),
        body(3, number, english[1]),
        body(4, number, russian[0]),
        body(5, number, russian[1]),
        closing(number),
    ]
    names = fact_slide_names(fact, edit)
    for name, image in zip(names, images, strict=True):
        path = OUT / name
        image.save(path, "JPEG", quality=93, optimize=True, subsampling=0)
        with Image.open(path) as check:
            if check.size != (W, H):
                raise ValueError(f"Unexpected dimensions: {path}")
            check.verify()
    print(f"Rendered fact {number:02d} · {len(names)} slides · {english[0].font_size}/{russian[0].font_size}px")


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    overrides = json.loads((ROOT / "instagram_fact_slide_overrides.json").read_text(encoding="utf-8"))
    for key in FACTS:
        fact = {"id": key}
        render_carousel(fact)
        edit = overrides.get(key)
        if edit:
            render_carousel(fact, edit)


if __name__ == "__main__":
    main()
