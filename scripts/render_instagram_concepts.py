#!/usr/bin/env python3
"""Three Ivory Art social concepts: two 12s Reels and a three-frame Story pack.

Use existing untouched gallery paintings; never synthesize or retouch artwork.
Creative previews only. This script does not send anything to Buffer or Instagram.
All sample audio is generated from original notes (no licensed recordings).
"""
from pathlib import Path
import math, os, subprocess, sys, wave
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
ART=ROOT/"instagram-media"/"prepared"
OUT=ROOT/"concept-previews"
OUT.mkdir(exist_ok=True)
W,H,FPS=720,1280,24
BLACK=(10,10,10);GOLD=(242,227,188);WHITE=(246,243,234);MUTED=(172,164,146)
SERIF="/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"
SANS="/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

def font(s,serif=False):
    return ImageFont.truetype(SERIF if serif else SANS,s)

def text(d,x,y,message,size,color=WHITE,serif=False,anchor=None):
    d.text((x,y),message,font=font(size,serif),fill=color,anchor=anchor)

def image(uid,index=1):
    return Image.open(ART/f"{uid}-{index}.jpg").convert("RGB")

def artwork(c,img,x,y,w,h,detail=False,zoom=1.0,focus=.5):
    scale=(max(w/img.width,h/img.height)*zoom if detail
           else min(w/img.width,h/img.height))
    iw,ih=max(1,int(img.width*scale)),max(1,int(img.height*scale))
    pic=img.resize((iw,ih),Image.Resampling.BICUBIC)
    if detail:
        px=max(0,min(iw-w,int((iw-w)*focus)))
        py=max(0,(ih-h)//2)
        pic=pic.crop((px,py,px+w,py+h))
    c.paste(pic,(x+(w-pic.width)//2,y+(h-pic.height)//2))

def header(d,number):
    text(d,39,35,"IVORY ART",34,GOLD,True)
    text(d,42,92,"G A L L E R Y",12,MUTED)
    text(d,680,67,number,13,MUTED,anchor="ra")
    d.line((40,124,680,124),fill=(79,69,53),width=1)

def bottom(d,t):
    d.rectangle((40,1240,680,1242),fill=(66,61,52))
    d.rectangle((40,1240,40+int(640*t/12),1242),fill=GOLD)

def original_music(path,seconds,mood):
    sr=24000
    n=int(seconds*sr)
    times=np.arange(n,dtype=np.float64)/sr
    sample=np.zeros(n)
    chords=([196,246.94,293.66],[174.61,220,261.63],
            [164.81,196,246.94],[174.61,220,293.66]) if mood==1 else (
            [146.83,220,293.66],[130.81,196,261.63],
            [146.83,220,246.94],[164.81,220,293.66])
    for k,notes in enumerate(chords):
        mask=(times>=k*seconds/4)&(times<(k+1)*seconds/4)
        local=times[mask]
        envelope=np.minimum(1,(local-k*seconds/4)/.85)*np.minimum(1,((k+1)*seconds/4-local)/.55)
        sample[mask]+=sum(np.sin(2*np.pi*hz*local) for hz in notes)/3*.23*np.clip(envelope,0,1)
    melody=[392,493.88,587.33,440,329.63] if mood==1 else [293.66,349.23,440,392]
    for k,point in enumerate(np.arange(.4,seconds-1,1.15 if mood==1 else 1.4)):
        start=int(point*sr);length=min(int(sr*2),n-start)
        local=np.arange(length)/sr;hz=melody[k%len(melody)]
        sample[start:start+length]+=((np.sin(2*np.pi*hz*local)+.25*np.sin(2*np.pi*2*hz*local))
                                       *np.exp(-3*local)*.10)
    sample*=np.clip(np.minimum(1,times/1.2)*np.minimum(1,(seconds-times)/1.2),0,1)
    with wave.open(str(path),"wb") as f:
        f.setnchannels(1);f.setsampwidth(2);f.setframerate(sr)
        f.writeframes((np.clip(sample,-1,1)*32767).astype("<i2").tobytes())

def video(filename,draw,mood):
    sound=OUT/(filename+"_music.wav")
    original_music(sound,12,mood)
    target=OUT/(filename+".mp4")
    cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-y",
         "-f","rawvideo","-pix_fmt","rgb24","-s","720x1280","-r","24","-i","pipe:0",
         "-i",str(sound),"-map","0:v:0","-map","1:a:0","-t","12",
         "-c:v","libx264","-preset","veryfast","-crf","23","-pix_fmt","yuv420p",
         "-c:a","aac","-b:a","128k","-movflags","+faststart",str(target)]
    p=subprocess.Popen(cmd,stdin=subprocess.PIPE,stderr=subprocess.PIPE)
    for n in range(12*FPS):
        p.stdin.write(draw(n/FPS).tobytes())
    p.stdin.close()
    err=p.stderr.read().decode(errors="replace")
    if p.wait()!=0:raise RuntimeError(err[-2000:])
    print("CREATED",target,target.stat().st_size,flush=True)

def cinematic():
    full=image("877c981e3b8d2d4d44e2d1c1")
    detail=image("877c981e3b8d2d4d44e2d1c1",2)
    def draw(t):
        c=Image.new("RGB",(W,H),BLACK);d=ImageDraw.Draw(c);header(d,"01 / CINEMATIC")
        if t<2.1:
            d.line((40,255,125,255),fill=GOLD,width=2)
            text(d,42,318,"THE ART OF",42,WHITE,True)
            text(d,42,393,"SUMMER",67,GOLD,True)
            artwork(c,full,88,557,544,430)
            d=ImageDraw.Draw(c)
            text(d,42,1068,"«Жаркое лето»",33,WHITE,True)
            text(d,42,1123,"Алексей Рычков",19,MUTED)
        elif t<5.7:
            artwork(c,full,56,178,608,822)
            d=ImageDraw.Draw(c);d.rectangle((43,169,677,1011),outline=(99,88,65))
            text(d,42,1052,"ЦВЕТ. СВЕТ. МГНОВЕНИЕ.",21,GOLD)
            text(d,42,1104,"Oil on canvas   /   60 × 80 cm",16,MUTED)
        elif t<9:
            travel=(t-5.7)/3.3
            artwork(c,detail,55,211,610,830,True,1.05+travel*.11,.32+travel*.38)
            d=ImageDraw.Draw(c)
            d.line((55,1069,205,1069),fill=GOLD,width=2)
            text(d,55,1102,"LOOK CLOSER",30,GOLD,True)
            text(d,55,1157,"Детали настоящей живописи",16,WHITE)
        else:
            artwork(c,full,134,224,452,640)
            d=ImageDraw.Draw(c)
            text(d,360,942,"ALEXEY RYCHKOV",20,WHITE,anchor="ma")
            text(d,360,993,"Жаркое лето",33,GOLD,True,anchor="ma")
            d.line((255,1044,465,1044),fill=(100,87,65))
            text(d,360,1106,"IVORY-ART.COM",20,WHITE,anchor="ma")
        bottom(d,t);return c
    video("01_cinematic_summer",draw,1)

def luxury():
    full=image("07cf3fcfca91eb5d4197b40f")
    detail=image("07cf3fcfca91eb5d4197b40f",2)
    def draw(t):
        c=Image.new("RGB",(W,H),BLACK);d=ImageDraw.Draw(c);header(d,"02 / EDITORIAL")
        if t<2.5:
            d.rectangle((42,193,678,1030),outline=(82,74,59))
            artwork(c,full,90,230,540,641)
            d=ImageDraw.Draw(c)
            text(d,43,914,"VENICE",68,GOLD,True)
            text(d,44,1009,"A story in color",27,WHITE,True)
            text(d,44,1110,"ИСКУССТВО В ДЕТАЛЯХ",17,MUTED)
        elif t<6.9:
            travel=(t-2.5)/4.4
            artwork(c,full,44,195,632,805,True,1+travel*.07,.45+travel*.09)
            d=ImageDraw.Draw(c)
            d.rectangle((43,850,677,1059),fill=(12,12,12))
            text(d,58,868,"Кафе в Венеции",39,WHITE,True)
            d.line((58,942,645,942),fill=GOLD,width=2)
            text(d,58,975,"Владимир Кожевников",19,GOLD)
            text(d,58,1012,"Холст, масло   ·   110 × 90 см",16,MUTED)
        elif t<9.5:
            artwork(c,detail,45,199,630,821,True,1.11,.55)
            d=ImageDraw.Draw(c)
            text(d,43,1065,"ART / FORM / FEELING",28,GOLD,True)
            text(d,43,1120,"A lasting impression.",18,WHITE)
        else:
            artwork(c,full,151,246,418,606)
            d=ImageDraw.Draw(c)
            d.line((170,906,550,906),fill=GOLD,width=2)
            text(d,360,980,"КАФЕ В ВЕНЕЦИИ",24,WHITE,anchor="ma")
            text(d,360,1057,"IVORY ART",43,GOLD,True,anchor="ma")
            text(d,360,1142,"ivory-art.com",20,MUTED,anchor="ma")
        bottom(d,t);return c
    video("02_luxury_venice",draw,2)

def stories():
    full=image("e9fa2233ee541d5fce64a8ea")
    detail=image("e9fa2233ee541d5fce64a8ea",2)
    for number in range(1,4):
        c=Image.new("RGB",(1080,1920),BLACK);d=ImageDraw.Draw(c)
        text(d,70,65,"IVORY ART",60,GOLD,True)
        text(d,75,159,"G A L L E R Y",20,MUTED)
        text(d,1010,110,f"0{number}/03",23,GOLD,anchor="ra")
        d.line((70,215,1010,215),fill=(83,77,62),width=2)
        if number==1:
            artwork(c,full,74,280,932,1190)
            d=ImageDraw.Draw(c)
            text(d,75,1515,"A MOMENT AT SEA",52,GOLD,True)
            text(d,75,1610,"Яхты у причала",46,WHITE,True)
            text(d,75,1720,"Рустем Стахурский",27,MUTED)
        elif number==2:
            artwork(c,full,98,300,884,490,True,1.22,.3)
            artwork(c,detail,98,816,884,527,True,1.12,.7)
            d=ImageDraw.Draw(c)
            text(d,75,1442,"THE BEAUTY IS",54,GOLD,True)
            text(d,75,1534,"IN THE DETAILS",54,GOLD,True)
            text(d,75,1650,"Холст, масло   ·   50 × 70 см",29,WHITE)
            text(d,75,1730,"Подлинная авторская живопись",23,MUTED)
        else:
            artwork(c,full,153,300,774,1070)
            d=ImageDraw.Draw(c)
            d.rectangle((70,1460,1010,1824),outline=(111,98,71),width=2)
            text(d,100,1498,"ВАША КОЛЛЕКЦИЯ",43,GOLD,True)
            text(d,100,1580,"НАЧИНАЕТСЯ ЗДЕСЬ",32,WHITE,True)
            text(d,100,1690,"Смотреть картину на сайте",26,MUTED)
            text(d,100,1760,"IVORY-ART.COM",31,GOLD)
        d.line((70,1860,1010,1860),fill=(87,73,52))
        target=OUT/f"03_story_{number}.jpg"
        c.save(target,"JPEG",quality=93,optimize=True)
        print("CREATED",target,target.stat().st_size,flush=True)

if __name__=="__main__":
    cinematic();luxury();stories()
