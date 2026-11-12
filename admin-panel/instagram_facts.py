"""Editorial Instagram facts. Independent from Telegram/MAX posting history.

Source themes: DmiriiX/ivory-bot-facts posts.json, IDs 1-15.
All copy is editorially adapted rather than translated verbatim.
"""
import re
import hashlib
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from instagram_campaign import campaign_slot

FACTS={
  "1": {
    "en_title": "Art That Lasts",
    "ru_title": "Картина на века",
    "en": "With thoughtful care, an oil painting can be enjoyed across generations. Stable conditions, careful handling and protection from direct sunlight matter far more than any promise of permanence.",
    "ru": "При бережном отношении масляная картина может радовать несколько поколений. Важны стабильные условия, аккуратное обращение и защита от прямого солнца.",
    "en_tags": "#artconservation #oilpainting #artcollecting",
    "ru_tags": "#сохранениекартин #маслянаяживопись #коллекционирование"
  },
  "2": {
    "en_title": "Before Van Eyck",
    "ru_title": "До ван Эйка",
    "en": "Jan van Eyck perfected luminous oil-painting techniques, but he did not invent oil painting from scratch. Earlier evidence includes murals made with drying oils in Afghanistan.",
    "ru": "Ян ван Эйк довёл работу масляными красками до удивительной выразительности, но не изобрёл её с нуля. Более ранние примеры использования масел обнаружены в росписях Афганистана.",
    "en_tags": "#arthistory #oilpaintinghistory #oldmasters",
    "ru_tags": "#историяискусства #историяживописи #старыемастера"
  },
  "3": {
    "en_title": "The Price of Blue",
    "ru_title": "Драгоценный синий",
    "en": "Natural ultramarine was once made from lapis lazuli, a rare stone brought to Europe along long trade routes. Its intense blue made it one of the most prized pigments in Renaissance painting.",
    "ru": "Натуральный ультрамарин получали из лазурита, который доставляли в Европу издалека. Его насыщенный синий был одним из самых ценных пигментов живописи Возрождения.",
    "en_tags": "#ultramarine #artpigments #renaissanceart",
    "ru_tags": "#ультрамарин #пигменты #ренессанс"
  },
  "4": {
    "en_title": "A Tube Changed Art",
    "ru_title": "Тюбик изменил живопись",
    "en": "In 1841, John Goffe Rand patented a collapsible metal paint tube. Portable colours helped artists work outdoors more easily and capture changing light.",
    "ru": "В 1841 году Джон Гофф Рэнд запатентовал металлический тюбик для красок. Удобная упаковка помогла художникам чаще работать на пленэре и ловить меняющийся свет.",
    "en_tags": "#pleinairpainting #arthistory #artistmaterials",
    "ru_tags": "#пленэр #историяискусства #материалыдляживописи"
  },
  "5": {
    "en_title": "Why Oil Feels Alive",
    "ru_title": "Почему масло так выразительно",
    "en": "Oil paint dries slowly enough for an artist to blend edges, build transitions and work wet into wet. Those decisions shape the painting's sense of depth and light.",
    "ru": "Масляная краска сохнет достаточно медленно, чтобы художник мог смягчать границы, смешивать оттенки и работать по сырому. Так рождаются глубина и тонкие переходы света.",
    "en_tags": "#oilpaintingtechnique #brushwork #paintingprocess",
    "ru_tags": "#маслянаяживопись #мазки #техникаживописи"
  },
  "6": {
    "en_title": "Beneath the Surface",
    "ru_title": "Под красочным слоем",
    "en": "Infrared imaging and X-rays can reveal changes hidden beneath a finished painting. Sometimes they show an artist reconsidering the composition while working.",
    "ru": "Инфракрасная съёмка и рентген иногда позволяют увидеть изменения под верхним красочным слоем. Так исследователи находят следы творческих решений художника.",
    "en_tags": "#artrestoration #artresearch #paintingtechniques",
    "ru_tags": "#реставрация #исследованиеживописи #секретыкартин"
  },
  "7": {
    "en_title": "A Painting's Fine Cracks",
    "ru_title": "Кракелюр",
    "en": "Fine cracks in a paint layer are called craquelure. They can reflect age and materials, but new or worsening cracking may also signal a conservation problem.",
    "ru": "Тонкую сетку трещинок на красочном слое называют кракелюром. Она бывает связана с возрастом и материалами, но новые трещины иногда указывают на проблему сохранности.",
    "en_tags": "#craquelure #artconservation #paintings",
    "ru_tags": "#кракелюр #реставрация #сохранениекартин"
  },
  "8": {
    "en_title": "The Mona Lisa Smile",
    "ru_title": "Улыбка Моны Лизы",
    "en": "Leonardo used soft transitions known as sfumato around the Mona Lisa's face. Subtle changes of shadow help make her expression seem different each time we look.",
    "ru": "Леонардо использовал мягкие переходы света и тени - сфумато. Благодаря им выражение лица Моны Лизы кажется изменчивым в зависимости от взгляда зрителя.",
    "en_tags": "#leonardodavinci #sfumato #arthistory",
    "ru_tags": "#леонардодавинчи #сфумато #историяискусства"
  },
  "9": {
    "en_title": "Layers of Colour",
    "ru_title": "Слои цвета",
    "en": "An oil painting is often built in stages: sketch, underpainting, colour and final accents. Layering lets painters adjust depth, light and texture over time.",
    "ru": "Масляная картина нередко рождается поэтапно: рисунок, подмалёвок, цвет и завершающие акценты. Слои позволяют постепенно уточнять свет, глубину и фактуру.",
    "en_tags": "#oilpaintinglayers #paintingtechniques #fineart",
    "ru_tags": "#подмалевок #слоивживописи #живопись"
  },
  "10": {
    "en_title": "How to Keep Art Safe",
    "ru_title": "Как беречь картину",
    "en": "Direct sunlight, high humidity and abrupt temperature changes can damage paintings. A stable environment and thoughtful placement are simple but important steps.",
    "ru": "Прямое солнце, высокая влажность и резкие перепады температуры способны повредить живопись. Стабильные условия и правильное размещение помогут сохранить картину.",
    "en_tags": "#artcare #artconservation #artcollectors",
    "ru_tags": "#уходзакартинами #сохранениеживописи #коллекционерам"
  },
  "11": {
    "en_title": "Van Gogh's Texture",
    "ru_title": "Фактура Ван Гога",
    "en": "Van Gogh often used thick, visible strokes of paint - a technique called impasto. The raised surface makes movement and light part of the painting's physical presence.",
    "ru": "Ван Гог часто писал густыми, заметными мазками - в технике импасто. Рельеф поверхности усиливает ощущение движения и света в самой живописи.",
    "en_tags": "#vangogh #impasto #paintingtexture",
    "ru_tags": "#вангог #импасто #фактураживописи"
  },
  "12": {
    "en_title": "Academic Painting",
    "ru_title": "Академическая школа",
    "en": "St Petersburg's Academy of Arts helped shape a rigorous tradition of drawing, composition and painting. That foundation still informs many contemporary artists' skills.",
    "ru": "Петербургская Академия художеств сформировала традицию серьёзной подготовки в рисунке, композиции и живописи. Эта школа и сегодня влияет на мастерство многих художников.",
    "en_tags": "#academicart #russianart #arteducation",
    "ru_tags": "#академическаяживопись #русскоеискусство #художественнаяшкола"
  },
  "13": {
    "en_title": "Holding the Light",
    "ru_title": "Поймать мгновение",
    "en": "Painters work with something a camera cannot decide for them: which light, gesture or colour matters most. One composition can preserve an impression of a fleeting moment.",
    "ru": "Художник выбирает, какой свет, жест или оттенок станет главным. Благодаря композиции мимолётное впечатление может остаться с нами надолго.",
    "en_tags": "#paintingcomposition #artappreciation #fineart",
    "ru_tags": "#композиция #искусствовдеталях #живопись"
  },
  "14": {
    "en_title": "Pigeons and Paintings",
    "ru_title": "Голуби различают стили",
    "en": "In controlled studies, pigeons learned to distinguish images by some visual features associated with different painting styles. It is a curious example of visual learning, not proof they appreciate art as humans do.",
    "ru": "В экспериментах голуби научились отличать изображения по некоторым визуальным признакам, связанным с живописными стилями. Это пример зрительного обучения, а не доказательство человеческого восприятия искусства.",
    "en_tags": "#artandscience #visualperception #artfacts",
    "ru_tags": "#искусствоинаука #восприятиеискусства #фактыобискусстве"
  },
  "15": {
    "en_title": "Art Changes With Us",
    "ru_title": "Новый взгляд на картину",
    "en": "The painting stays the same, yet we notice different details as our experiences change. Returning to an original artwork can reveal something we missed before.",
    "ru": "Картина остаётся прежней, но с опытом мы замечаем в ней новые детали. Возвращаясь к оригинальному произведению, можно увидеть то, что раньше ускользало.",
    "en_tags": "#artappreciation #originalart #collectingart",
    "ru_tags": "#восприятиеживописи #оригинальнаякартина #искусстводома"
  }
}

