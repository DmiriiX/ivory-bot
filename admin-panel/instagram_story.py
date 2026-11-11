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


def story_triptych(photos, title, artist, dimensions=""):
    """Three distinct 9:16 branded images, preserving real painting pixels.

    Slide 1: entire artwork. Slide 2: real detail crops.
    Slide 3: entire artwork with a clear site CTA (non-clickable in image).
    """
    if not photos:
        raise ValueError("Story requires artwork")
    originals=[]
    for data in photos[:2]:
        with Image.open(BytesIO(data)) as raw:
            originals.append(ImageOps.exif_transpose(raw).convert("RGB"))
    main=originals[0]
    detail=originals[1] if len(originals)>1 else main
    result=[]
    for slide in (1,2,3):
        canvas=Image.new("RGB",(1080,1920),"#0b0b0a")
        d=ImageDraw.Draw(canvas)
        d.text((72,80),"IVORY ART",font=_font(63),fill="#f2e3bc")
        d.text((76,181),"G A L L E R Y",font=_font(22,False),fill="#c6b997")
        d.text((800,118),("ARTWORK" if slide==1 else "DETAIL" if slide==2 else "DISCOVER"),font=_font(23,False),fill="#f2e3bc")
        d.line((72,248,1008,248),fill="#61543b",width=2)
        if slide==1:
            photo=main.copy()
            photo.thumbnail((928,1120),Image.Resampling.LANCZOS)
            canvas.paste(photo,((1080-photo.width)//2,296+(1120-photo.height)//2))
            d=ImageDraw.Draw(canvas)
            title=str(title or "Original Artwork")[:115]
            artist=str(artist or "IVORY ART Gallery")[:90]
            d.text((74,1525),"ORIGINAL ART",font=_font(43),fill="#f2e3bc")
            d.text((74,1624),title,font=_fit_text(title,52,923),fill="#f6f0e3")
            d.text((74,1720),artist,font=_fit_text(artist,31,920,False),fill="#cfc3ad")
        elif slide==2:
            # One faithful photograph, with restrained editorial typography.
            # No AI painting generation, collages or synthetic brushstrokes.
            photo=detail.copy()
            # Preserve the entire genuine detail photograph and its natural
            # proportions rather than forcing an arbitrary two-panel crop.
            photo.thumbnail((900,1190),Image.Resampling.LANCZOS)
            x=(1080-photo.width)//2
            y=304+(1190-photo.height)//2
            canvas.paste(photo,(x,y))
            d=ImageDraw.Draw(canvas)
            d.line((72,1517,1008,1517),fill="#61543b",width=2)
            d.text((75,1564),"A CLOSER LOOK",font=_font(31),fill="#f2e3bc")
            title=str(title or "Original Artwork")[:115]
            artist=str(artist or "IVORY ART Gallery")[:90]
            d.text((75,1635),title,font=_fit_text(title,46,925),fill="#f6f0e3")
            d.text((76,1725),artist,font=_fit_text(artist,27,920,False),fill="#cfc3ad")
        else:
            photo=main.copy()
            photo.thumbnail((850,1070),Image.Resampling.LANCZOS)
            canvas.paste(photo,((1080-photo.width)//2,295+(1070-photo.height)//2))
            d=ImageDraw.Draw(canvas)
            d.line((72,1417,1008,1417),fill="#756343",width=2)
            title=str(title or "Original Artwork")[:115]
            d.text((75,1475),title,font=_fit_text(title,45,930),fill="#f2e3bc")
            d.text((75,1570),"Смотреть работу на сайте",font=_fit_text("Смотреть работу на сайте",32,930,False),fill="#f6f0e3")
            d.rectangle((73,1670,1007,1810),outline="#8e7953",width=2)
            d.text((111,1711),"IVORY-ART.COM",font=_font(45,False),fill="#f2e3bc")
        d=ImageDraw.Draw(canvas)
        d.line((73,1860,1007,1860),fill="#61543b",width=2)
        buffer=BytesIO()
        canvas.save(buffer,"JPEG",quality=91,optimize=True)
        result.append(buffer.getvalue())
    return result
