"""IVORY ART original editorial Story image generator.

All lettering is baked into the JPEG. No interactive Instagram stickers or
third-party music are requested, so automatic publishing can be attempted.
"""
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


def _font(size, serif=True):
    root = Path("/usr/share/fonts/truetype/dejavu")
    names = (["DejaVuSerif.ttf", "DejaVuSans.ttf"] if serif
             else ["DejaVuSans.ttf", "DejaVuSerif.ttf"])
    for name in names:
        path = root / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()


def _fit_text(text, size, max_width, serif=True):
    for size in range(size, 17, -2):
        font = _font(size, serif)
        if ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
    return _font(17, serif)


def story_image(photo_bytes, title, artist):
    """Portrait 9:16, matte black, unobstructed painting with ivory typography."""
    width, height = 1080, 1920
    background = Image.new("RGB", (width, height), "#0b0b0a")
    d = ImageDraw.Draw(background)
    gold, secondary = "#f2e3bc", "#d0c4aa"
    d.text((75, 113), "IVORY ART", font=_font(70), fill=gold)
    d.text((79, 206), "G A L L E R Y", font=_font(26, False), fill=secondary)
    d.line((78, 281, 1000, 281), fill="#574b35", width=2)

    with Image.open(BytesIO(photo_bytes)) as source:
        photo = ImageOps.exif_transpose(source).convert("RGB")
        photo.thumbnail((925, 1170), Image.Resampling.LANCZOS)
        x = (width - photo.width)//2
        y = 345 + (1170-photo.height)//2
        background.paste(photo, (x, y))
    d = ImageDraw.Draw(background)
    d.line((78, 1590, 1000, 1590), fill="#574b35", width=2)
    title = str(title or "Original Artwork").strip()[:130]
    artist = str(artist or "IVORY ART Gallery").strip()[:90]
    title_font = _fit_text(title, 48, 925)
    artist_font = _fit_text(artist, 30, 925, serif=False)
    d.text((78, 1640), title, font=title_font, fill=gold)
    d.text((78, 1720), artist, font=artist_font, fill=secondary)
    d.text((78, 1826), "IVORY-ART.COM", font=_font(29, False), fill=gold)
    buffer = BytesIO()
    background.save(buffer, "JPEG", quality=92, optimize=True)
    return buffer.getvalue()