IMAGE_PREFIX="https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/facts/"
MSK=ZoneInfo("Europe/Moscow")

def fact_key(fact):
    return "igfact:"+str(fact["id"])

def fact_caption(fact, override=None):
    entry=FACTS.get(str(fact["id"]))
    if not entry:
        raise ValueError("Unreviewed Instagram fact ID")
    override = override or {}
    en = override.get("en") or entry["en"]
    ru = override.get("ru") or entry["ru"]
    return "\n\n".join((
        "ART FACTS · "+entry["en_title"]+"\n"+en,
        "ФАКТЫ ОБ ИСКУССТВЕ · "+entry["ru_title"]+"\n"+ru,
        "#ivoryart #artfacts #arthistory #arteducation "+entry["en_tags"]+
        "\n#фактыобискусстве #историяискусства #живопись "+entry["ru_tags"]
    ))

def fact_media(fact):
    return IMAGE_PREFIX+"fact-"+str(fact["id"]).zfill(2)+".jpg"

def fact_slides(fact, override=None):
    """Four 4:5 slides; a revision is immutable until all JPGs are ready."""
    key=str(fact["id"])
    if key not in FACTS:
        raise ValueError("Unreviewed fact")
    revision=(override or {}).get("revision", "")
    if revision and not re.fullmatch(r"[0-9a-f]{12}",revision):
        raise ValueError("Invalid slide revision")
    suffix="-"+revision if revision else ""
    return [IMAGE_PREFIX+"fact-"+key.zfill(2)+"-"+str(n)+suffix+".jpg"
            for n in range(1,5)]


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
        date_cursor=dt+timedelta(minutes=91)
        if dt.date().isoformat() in existing_dates:continue
        kind="fact" if state.get("ig_facts_enabled") and sequence%3==0 else "artwork"
        if kind=="fact":
            fact=next((f for f in facts if int(f["id"])==next_no),None) if next_no else None
            item={"at":dt.isoformat(),"kind":"fact","format":"post",
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
