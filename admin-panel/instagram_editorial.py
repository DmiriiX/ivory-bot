"""Premium original-artwork-only Instagram Reel renderer for Ivory Art.

Cinematic and Luxury alternate by catalogue order. The paintings are untouched:
every crop is a literal detail of an authentic source photo. No generated content.
All sound is original programmatic ambient composition.
"""
import asyncio
import math
import subprocess
import tempfile
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps
from media import normalized_image
from instagram_reel import original_ambient_audio

SIZE=(720,1280)
FPS=30
DURATION=12
BG=(11,11,10)
GOLD=(242,227,188)
MUTED=(180,170,151)
OFFWHITE=(246,241,230)


def _font(size, serif=False):
    root=Path("/usr/share/fonts/truetype/dejavu")
    file=root/("DejaVuSerif.ttf" if serif else "DejaVuSans.ttf")
    return ImageFont.truetype(str(file),size)


def _fit(draw, value, size=35, limit=620, serif=False):
    value=str(value or "").strip()
    for n in range(size,15,-2):
        f=_font(n,serif)
        if draw.textbbox((0,0),value,font=f)[2]<=limit:
            return f
    return _font(16,serif)


def _label(draw,x,y,value,size,color,limit=630,serif=False):
    draw.text((x,y),str(value or ""),font=_fit(draw,value,size,limit,serif),fill=color)


