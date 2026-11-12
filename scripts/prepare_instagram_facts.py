#!/usr/bin/env python3
"""Render fully original, legible 4-card Instagram Facts carousels (1080x1350).

Each carousel: editorial cover, English explanation, Russian explanation,
quiet site CTA. All text sourced from independently curated FACTS.
This script NEVER publishes to Instagram or Buffer.
"""
import sys
import json
import re
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"admin-panel"))
from instagram_facts import FACTS

OUT=ROOT/"instagram-media"/"facts"
OUT.mkdir(parents=True,exist_ok=True)
W,H=1080,1350
BG="#0d0d0c"
IVORY="#f2e3bc"
MUTED="#d0c4ab"
GOLD="#ad9669"
BORDER="#5e5038"
FONTPATH=Path("/usr/share/fonts/truetype/dejavu")

def font(size,serif=False):
    return ImageFont.truetype(str(FONTPATH/("DejaVuSerif.ttf" if serif else "DejaVuSans.ttf")),size)

def layout_text(draw,body,max_size,max_width,max_height,limit=18):
    """Fit natural language on screen, never clip or silently truncate."""
    for size in range(max_size,limit-1,-2):
        ft=font(size)
        words=body.split()
        lines=[]; row=""
        for word in words:
            proposed=(row+" "+word).strip()
            if row and draw.textbbox((0,0),proposed,font=ft)[2]>max_width:
                lines.append(row)
                row=word
            else:row=proposed
        if row:lines.append(row)
        line_height=int(size*1.58)
        if len(lines)*line_height<=max_height:
            return ft,lines,line_height
    raise ValueError("Fact text too long to remain legible")

def card_base(number,slide,language=None):
    im=Image.new("RGB",(W,H),BG)
    d=ImageDraw.Draw(im)
    d.rectangle((69,94,73,192),fill=IVORY)
    d.text((97,90),"IVORY ART",font=font(57,True),fill=IVORY)
    d.text((97,167),"G A L L E R Y",font=font(18),fill=MUTED)
    d.text((868,127),f"{slide:02d} / 04",font=font(25),fill=GOLD)
    d.line((80,244,998,244),fill=BORDER,width=2)
    d.text((82,317),"ART  /  FACTS",font=font(28),fill=GOLD)
    d.text((82,389),f"№ {number:02d}",font=font(26,True),fill=MUTED)
    if language:d.text((862,389),language,font=font(24),fill=MUTED)
    d.line((82,1160,998,1160),fill=BORDER,width=2)
    d.text((82,1205),"ORIGINAL ART  ·  IVORY-ART.COM",font=font(25),fill=IVORY)
    return im,d

def write_paragraph(draw,text,x,y,size,max_width,max_height,colour=IVORY):
    ft,lines,line_height=layout_text(draw,text,size,max_width,max_height)
    for line in lines:
        draw.text((x,y),line,font=ft,fill=colour)
        y+=line_height
    return y

def render_cover(number,record):
    im,d=card_base(number,1)
    # Minimal abstract ornament: geometrical lines, never imitation artwork.
    for i in range(24):
        d.arc((655-i*10, -90+i*19, 1535-i*9, 790+i*17),
              start=28,end=162,fill=(49+i//4,43+i//5,31+i//6),width=2)
    d.text((82,488),f"{number:02d}",font=font(121,True),fill="#6a593e")
    write_paragraph(d,record["en_title"].upper(),82,704,57,915,270)
    d.line((82,943,232,943),fill=GOLD,width=3)
    write_paragraph(d,record["ru_title"],82,995,37,915,120,MUTED)
    return im

def render_text(number,record,english):
    slide=2 if english else 3
    im,d=card_base(number,slide,"EN" if english else "RU")
    title=record["en_title"] if english else record["ru_title"]
    body=record["en"] if english else record["ru"]
    write_paragraph(d,title,82,475,49,910,150)
    d.line((82,662,225,662),fill=GOLD,width=3)
    write_paragraph(d,body,82,742,43,900,410,IVORY)
    return im

def render_final(number,record):
    im,d=card_base(number,4)
    d.text((82,507),"ART IS WORTH",font=font(58,True),fill=IVORY)
    d.text((82,607),"EXPLORING.",font=font(58,True),fill=IVORY)
    d.line((82,746,242,746),fill=GOLD,width=3)
    write_paragraph(d,"Искусство, к которому хочется возвращаться.",82,821,35,895,190,MUTED)
    d.rectangle((82,1029,998,1116),outline=GOLD,width=2)
    d.text((121,1053),"IVORY-ART.COM",font=font(36),fill=IVORY)
    return im

def save(im,path):
    im.save(path,"JPEG",quality=93,optimize=True,subsampling=0)
    with Image.open(path) as check:
        assert check.size==(W,H)
    print("GENERATED",path.relative_to(ROOT),path.stat().st_size)

overrides=json.loads((ROOT/"instagram_fact_slide_overrides.json").read_text(encoding="utf-8"))
for raw_id,record in FACTS.items():
    num=int(raw_id)
    cards=[render_cover(num,record),render_text(num,record,True),
           render_text(num,record,False),render_final(num,record)]
    for slide,im in enumerate(cards,1):
        save(im,OUT/f"fact-{num:02d}-{slide}.jpg")
    # Keep the original cover URL for existing Mini App users.
    save(cards[0],OUT/f"fact-{num:02d}.jpg")
    revision=overrides.get(raw_id) or {}
    if revision:
        rev=revision.get("revision","")
        if not re.fullmatch(r"[0-9a-f]{12}",rev):
            raise ValueError("Invalid revision for fact "+raw_id)
        edited=dict(record,en=revision["en"],ru=revision["ru"])
        amended=[render_cover(num,edited),render_text(num,edited,True),
                 render_text(num,edited,False),render_final(num,edited)]
        for slide,im in enumerate(amended,1):
            save(im,OUT/f"fact-{num:02d}-{slide}-{rev}.jpg")
