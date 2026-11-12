#!/usr/bin/env python3
"""Render 4:5 Instagram FACT cards. Typography only: no counterfeit artworks."""
import sys, math, textwrap
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageFilter
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"admin-panel"))
from instagram_facts import FACTS
OUT=ROOT/"instagram-media"/"facts"
OUT.mkdir(parents=True,exist_ok=True)
W,H=1080,1350
FONTROOT=Path("/usr/share/fonts/truetype/dejavu")
def font(size,serif=False):
    return ImageFont.truetype(str(FONTROOT/("DejaVuSerif.ttf" if serif else "DejaVuSans.ttf")),size)
def wrap(draw,text,ft,max_width):
    words=text.split(); lines=[];line=""
    for word in words:
        trial=(line+" "+word).strip()
        if line and draw.textbbox((0,0),trial,font=ft)[2]>max_width:
            lines.append(line);line=word
        else:line=trial
    if line:lines.append(line)
    return lines
def paragraph(draw,text,y,size,color,serif,maxlines=6,width=920,gap=14):
    ft=font(size,serif); lines=wrap(draw,text,ft,width)[:maxlines]
    for line in lines:
        draw.text((82,y),line,font=ft,fill=color,stroke_width=0)
        y+=size+gap
    return y
for raw_id,rec in FACTS.items():
    no=int(raw_id)
    img=Image.new("RGB",(W,H),(13,13,12))
    draw=ImageDraw.Draw(img)
    # Restrained brushed-gold geometry: elegant but not fake painting imagery.
    for j in range(28):
        off=j*13
        shade=(47+j//3,40+j//4,27+j//5)
        draw.arc((635-off,-380+off,1510-off,495+off),start=15,end=170,fill=shade,width=2)
    draw.rectangle((67,93,71,190),fill=(242,227,188))
    draw.text((92,89),"IVORY ART",font=font(57,True),fill=(242,227,188))
    draw.text((95,166),"G A L L E R Y",font=font(20),fill=(194,180,149))
    draw.line((81,245,994,245),fill=(89,79,55),width=2)
    draw.text((81,313),"ART / FACTS",font=font(27),fill=(203,185,146))
    draw.text((81,402),f"{no:02d}",font=font(124,True),fill=(112,94,64))
    y=588
    y=paragraph(draw,rec["en_title"].upper(),y,58,(245,234,209),True,3,920,16)
    draw.line((82,y+27,230,y+27),fill=(183,149,94),width=3)
    y+=80
    y=paragraph(draw,rec["ru_title"],y,41,(210,200,179),True,3,920,13)
    draw.line((81,1165,994,1165),fill=(75,66,50),width=2)
    draw.text((82,1206),"ART HISTORY · COLLECTING · TECHNIQUE",font=font(18),fill=(174,163,141))
    draw.text((82,1261),"IVORY-ART.COM",font=font(26),fill=(242,227,188))
    path=OUT/f"fact-{no:02d}.jpg"
    img.save(path,"JPEG",quality=91,optimize=True)
    print("GENERATED",path.relative_to(ROOT),path.stat().st_size)
