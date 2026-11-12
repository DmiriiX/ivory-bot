"""Instagram Facts, with reviewed translations of the Telegram/MAX originals.

The original Russian copy is from DmiriiX/ivory-bot-facts posts.json.
Instagram publication history and editorial overrides are independent.
"""
import hashlib
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from instagram_campaign import campaign_slot

FACTS = json.loads(Path(__file__).with_name("instagram_fact_content.json").read_text(encoding="utf-8"))
IMAGE_PREFIX = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/facts/"
FACT_SLIDE_COUNT = 6
MAX_FACT_CAPTION_LENGTH = 2196
MSK=ZoneInfo("Europe/Moscow")

def fact_key(fact):
    return "igfact:"+str(fact["id"])

def fact_slide_text(fact, override=None):
    entry = FACTS.get(str(fact["id"]))
    if not entry:
        raise ValueError("Unreviewed Instagram fact ID")
    override = override or {}
    return override.get("en") or entry["en"], override.get("ru") or entry["ru"]

def fact_caption(fact, override=None):
    en, ru = fact_slide_text(fact, override)
    tags = FACTS[str(fact["id"])]["tags"]
    return "\n\n".join((en, ru, " ".join(tags)))

def fact_media(fact):
    return fact_slides(fact)[0]

def fact_slide_names(fact, override=None):
    """The six cards are distinct from the media URLs used by older posts."""
    key = str(fact["id"])
    if key not in FACTS:
        raise ValueError("Unreviewed fact")
    revision = (override or {}).get("revision") or ""
    if revision and not re.fullmatch(r"[0-9a-f]{12}", revision):
        raise ValueError("Invalid slide revision")
    suffix = f"-{revision}" if revision else ""
    return [f"fact-{int(key):02d}-carousel-{n}{suffix}.jpg" for n in range(1, FACT_SLIDE_COUNT + 1)]

def fact_slides(fact, override=None):
    return [IMAGE_PREFIX + name for name in fact_slide_names(fact, override)]


def cycle_records(state):
    return sorted(
       ((key,v) for key,v in (state.get("records") or {}).items()
        if v.get("editorial_cycle") and v.get("status") in ("uncertain","accepted","sent","failed")),
       key=lambda item:item[1].get("created_at",""))

def cycle_next_kind(state):
    # Start with fact #1; then two gallery paintings; repeat.
    return "fact" if len(cycle_records(state))%3==0 else "artwork"

def next_fact(facts,state):
    records=state.get("records") or {}
    excluded=set(str(x) for x in state.get("ig_fact_excluded",[]))
    next_id=state.get("ig_fact_next_id")
    eligible=[p for p in facts if str(p.get("id")) not in excluded
              and fact_key(p) not in records and str(p.get("id",-1)) in FACTS]
    eligible.sort(key=lambda p:int(p["id"]))
    return next((p for p in eligible if str(p["id"])==str(next_id)),None) or (eligible[0] if eligible else None)

def artwork_key(post):
    value="painting:"+str(post.get("link") or post.get("title"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def feed_calendar(state,facts,now=None,count=12,artworks=None,media=None):
    """Projected campaign feed slots, including draft artwork selection.

    Fact IDs and predicted artworks are read-only suggestions: actual Buffer
    submission still validates images, previous delivery and live controls.
    """
    now=(now or datetime.now(MSK)).astimezone(MSK)
    campaign=state.get("campaign") or {}
    sequence=len(cycle_records(state))
    next_no=int(next_fact(facts,state)["id"]) if next_fact(facts,state) else None
    results=[]
    date_cursor=now
    existing_dates={v.get("campaign_date") for v in (state.get("records") or {}).values()}
    artworks=artworks or []
    media=media or {}
    reserved=set((state.get("records") or {})) | set(state.get("baseline_ids") or [])
    already_art=sum(v.get("campaign") is True and v.get("kind")!="fact"
                    and v.get("status") in ("sent","accepted")
                    for v in (state.get("records") or {}).values())
    reel_count=sum(v.get("campaign") is True and v.get("kind")!="fact" and v.get("format")=="reel"
                   and v.get("status") in ("sent","accepted")
                   for v in (state.get("records") or {}).values())

    for _ in range(45):
        slot=campaign_slot(campaign,"feed",date_cursor)
        if not slot.get("next_at"):break
        dt=datetime.fromisoformat(slot["next_at"])
        date_cursor=dt+timedelta(hours=5,minutes=31)
        if dt.date().isoformat() in existing_dates:continue
        kind="fact" if state.get("ig_facts_enabled") and sequence%3==0 else "artwork"
        if kind=="fact":
            fact=next((f for f in facts if int(f["id"])==next_no),None) if next_no else None
            item={"at":dt.isoformat(),"kind":"fact","format":"carousel",
                  "id":str(fact["id"]) if fact else None,
                  "title":fact["title"] if fact else "Очередь фактов закончилась",
                  "photo":fact_media(fact) if fact else None,
                  "status":"planned"}
            if fact:
                remaining=[int(x["id"]) for x in facts if int(x["id"])>next_no
                           and fact_key(x) not in (state.get("records") or {})
                           and str(x["id"]) not in {str(i) for i in state.get("ig_fact_excluded",[])}]
                next_no=min(remaining) if remaining else None
        else:
            desired=("reel","carousel","reel","carousel")[already_art%4]
            candidates=[p for p in artworks if artwork_key(p) not in reserved]
            if desired=="reel":
                preferred_style=("cinematic","luxury")[reel_count%2]
                artwork=next((p for p in candidates
                              if media.get(artwork_key(p),{}).get("reel_style")==preferred_style
                              and media.get(artwork_key(p),{}).get("reel")),None)
                if artwork is None:
                    artwork=next((p for p in candidates if media.get(artwork_key(p),{}).get("reel")),None)
            else:
                artwork=next((p for p in candidates if len(media.get(artwork_key(p),{}).get("images") or [])>=2),None)
            if artwork is None:
                artwork=candidates[0] if candidates else None
            if artwork:
                key=artwork_key(artwork)
                prepared=media.get(key,{})
                if desired=="reel" and prepared.get("reel"):
                    actual="reel"
                    reel_count+=1
                elif len(prepared.get("images") or [])>=2:
                    actual="carousel"
                else:
                    actual="post"
                reserved.add(key)
                item={"at":dt.isoformat(),"kind":"artwork","format":actual,"id":key,
                      "title":artwork.get("title"),"artist":artwork.get("artist"),
                      "photo":artwork.get("photo"),"status":"planned"}
            else:
                item={"at":dt.isoformat(),"kind":"artwork","format":"post","id":None,
                      "title":"Работы в очереди закончились","status":"planned"}
            already_art+=1
        results.append(item)
        sequence+=1
        if len(results)>=count:break
    return results