def _photo(canvas, photo, bounds, *, crop=False, zoom=1, focus=.5):
    x,y,w,h=bounds
    if crop:
        ratio=max(w/photo.width,h/photo.height)*zoom
        sw,sh=max(w,round(photo.width*ratio)),max(h,round(photo.height*ratio))
        pic=photo.resize((sw,sh),Image.Resampling.BILINEAR)
        px=min(max(0,int((sw-w)*focus)),sw-w)
        py=(sh-h)//2
        pic=pic.crop((px,py,px+w,py+h))
        canvas.paste(pic,(x,y))
    else:
        ratio=min(w/photo.width,h/photo.height)
        sw,sh=max(1,round(photo.width*ratio)),max(1,round(photo.height*ratio))
        pic=photo.resize((sw,sh),Image.Resampling.BILINEAR)
        canvas.paste(pic,(x+(w-sw)//2,y+(h-sh)//2))


def draw_frame(t, photos, title, artist, style):
    canvas=Image.new("RGB",SIZE,BG)
    d=ImageDraw.Draw(canvas)
    d.text((42,40),"IVORY ART",font=_font(32,True),fill=GOLD)
    d.text((45,94),"G A L L E R Y",font=_font(12),fill=MUTED)
    d.line((42,129,678,129),fill=(82,72,56),width=1)
    full=photos[0]
    detail=photos[1] if len(photos)>1 else full
    if style=="cinematic":
        if t<2:
            _label(d,45,243,"ART IN MOTION",26,GOLD,serif=True)
            _label(d,45,307,title,48,OFFWHITE,serif=True)
            _photo(canvas,full,(70,443,580,613))
            d=ImageDraw.Draw(canvas)
            _label(d,45,1100,artist,23,MUTED)
        elif t<5.4:
            _photo(canvas,full,(46,183,628,840),crop=True,zoom=1.02+0.07*(t-2)/3.4,focus=.48)
            d=ImageDraw.Draw(canvas)
            d.line((45,1040,240,1040),fill=GOLD,width=2)
            _label(d,45,1080,"A CLOSER LOOK",28,OFFWHITE,serif=True)
        elif t<9.2:
            f=.25+.52*(t-5.4)/3.8
            _photo(canvas,detail,(46,196,628,836),crop=True,zoom=1.08,focus=f)
            d=ImageDraw.Draw(canvas)
            _label(d,45,1063,"THE BEAUTY OF DETAILS",25,GOLD,serif=True)
            _label(d,45,1121,artist,18,MUTED)
        else:
            _photo(canvas,full,(100,228,520,715))
            d=ImageDraw.Draw(canvas)
            _label(d,45,977,title,40,GOLD,serif=True)
            _label(d,45,1045,artist,21,OFFWHITE)
            _label(d,45,1147,"IVORY-ART.COM",20,MUTED)
    elif style=="luxury":
        if t<2.6:
            d.rectangle((44,186,676,1030),outline=(84,75,60),width=2)
            _photo(canvas,full,(80,205,560,690))
            d=ImageDraw.Draw(canvas)
            _label(d,52,914,"ART / FORM / FEELING",29,GOLD,serif=True)
            _label(d,52,990,artist,20,OFFWHITE)
            _label(d,52,1087,"AN IVORY ART SELECTION",16,MUTED)
        elif t<6.7:
            _photo(canvas,full,(43,187,634,845),crop=True,zoom=1.03+.05*(t-2.6)/4.1,focus=.45)
            d=ImageDraw.Draw(canvas)
            d.rectangle((43,929,677,1123),fill=BG)
            _label(d,55,945,title,40,GOLD,serif=True)
            d.line((55,1014,647,1014),fill=GOLD,width=2)
            _label(d,55,1040,artist,20,OFFWHITE)
        elif t<9.3:
            _photo(canvas,detail,(47,190,626,820),crop=True,zoom=1.11,focus=.57)
            d=ImageDraw.Draw(canvas)
            _label(d,45,1050,"COLLECT THE MOMENT",28,GOLD,serif=True)
            _label(d,45,1120,"ORIGINAL PAINTING",17,MUTED)
        else:
            _photo(canvas,full,(117,222,486,710))
            d=ImageDraw.Draw(canvas)
            d.line((90,966,630,966),fill=GOLD,width=2)
            _label(d,45,988,title,39,OFFWHITE,serif=True)
            _label(d,45,1050,artist,20,MUTED)
            _label(d,45,1150,"IVORY-ART.COM",23,GOLD)
    else:
        raise ValueError("Unknown editorial style")
    d=ImageDraw.Draw(canvas)
    d.line((45,1240,675,1240),fill=(66,62,54),width=2)
    d.line((45,1240,45+int(630*t/DURATION),1240),fill=GOLD,width=3)
    return canvas


def _encode(photos,title,artist,style,out):
    wav=out.with_suffix(".wav")
    original_ambient_audio(wav,DURATION,style)
    cmd=["ffmpeg","-hide_banner","-loglevel","error","-nostdin","-y",
         "-f","rawvideo","-pixel_format","rgb24","-video_size","720x1280",
         "-framerate",str(FPS),"-i","pipe:0","-i",str(wav),
         "-map","0:v:0","-map","1:a:0","-t",str(DURATION),"-c:v","libx264",
         "-preset","veryfast","-crf","25","-pix_fmt","yuv420p",
         "-r",str(FPS),"-c:a","aac","-b:a","128k",
         "-movflags","+faststart",str(out)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    try:
        for i in range(DURATION*FPS):
            p.stdin.write(draw_frame(i/FPS,photos,title,artist,style).tobytes())
        p.stdin.close()
        err=p.stderr.read().decode("utf-8",errors="replace")
        if p.wait(timeout=90):
            raise RuntimeError("Reel encoding failed: "+err[-350:])
        if not out.is_file() or out.stat().st_size<20000 or out.stat().st_size>35_000_000:
            raise ValueError("Invalid editorial Reel")
        return out.read_bytes()
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()


async def make_editorial_reel(images,title,artist,style):
    if style not in ("cinematic","luxury"):
        raise ValueError("Unsupported style")
    if not images:
        raise ValueError("Painting photo required")
    # Real Tilda photographs only; domain/size limits apply in normalized_image.
    fetched=await asyncio.gather(*(normalized_image(url) for url in images[:2]))
    photos=[]
    for raw in fetched:
        with Image.open(BytesIO(raw)) as im:
            photos.append(ImageOps.exif_transpose(im).convert("RGB"))
    with tempfile.TemporaryDirectory(prefix="ivory-editorial-") as folder:
        return await asyncio.to_thread(_encode,photos,title,artist,style,Path(folder)/"reel.mp4")
