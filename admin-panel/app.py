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
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

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
    result = await gh("GET", kind, "contents/" + path, params={"ref": "main"})
    if result.get("type") != "file":
        raise HTTPException(502, "Unexpected GitHub file type")
    return json.loads(base64.b64decode(result["content"]).decode("utf-8")), result["sha"]


async def update_file(kind, path, data, sha, message):
    import base64
    content = (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    return await gh("PUT", kind, "contents/" + path, body={
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "sha": sha,
        "branch": "main",
    })


def identity(kind, post):
    if kind == "facts":
        value = "fact:" + str(post.get("id") or post.get("title"))
    else:
        value = "painting:" + str(post.get("link") or post.get("title"))
    return hashlib.sha256(value.encode()).hexdigest()[:24]


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
            "link": str(p.get("link") or ""),
            "used": identity(kind, p) in used,
            "excluded": identity(kind, p) in excluded,
        }
        for p in posts
    ]
    return {
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
