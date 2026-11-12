"""IVORY-ART admin Telegram bot and Mini App backend.

Run with: uvicorn app:app --host 0.0.0.0 --port 8000
All credentials are read from environment. No token is committed to GitHub.
"""
import hashlib
import hmac
import json
import os
import time
from urllib.parse import parse_qsl, quote
from typing import Literal

import httpx
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, Response
import re
from pydantic import BaseModel, Field
import sys
sys.path.insert(0, os.path.dirname(__file__))
from media import normalized_image
from instagram_gallery import discover_gallery, format_for_gallery
from instagram_facts import (
    FACTS, MAX_FACT_CAPTION_LENGTH, fact_caption, fact_key, fact_slide_text,
    fact_slides, next_fact, feed_calendar, cycle_next_kind,
)
from instagram_fact_layout import MAX_SLIDE_TEXT_LENGTH, fact_text_pages
from instagram_editorial import make_editorial_reel
from schedule_info import next_post, next_instagram_check, next_instagram_publication, next_instagram_story
from instagram import post_caption as instagram_post_caption, inspection as buffer_inspection, sync_instagram, verify_github_oidc, get_buffer_status, list_recent_instagram_posts, collect_post_metrics, sync_instagram_story, unavailable_fact_slide

app = FastAPI(title="IVORY-ART Admin", docs_url=None, redoc_url=None)
HERE = os.path.dirname(__file__)
TG_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
OWNER = os.getenv("GITHUB_OWNER", "DmiriiX")
REPOS = {
    "paintings": os.getenv("GITHUB_PAINTINGS_REPO", "ivory-bot"),
    "facts": os.getenv("GITHUB_FACTS_REPO", "ivory-bot-facts"),
}
BASE = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
ADMIN_IDS = {int(x.strip()) for x in os.getenv("ADMIN_TELEGRAM_IDS", "").split(",") if x.strip().isdigit()}
BOT_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET", "")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
MAX_AGE = 3600

async def _telegram_setup():
    """Register webhook and Mini App menu without displaying any credential."""
    if not (TG_TOKEN and BOT_SECRET and BASE.startswith("https://")):
        print("Telegram setup skipped: incomplete environment")
        return
    async with httpx.AsyncClient(timeout=15) as client:
        for method, payload in (
            ("setWebhook", {
                "url": BASE + "/telegram/webhook",
                "secret_token": BOT_SECRET,
                "allowed_updates": ["message"],
                "drop_pending_updates": False,
            }),
            ("setChatMenuButton", {
                "menu_button": {
                    "type": "web_app",
                    "text": "Панель IVORY-ART",
                    "web_app": {"url": BASE},
                },
            }),
        ):
            try:
                response = await client.post(
                    "https://api.telegram.org/bot" + TG_TOKEN + "/" + method,
                    json=payload,
                )
                ok = response.status_code == 200 and response.json().get("ok") is True
                print("Telegram " + method + ": " + ("OK" if ok else "FAILED status " + str(response.status_code)))
            except (httpx.HTTPError, ValueError) as exc:
                print("Telegram " + method + " failed: " + type(exc).__name__)


@app.on_event("startup")
async def register_telegram():
    await _telegram_setup()



def ready():
    if not (TG_TOKEN and GITHUB_TOKEN and ADMIN_IDS and BASE.startswith("https://") and BOT_SECRET):
        raise HTTPException(503, "Server not configured")


def authenticate(init_data: str):
    ready()
    if not init_data:
        raise HTTPException(401, "Telegram authentication required")
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True, strict_parsing=True))
        supplied_hash = pairs.pop("hash")
        if abs(time.time() - int(pairs["auth_date"])) > MAX_AGE:
            raise ValueError("Old Telegram session")
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", TG_TOKEN.encode(), hashlib.sha256).digest()
        expected_hash = hmac.new(secret_key, check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(supplied_hash, expected_hash):
            raise ValueError("Bad signature")
        user = json.loads(pairs["user"])
        if int(user["id"]) not in ADMIN_IDS:
            raise HTTPException(403, "Access denied")
        return user
    except HTTPException:
        raise
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(401, "Invalid Telegram session") from exc


def repo_name(kind):
    if kind not in REPOS:
        raise HTTPException(404, "Unknown bot")
    return REPOS[kind]


async def gh(method, kind, path="", body=None, params=None):
    ready()
    repo = repo_name(kind)
    url = f"https://api.github.com/repos/{quote(OWNER, safe='')}/{quote(repo, safe='')}/{path}"
    async with httpx.AsyncClient(timeout=25) as client:
        res = await client.request(method, url, headers={
            "Authorization": f"Bearer {GITHUB_TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }, json=body, params=params)
    if res.status_code >= 400:
        raise HTTPException(502, f"GitHub error: {res.status_code}")
    return res.json() if res.content else {}


async def read_file(kind, path):
    import base64
    # Keep Instagram runtime state on a separate branch, so data updates
    # cannot redeploy Render and terminate an in-flight Buffer request.
    ref = "instagram-runtime-state" if kind == "paintings" and path == "instagram_state.json" else "main"
    result = await gh("GET", kind, "contents/" + path, params={"ref": ref})
    if result.get("type") != "file":
        raise HTTPException(502, "Unexpected GitHub file type")
    return json.loads(base64.b64decode(result["content"]).decode("utf-8")), result["sha"]


async def update_file(kind, path, data, sha, message):
    import base64
    ref = "instagram-runtime-state" if kind == "paintings" and path == "instagram_state.json" else "main"
    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return await gh("PUT", kind, "contents/" + path, body={
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "sha": sha,
        "branch": ref,
    })


def identity(kind, post):
    if kind == "facts":
        value = "fact:" + str(post.get("id") or post.get("title"))
    else:
        value = "painting:" + str(post.get("link") or post.get("title"))
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def metrics_cipher():
    """Encryption is mandatory because this GitHub repository is public."""
    from cryptography.fernet import Fernet
    key = os.getenv("INSTAGRAM_METRICS_ENCRYPTION_KEY", "").strip()
    if not key:
        raise HTTPException(503, "Instagram metrics encryption key unavailable")
    return Fernet(key.encode("ascii"))


def decode_metrics_file(document):
    import base64
    if not document.get("ciphertext"):
        return {"checked_at": None, "posts": {}}
    try:
        return json.loads(metrics_cipher().decrypt(
            document["ciphertext"].encode("ascii")).decode("utf-8"))
    except Exception as exc:
        raise HTTPException(503, "Unable to decrypt Instagram metrics") from exc


def encode_metrics_file(document):
    data = json.dumps(document, ensure_ascii=False).encode("utf-8")
    return {"ciphertext": metrics_cipher().encrypt(data).decode("ascii")}


async def control_file(kind):
    try:
        return await read_file(kind, "control.json")
    except HTTPException:
        # Default control is read-only if not yet installed.
        return {"paused": False, "excluded_ids": [], "next_id": None}, None


async def snapshot(kind):
    posts, _ = await read_file(kind, "posts.json")
    state, _ = await read_file(kind, "state.json")
    control, _ = await control_file(kind)
    used = set(state.get("used_ids") or [])
    used.update(identity(kind, posts[i]) for i in state.get("used_indices", []) if isinstance(i, int) and 0 <= i < len(posts))
    excluded = set(control.get("excluded_ids") or [])
    pending = state.get("pending")
    records = [
        {
            "id": identity(kind, p),
            "title": str(p.get("title") or ""),
            "artist": str(p.get("artist") or ""),
            "photo": str(p.get("photo") or ""),
            "caption": str(p.get("caption") or ""),
            "link": str(p.get("public_link") or p.get("link") or ""),
            "used": identity(kind, p) in used,
            "excluded": identity(kind, p) in excluded,
        }
        for p in posts
    ]
    next_slot = next_post(kind, state.get("last_post_at"),
                          paused=bool(control.get("paused")), pending=pending,
                          remaining=sum(1 for p in records if not p["used"] and not p["excluded"]))
    return {
        "next_schedule": next_slot,
        "kind": kind,
        "total": len(records),
        "published": sum(1 for p in records if p["used"]),
        "remaining": sum(1 for p in records if not p["used"] and not p["excluded"]),
        "paused": bool(control.get("paused")),
        "last_post_at": state.get("last_post_at"),
        "pending": pending,
        "next_id": control.get("next_id"),
        "posts": records,
    }


async def bot_send(chat_id, text, buttons=None):
    if not TG_TOKEN:
        return
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "HTML"}
    if buttons:
        payload["reply_markup"] = {"inline_keyboard": buttons}
    async with httpx.AsyncClient(timeout=20) as client:
        res = await client.post(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage", json=payload)
        res.raise_for_status()


@app.get("/", response_class=HTMLResponse)
async def index():
    return open(os.path.join(HERE, "index.html"), encoding="utf-8").read()


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/telegram/webhook")
async def telegram_webhook(request: Request, x_telegram_bot_api_secret_token: str = Header(default="")):
    ready()
    if not hmac.compare_digest(x_telegram_bot_api_secret_token, BOT_SECRET):
        raise HTTPException(403, "Bad webhook secret")
    event = await request.json()
    message = event.get("message") or {}
    user = message.get("from") or {}
    chat = message.get("chat") or {}
    if int(user.get("id") or 0) not in ADMIN_IDS or chat.get("type") != "private":
        return {"ok": True}
    command = (message.get("text") or "").split()[0].lower()
    if command in ("/start", "/menu", "/help"):
        await bot_send(chat["id"], "🎨 <b>IVORY-ART | Центр управления</b>\n\nОткройте панель для просмотра очереди, истории и настроек двух ботов.", [[{"text": "Открыть панель", "web_app": {"url": BASE}}]])
    elif command == "/status":
        painting = await snapshot("paintings")
        facts = await snapshot("facts")
        await bot_send(chat["id"], f"🎨 Картины: {painting['published']}/{painting['total']}, {'пауза' if painting['paused'] else 'активен'}\n📚 Факты: {facts['published']}/{facts['total']}, {'пауза' if facts['paused'] else 'активен'}")
    else:
        await bot_send(chat["id"], "Команды: /menu и /status", [[{"text": "Панель", "web_app": {"url": BASE}}]])
    return {"ok": True}


@app.get("/api/{kind}")
async def view(kind: Literal["facts", "paintings"], x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    return await snapshot(kind)


class Toggle(BaseModel):
    paused: bool


@app.post("/api/{kind}/pause")
async def pause(kind: Literal["facts", "paintings"], update: Toggle, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    control, sha = await control_file(kind)
    if not sha:
        raise HTTPException(409, "control.json not installed in this repository")
    control["paused"] = update.paused
    await update_file(kind, "control.json", control, sha, "Admin: " + ("pause" if update.paused else "resume") + " posts")
    return {"paused": update.paused}


class Select(BaseModel):
    id: str = Field(min_length=24, max_length=24)
    excluded: bool | None = None


@app.post("/api/{kind}/exclude")
async def exclude(kind: Literal["facts", "paintings"], data: Select, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    posts, _ = await read_file(kind, "posts.json")
    if data.id not in {identity(kind, p) for p in posts}:
        raise HTTPException(404, "Unknown publication")
    control, sha = await control_file(kind)
    if not sha:
        raise HTTPException(409, "control.json not installed")
    excluded = set(control.get("excluded_ids") or [])
    if data.excluded is True:
        excluded.add(data.id)
    else:
        excluded.discard(data.id)
    control["excluded_ids"] = sorted(excluded)
    if control.get("next_id") in excluded:
        control["next_id"] = None
    await update_file(kind, "control.json", control, sha, "Admin: update excluded posts")
    return {"ok": True}


@app.post("/api/{kind}/next")
async def make_next(kind: Literal["facts", "paintings"], data: Select, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    snap = await snapshot(kind)
    target = next((p for p in snap["posts"] if p["id"] == data.id), None)
    if not target or target["used"] or target["excluded"]:
        raise HTTPException(409, "Post is unavailable")
    if snap["pending"]:
        raise HTTPException(409, "A partial publication is pending; resolve it first")
    control, sha = await control_file(kind)
    if not sha:
        raise HTTPException(409, "control.json not installed")
    control["next_id"] = data.id
    await update_file(kind, "control.json", control, sha, "Admin: choose next publication")
    return {"ok": True}


class EditPost(BaseModel):
    id: str = Field(min_length=24, max_length=24)
    caption: str = Field(max_length=4000)


@app.post("/api/{kind}/caption")
async def caption(kind: Literal["facts", "paintings"], data: EditPost, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    posts, sha = await read_file(kind, "posts.json")
    index = next((i for i, p in enumerate(posts) if identity(kind, p) == data.id), None)
    if index is None:
        raise HTTPException(404, "Post not found")
    if not data.caption.strip():
        raise HTTPException(422, "Caption cannot be empty")
    posts[index]["caption"] = data.caption
    await update_file(kind, "posts.json", posts, sha, "Admin: edit post caption")
    return {"ok": True}


@app.post("/api/{kind}/publish")
async def publish(kind: Literal["facts", "paintings"], x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    current = await snapshot(kind)
    if current["paused"]:
        raise HTTPException(409, "Bot paused")
    if current["pending"]:
        raise HTTPException(409, "Unresolved partial publication")
    if not current["remaining"]:
        raise HTTPException(409, "No new posts")
    # Dispatch uses the existing dedicated workflow, preserving credentials and delivery state.
    await gh("POST", kind, "actions/workflows/post.yml/dispatches", body={
        "ref": "main",
        "inputs": {"dry_run": "false", "force_post": "true"},
    })
    return {"started": True, "note": "GitHub accepted workflow dispatch; delivery is not yet confirmed"}

class InstagramEditorialSwitch(BaseModel):
    enabled: bool

class InstagramEditorialExclude(BaseModel):
    id: int = Field(ge=1, le=10000)
    excluded: bool

class InstagramEditorialSelect(BaseModel):
    id: int = Field(ge=1, le=10000)

class InstagramEditorialEdit(BaseModel):
    kind: Literal["fact","artwork"]
    id: str = Field(min_length=1,max_length=80)
    caption: str = Field(min_length=15,max_length=2200)


@app.get("/api/integrations/instagram/editorial")
async def instagram_editorial(x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    history, _ = await read_file("paintings","instagram_state.json")
    facts,_ = await read_file("facts","posts.json")
    slide_overrides,_ = await read_file("paintings","instagram_fact_slide_overrides.json")
    artworks,_ = await read_file("paintings","posts.json")
    try:
        prepared,_=await read_file("paintings","instagram_assets.json")
        prepared=prepared.get("artworks") or {}
    except HTTPException:
        prepared={}
    records=history.get("records") or {}
    exclusions=set(str(i) for i in history.get("ig_fact_excluded",[]))
    overrides=history.get("ig_fact_captions") or {}
    story_slot=next_instagram_story(history)
    story_records=history.get("story_records") or {}
    used_story_ids={v.get("artwork_id") for v in story_records.values()}
    ready_story=sorted(((key,record) for key,record in records.items()
                        if record.get("status")=="sent" and key not in used_story_ids
                        and len((prepared.get(key) or {}).get("stories") or [])==3),
                       key=lambda pair:pair[1].get("created_at", ""),reverse=True)
    slot_day=story_slot.get("next_at", "")[:10]
    in_progress=next((v.get("artwork_id") for v in story_records.values()
                      if v.get("campaign_date")==slot_day and v.get("artwork_id")),None)
    story_id=in_progress or (ready_story[0][0] if ready_story else None)
    story_artwork=next((p for p in artworks if identity("paintings",p)==story_id),None)
    drafts = []
    for fact in facts:
        fact_id = str(fact["id"])
        if fact_id not in FACTS:
            continue
        edit = slide_overrides.get(fact_id)
        slides = fact_slides(fact, edit)
        en, ru = fact_slide_text(fact, edit)
        drafts.append({
            "id": fact_id, "title": FACTS[fact_id]["ru_title"], "photo": slides[0],
            "caption": overrides.get(fact_id) or fact_caption(fact, edit),
            "slides": slides, "format": "carousel", "slide_en": en, "slide_ru": ru,
            "slides_edited": fact_id in slide_overrides, "excluded": fact_id in exclusions,
            "status": (records.get(fact_key(fact)) or {}).get("status", "queue"),
        })
    return {
        "facts_enabled":bool(history.get("ig_facts_enabled",False)),
        "next_kind":cycle_next_kind(history) if history.get("ig_facts_enabled") else "artwork",
        "calendar":feed_calendar(history,facts,artworks=artworks,
                                 media=prepared if history.get("rich_media_enabled") else {}),
        "story_plan":({"kind":"story","format":"story","at":story_slot["next_at"],
                       "id":story_id,"title":(story_artwork or {}).get("title") or "Работа будет выбрана после публикации картины",
                       "status":"planned"} if story_slot.get("next_at") else None),
        "facts": drafts,
        "artworks":[
            {"id":identity("paintings",p),"title":p.get("title"),"artist":p.get("artist"),
             "photo":p.get("photo"),"caption":(history.get("ig_artwork_captions") or {}).get(identity("paintings",p)) or instagram_post_caption(p),
             "status":(records.get(identity("paintings",p)) or {}).get("status","queue"),
             "format":(records.get(identity("paintings",p)) or {}).get("format"),
             "images":(prepared.get(identity("paintings",p)) or {}).get("images") or [],
             "reel":(prepared.get(identity("paintings",p)) or {}).get("reel"),
             "reel_style":(prepared.get(identity("paintings",p)) or {}).get("reel_style"),
             "stories":(prepared.get(identity("paintings",p)) or {}).get("stories") or [],
             "story_status":next((v.get("status") for v in (history.get("story_records") or {}).values()
                                  if v.get("artwork_id")==identity("paintings",p)),"queue")}
            for p in artworks],
        "selected_fact_id":str((next_fact(facts,history) or {}).get("id") or ""),
    }


@app.post("/api/integrations/instagram/editorial/toggle")
async def instagram_editorial_toggle(data:InstagramEditorialSwitch,
                                     x_telegram_init_data:str=Header(default="")):
    authenticate(x_telegram_init_data)
    history,sha=await read_file("paintings","instagram_state.json")
    if data.enabled:
        facts,_=await read_file("facts","posts.json")
        first=next_fact(facts,history)
        if not first:
            raise HTTPException(409,"No available Instagram facts")
        edits, _ = await read_file("paintings", "instagram_fact_slide_overrides.json")
        missing = await unavailable_fact_slide(fact_slides(first, edits.get(str(first["id"]))))
        if missing is not None:
            raise HTTPException(409, f"Слайд {missing} следующего факта ещё готовится")
    if any(v.get("status") in ("uncertain","accepted") for v in (history.get("records") or {}).values()):
        raise HTTPException(409,"Finish pending Instagram delivery first")
    history["ig_facts_enabled"]=data.enabled
    await update_file("paintings","instagram_state.json",history,sha,
                      "Admin: "+("enable" if data.enabled else "pause")+" independent Instagram facts [skip ci]")
    return {"enabled":data.enabled}


@app.post("/api/integrations/instagram/editorial/caption")
async def instagram_editorial_caption(data:InstagramEditorialEdit,
                                      x_telegram_init_data:str=Header(default="")):
    authenticate(x_telegram_init_data)
    history,sha=await read_file("paintings","instagram_state.json")
    records=history.get("records") or {}
    if data.kind=="fact":
        facts,_=await read_file("facts","posts.json")
        if data.id not in {str(f.get("id")) for f in facts}:
            raise HTTPException(404,"Unknown fact")
        if fact_key({"id":data.id}) in records:
            raise HTTPException(409,"This fact is reserved or already published; cannot edit")
        if len(data.caption.strip()) > MAX_FACT_CAPTION_LENGTH:
            raise HTTPException(422, f"Подпись может содержать до {MAX_FACT_CAPTION_LENGTH} символов")
        target="ig_fact_captions"
    else:
        posts,_=await read_file("paintings","posts.json")
        if data.id not in {identity("paintings",p) for p in posts}:
            raise HTTPException(404,"Unknown artwork")
        if data.id in records:
            raise HTTPException(409,"This artwork is reserved or already published")
        target="ig_artwork_captions"
    history.setdefault(target,{})[data.id]=data.caption.strip()
    await update_file("paintings","instagram_state.json",history,sha,
                      "Admin: update Instagram-only "+data.kind+" draft [skip ci]")
    return {"ok":True,"kind":data.kind,"id":data.id}


class InstagramFactSlideEdit(BaseModel):
    id: int = Field(ge=1,le=15)
    en: str = Field(min_length=20, max_length=MAX_SLIDE_TEXT_LENGTH)
    ru: str = Field(min_length=20, max_length=MAX_SLIDE_TEXT_LENGTH)


@app.post("/api/integrations/instagram/editorial/slides")
async def instagram_editorial_slides(data:InstagramFactSlideEdit,
                                    x_telegram_init_data:str=Header(default="")):
    """Edit EN/RU slide copy before sending; GitHub regenerates versioned JPEGs.

    Published or reserved facts cannot be changed retroactively.
    Each revision becomes publishable once all six slides are available.
    """
    authenticate(x_telegram_init_data)
    history,_=await read_file("paintings","instagram_state.json")
    key=fact_key({"id":data.id})
    if key in (history.get("records") or {}):
        raise HTTPException(409,"Fact reserved or published; cannot change image slides")
    en,ru=data.en.strip(),data.ru.strip()
    try:
        fact_text_pages(en)
        fact_text_pages(ru)
    except ValueError as exc:
        raise HTTPException(422, "Текст должен помещаться на двух слайдах для каждого языка") from exc
    if len(fact_caption({"id": data.id}, {"en": en, "ru": ru})) > MAX_FACT_CAPTION_LENGTH:
        raise HTTPException(422, f"Общий текст подписи должен быть до {MAX_FACT_CAPTION_LENGTH} символов")
    revision=hashlib.sha256((en+"\\0"+ru).encode("utf-8")).hexdigest()[:12]
    edits,sha=await read_file("paintings","instagram_fact_slide_overrides.json")
    edits[str(data.id)]={"en":en,"ru":ru,"revision":revision}
    await update_file("paintings","instagram_fact_slide_overrides.json",edits,sha,
                      "Admin: regenerate versioned bilingual Instagram Fact carousel slides")
    return {"ok":True,"id":data.id,"revision":revision,
            "note":"Готовится новая версия из шести слайдов"}


@app.post("/api/integrations/instagram/editorial/exclude")
async def instagram_editorial_exclude(data:InstagramEditorialExclude,
                                      x_telegram_init_data:str=Header(default="")):
    authenticate(x_telegram_init_data)
    facts,_=await read_file("facts","posts.json")
    if data.id not in {int(f["id"]) for f in facts}:
        raise HTTPException(404,"Unknown fact")
    history,sha=await read_file("paintings","instagram_state.json")
    excluded=set(str(x) for x in history.get("ig_fact_excluded",[]))
    if fact_key({"id":data.id}) in (history.get("records") or {}):
        raise HTTPException(409,"Fact already reserved")
    (excluded.add if data.excluded else excluded.discard)(str(data.id))
    history["ig_fact_excluded"]=sorted(excluded,key=int)
    await update_file("paintings","instagram_state.json",history,sha,
                      "Admin: update excluded Instagram-only facts [skip ci]")
    return {"ok":True}


@app.post("/api/integrations/instagram/editorial/next")
async def instagram_editorial_next(data:InstagramEditorialSelect,
                                   x_telegram_init_data:str=Header(default="")):
    authenticate(x_telegram_init_data)
    history,sha=await read_file("paintings","instagram_state.json")
    facts,_=await read_file("facts","posts.json")
    if data.id not in {int(f["id"]) for f in facts} or fact_key({"id":data.id}) in (history.get("records") or {}):
        raise HTTPException(409,"Fact unavailable")
    if str(data.id) in set(str(x) for x in history.get("ig_fact_excluded",[])):
        raise HTTPException(409,"Fact is excluded")
    history["ig_fact_next_id"]=data.id
    await update_file("paintings","instagram_state.json",history,sha,
                      "Admin: choose next Instagram fact without changing TG/MAX [skip ci]")
    return {"ok":True}


@app.get("/api/integrations/instagram")
async def instagram_status(x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    status = await buffer_inspection()
    try:
        history, _ = await read_file("paintings", "instagram_state.json")
        entries = history.get("records") or {}
        status.update({
            "enabled": bool(history.get("enabled")),
            "next_check": next_instagram_check(enabled=bool(history.get("enabled"))),
            "next_publication": next_instagram_publication(history),
            "next_story": next_instagram_story(history),
            "campaign": history.get("campaign") or {},
            "story_sent": sum(v.get("status") == "sent"
                              for v in (history.get("story_records") or {}).values()),
            "story_accepted": sum(v.get("status") == "accepted"
                                  for v in (history.get("story_records") or {}).values()),
            "rich_media_enabled": bool(history.get("rich_media_enabled", False)),
            "rich_media_ready": 0,
            "metrics_last_checked": None,
            "metrics_posts": [],

            "already_published_before_connection": len(history.get("baseline_ids") or []),
            "accepted": sum(v.get("status") in ("accepted", "sent") for v in entries.values()),
            "sent": sum(v.get("status") == "sent" for v in entries.values()),
            "uncertain": sum(v.get("status") == "uncertain" for v in entries.values()),
            "failed": sum(v.get("status") == "failed" for v in entries.values()),
        })
    except Exception:
        status["enabled"] = False
    try:
        prepared_index, _ = await read_file("paintings", "instagram_assets.json")
        status["rich_media_ready"] = sum(
            isinstance(v.get("images"), list) and len(v["images"]) >= 2
            for v in (prepared_index.get("artworks") or {}).values())
    except Exception:
        pass
    try:
        metrics_document, _ = await read_file("paintings", "instagram_metrics.json")
        metrics = decode_metrics_file(metrics_document)
        status["metrics_last_checked"] = metrics.get("checked_at")
        status["metrics_posts"] = [
            {"title": rec.get("title"), "format": rec.get("format"),
             "external_link": rec.get("external_link"),
             "metrics": (metrics.get("posts") or {}).get(post_id, {}).get("metrics", {}),
             "metrics_updated_at": (metrics.get("posts") or {}).get(post_id, {}).get("metrics_updated_at"),
             "error": (metrics.get("posts") or {}).get(post_id, {}).get("error")}
            for post_id, rec in [*((history.get("records") or {}).items()),
                                 *((history.get("story_records") or {}).items())]
            if rec.get("status") in ("sent", "accepted")
        ]
    except Exception:
        pass
    return status


async def instagram_artwork(artwork_id: str):
    if not re.fullmatch(r"[0-9a-f]{24}", artwork_id):
        raise HTTPException(404, "Invalid artwork")
    posts, _ = await read_file("paintings", "posts.json")
    post = next((p for p in posts if identity("paintings", p) == artwork_id), None)
    if not post:
        raise HTTPException(404, "Artwork not found")
    return post


@app.get("/api/integrations/instagram/artworks")
async def instagram_artworks(x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    posts, _ = await read_file("paintings", "posts.json")
    history, _ = await read_file("paintings", "instagram_state.json")
    recorded = history.get("records") or {}
    return {"automatic_multi_image_enabled": False,
            "note": "Reels/carousels are previews only; existing single-image automation remains unchanged",
            "artworks": [
                {"id": identity("paintings", p), "title": p.get("title"),
                 "artist": p.get("artist"), "photo": p.get("photo"),
                 "published_to_instagram": identity("paintings", p) in recorded}
                for p in posts
            ]}


@app.get("/api/integrations/instagram/preview/{artwork_id}")
async def instagram_preview(artwork_id: str, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    post = await instagram_artwork(artwork_id)
    images, source = await discover_gallery(post)
    return {"id": artwork_id, "title": post.get("title"), "artist": post.get("artist"),
            "images": images, "image_count": len(images),
            "recommended_format": format_for_gallery(images),
            "reel_available": bool(images), "gallery_source": source,
            "draft_only": True,
            "note": "Не является публикацией. Дополнительные фото только из проверенной галереи товара."}


@app.get("/api/integrations/instagram/preview/{artwork_id}/reel")
async def instagram_reel_preview(artwork_id: str, style: Literal["cinematic", "luxury"] = "cinematic",
                                 x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    post = await instagram_artwork(artwork_id)
    images, _ = await discover_gallery(post)
    from instagram_translations import TITLES, ARTISTS
    try:
        video = await make_editorial_reel(
            images[:2], TITLES.get(post.get("title"), post.get("title") or "Original Artwork"),
            ARTISTS.get(post.get("artist"), post.get("artist") or "IVORY ART"), style)
    except Exception as exc:
        print("Reel preview failed", type(exc).__name__)
        raise HTTPException(502, "Reel preview unavailable") from exc
    return Response(video, media_type="video/mp4",
                    headers={"Cache-Control": "no-store", "Content-Disposition": "inline; filename=ivory-preview.mp4"})


class InstagramSwitch(BaseModel):
    enabled: bool


class InstagramSelectedPost(BaseModel):
    kind: Literal["fact", "artwork", "story"]
    id: str = Field(min_length=1, max_length=80)
    format: Literal["carousel", "reel", "post", "story"]


@app.post("/api/integrations/instagram/toggle")
async def instagram_toggle(change: InstagramSwitch, x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    if change.enabled:
        status = await buffer_inspection()
        if not status.get("connected"):
            raise HTTPException(409, "Buffer Instagram @ivoryartgallery is not connected")
    history, sha = await read_file("paintings", "instagram_state.json")
    if any(v.get("status") == "uncertain" for v in (history.get("records") or {}).values()):
        raise HTTPException(409, "Review uncertain Instagram delivery before resuming")
    history["enabled"] = change.enabled
    await update_file("paintings", "instagram_state.json", history, sha,
                      "Admin: enable Instagram" if change.enabled else "Admin: pause Instagram")
    return {"enabled": change.enabled}


class RichMediaSwitch(BaseModel):
    enabled: bool


@app.post("/api/integrations/instagram/rich-media")
async def instagram_rich_media_switch(change: RichMediaSwitch,
                                       x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    index, _ = await read_file("paintings", "instagram_assets.json")
    ready = sum(len(v.get("images") or []) >= 2
                for v in (index.get("artworks") or {}).values())
    if change.enabled and ready < 1:
        raise HTTPException(409, "No tested multi-photo assets are prepared")
    history, sha = await read_file("paintings", "instagram_state.json")
    history["rich_media_enabled"] = change.enabled
    await update_file("paintings", "instagram_state.json", history, sha,
                      "Admin: " + ("enable" if change.enabled else "disable") +
                      " Instagram multi-photo publishing [skip ci]")
    return {"enabled": change.enabled, "ready": ready}


@app.post("/internal/instagram/sync")
async def instagram_sync(request: Request, authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Signed GitHub OIDC token required")
    await verify_github_oidc(authorization[7:])
    return await sync_instagram(read_file, update_file, identity, gh)


@app.post("/api/integrations/instagram/publish")
async def instagram_publish(x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    # Manual action skips the clock, but keeps all delivery and date guards.
    result = await sync_instagram(read_file, update_file, identity, gh, manual=True)
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason") or "Instagram publication needs review")
    return result


@app.post("/api/integrations/instagram/publish-selected")
async def instagram_publish_selected(selection: InstagramSelectedPost,
                                     x_telegram_init_data: str = Header(default="")):
    authenticate(x_telegram_init_data)
    if selection.kind == "fact" and (selection.format != "carousel" or not selection.id.isdigit()):
        raise HTTPException(422, "Invalid fact selection")
    if selection.kind in ("artwork", "story") and not re.fullmatch(r"[0-9a-f]{24}", selection.id):
        raise HTTPException(422, "Invalid artwork selection")
    if selection.kind == "artwork" and selection.format not in ("post", "carousel", "reel"):
        raise HTTPException(422, "Invalid artwork format")
    if selection.kind == "story" and selection.format != "story":
        raise HTTPException(422, "Invalid Story format")
    if selection.kind == "story":
        result = await sync_instagram_story(read_file, update_file, identity,
                                            manual=True, artwork_id=selection.id)
    else:
        result = await sync_instagram(read_file, update_file, identity, gh, manual=True,
                                      selected_kind=selection.kind, selected_id=selection.id,
                                      selected_format=selection.format)
    if not result.get("ok"):
        raise HTTPException(409, result.get("reason") or "Instagram publication needs review")
    return result


@app.post("/internal/instagram/stories")
async def instagram_stories_sync(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Signed GitHub OIDC token required")
    await verify_github_oidc(
        authorization[7:],
        workflow="DmiriiX/ivory-bot/.github/workflows/instagram-stories.yml@refs/heads/main")
    return await sync_instagram_story(read_file, update_file, identity)


@app.post("/internal/instagram/metrics")
async def instagram_metrics_sync(authorization: str = Header(default="")):
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "Signed GitHub OIDC token required")
    await verify_github_oidc(
        authorization[7:],
        workflow="DmiriiX/ivory-bot/.github/workflows/instagram-metrics.yml@refs/heads/main")
    history, _ = await read_file("paintings", "instagram_state.json")
    records = {**(history.get("records") or {}), **(history.get("story_records") or {})}
    results = await collect_post_metrics(records)
    if results and not any("error" not in record for record in results.values()):
        # Preserve last successful snapshot if the experimental API is unavailable.
        return {"ok": False, "reason": "Buffer metrics unavailable", "errors": len(results)}
    from datetime import datetime, timezone
    existing_document, sha = await read_file("paintings", "instagram_metrics.json")
    existing = decode_metrics_file(existing_document)
    existing["checked_at"] = datetime.now(timezone.utc).isoformat()
    existing["posts"] = results
    await update_file("paintings", "instagram_metrics.json", encode_metrics_file(existing), sha,
                      "Update daily Instagram metrics snapshot [skip ci]")
    return {"ok": True, "posts": len(results),
            "with_metrics": sum(bool(p.get("metrics")) for p in results.values())}


@app.on_event("startup")
async def inspect_failed_instagram_posts():
    try:
        history, _ = await read_file("paintings", "instagram_state.json")
        for record in (history.get("records") or {}).values():
            if record.get("buffer_post_id") and record.get("buffer_status") == "error":
                remote = await get_buffer_status(record["buffer_post_id"])
                issue = remote.get("error") or {}
                print("Instagram test delivery diagnosis:", json.dumps({
                    "title": record.get("title"),
                    "status": remote.get("status"),
                    "message": str(issue.get("message") or "")[:360],
                    "support_url": str(issue.get("supportUrl") or "")[:180],
                }, ensure_ascii=False))
    except Exception as exc:
        print("Instagram test diagnostic unavailable:", type(exc).__name__)


@app.on_event("startup")
async def audit_uncertain_instagram_posts():
    try:
        history, _ = await read_file("paintings", "instagram_state.json")
        unsure = [v for v in (history.get("records") or {}).values() if v.get("status") == "uncertain"]
        if not unsure:
            return
        recent = await list_recent_instagram_posts()
        for record in unsure:
            # Read-only audit; log only identifiers and statuses.
            expected = record.get("title")
            from instagram_translations import TITLES
            keyword = TITLES.get(expected, expected)
            matches = [x for x in recent if keyword and keyword.casefold() in (x.get("text") or "").casefold()]
            print("Instagram uncertain-post audit:", json.dumps({
                "title": expected, "matches": [
                    {"id": x.get("id"), "status": x.get("status"),
                     "external_link": x.get("externalLink")}
                    for x in matches[:5]
                ],
            }, ensure_ascii=False))
    except Exception as exc:
        print("Instagram uncertain-post audit error:", str(exc)[:220])


@app.on_event("startup")
async def instagram_probe():
    result = await buffer_inspection()
    print("Buffer Instagram: " + ("CONNECTED" if result.get("connected") else "NOT CONNECTED"))
    if not result.get("connected"):
        print("Buffer diagnostic: " + str(result.get("error", "unavailable"))[:160])



@app.get("/instagram-image/{artwork_id}.jpg")
async def instagram_media(artwork_id: str):
    if not re.fullmatch(r"[0-9a-f]{24}", artwork_id):
        raise HTTPException(404, "Unknown artwork")
    posts, _ = await read_file("paintings", "posts.json")
    post = next((p for p in posts if identity("paintings", p) == artwork_id), None)
    if not post:
        raise HTTPException(404, "Unknown artwork")
    try:
        image = await normalized_image(post.get("photo", ""))
    except (httpx.HTTPError, ValueError, OSError) as exc:
        print("Instagram media preparation failed:", type(exc).__name__)
        raise HTTPException(502, "Artwork image unavailable") from exc
    return Response(image, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})
