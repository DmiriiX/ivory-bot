#!/usr/bin/env python3
"""Автопостинг картин IVORY-ART в Telegram и MAX."""

import json
import os
import random
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# MAX API: сертификаты на GitHub runners часто не доверяются
ssl._create_default_https_context = ssl._create_unverified_context

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "posts.json"
STATE_FILE = ROOT / "state.json"

TG_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
TG_CHANNEL = os.environ.get("CHANNEL_ID", "@ivoryartgallery").strip()

MAX_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL = os.environ.get("MAX_CHANNEL_ID", "-73462616868288").strip()

TZ = ZoneInfo("Europe/Moscow")
POST_EVERY_DAYS = 3
WINDOW_START_HOUR = 11
WINDOW_END_HOUR = 20
BUTTON_TEXT = "Больше картин на нашем сайте"
DEFAULT_LINK = "https://ivory-art.com/catalog"


def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def http_json(url, payload=None, headers=None, method=None):
    data = None
    hdrs = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        hdrs["Content-Type"] = "application/json; charset=utf-8"
        method = method or "POST"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method or "GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"HTTP {e.code} {e.reason}: {err_body}")
        try:
            return json.loads(err_body)
        except Exception:
            return {"ok": False, "description": err_body, "error_code": e.code}


def should_post_now(state, now):
    if not (WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR):
        print(f"Outside window ({now.hour}:00 MSK), skip")
        return False

    last = None
    if state.get("last_post_at"):
        try:
            last = datetime.fromisoformat(state["last_post_at"])
            if last.tzinfo is None:
                last = last.replace(tzinfo=TZ)
            else:
                last = last.astimezone(TZ)
        except Exception:
            last = None

    if last and last.date() == now.date():
        print("Already posted today, skip")
        return False

    if last and (now - last) < timedelta(days=POST_EVERY_DAYS):
        print(f"Need {POST_EVERY_DAYS} days since last post, skip")
        return False

    remaining = list(range(now.hour, WINDOW_END_HOUR))
    if not remaining:
        return False
    chosen = random.choice(remaining)
    print(f"Remaining {remaining}, chosen {chosen}, now {now.hour}")
    if now.hour != chosen:
        print("Not this hour, skip")
        return False
    return True


def pick_post(posts, state):
    used = set(state.get("used_indices", []))
    last_artist = (state.get("last_artist") or "").strip().lower()
    available = [i for i in range(len(posts)) if i not in used]
    if not available:
        print("All posts used, resetting cycle")
        available = list(range(len(posts)))
        state["used_indices"] = []

    different = [
        i
        for i in available
        if (posts[i].get("artist") or "").strip().lower() != last_artist
    ]
    pool = different if different else available
    return random.choice(pool)


def safe_caption(text: str, limit: int = 1024) -> str:
    """Telegram caption max 1024; убираем опасные для HTML символы без тегов."""
    if not text:
        return ""
    # оставляем только разрешённые нами теги
    text = text.replace("<b>", "\x00b\x00").replace("</b>", "\x00/b\x00")
    text = text.replace("<i>", "\x00i\x00").replace("</i>", "\x00/i\x00")
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = (
        text.replace("\x00b\x00", "<b>")
        .replace("\x00/b\x00", "</b>")
        .replace("\x00i\x00", "<i>")
        .replace("\x00/i\x00", "</i>")
    )
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text


def post_telegram(post):
    if not TG_TOKEN:
        print("Skip Telegram: no BOT_TOKEN")
        return False

    caption = safe_caption(post.get("caption", post.get("title", "")))
    photo = (post.get("photo") or "").strip()
    link = (post.get("link") or DEFAULT_LINK).strip()
    if not link.startswith("http"):
        link = DEFAULT_LINK

    keyboard = {"inline_keyboard": [[{"text": BUTTON_TEXT, "url": link}]]}

    print(f"TG photo: {photo[:80]}...")
    print(f"TG caption length: {len(caption)}")

    result = None
    if photo:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TG_CHANNEL,
            "photo": photo,
            "caption": caption,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }
        result = http_json(url, payload)
        if result.get("ok"):
            print("Telegram OK (photo)")
            return True
        print("Telegram sendPhoto failed, trying without parse_mode...")
        payload.pop("parse_mode", None)
        result = http_json(url, payload)
        if result.get("ok"):
            print("Telegram OK (photo, no parse_mode)")
            return True
        print("Telegram sendPhoto failed, falling back to text...")

    # fallback: текст + ссылка на картину в caption
    text = caption
    if photo:
        text = f"{caption}\n\n{photo}" if caption else photo
        text = text[:4090]
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    payload = {
        "chat_id": TG_CHANNEL,
        "text": text or "IVORY-ART",
        "parse_mode": "HTML",
        "reply_markup": keyboard,
        "disable_web_page_preview": False,
    }
    result = http_json(url, payload)
    if result.get("ok"):
        print("Telegram OK (text fallback)")
        return True

    # last try without HTML
    payload.pop("parse_mode", None)
    result = http_json(url, payload)
    if result.get("ok"):
        print("Telegram OK (text, no parse_mode)")
        return True

    print("Telegram error:", result)
    return False


def post_max(post):
    if not MAX_TOKEN:
        print("Skip MAX: no MAX_BOT_TOKEN")
        return False

    text = post.get("caption", post.get("title", "")) or ""
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        text = text.replace(tag, "")
    text = text[:4000]

    photo = (post.get("photo") or "").strip()
    link = (post.get("link") or DEFAULT_LINK).strip()
    if not link.startswith("http"):
        link = DEFAULT_LINK

    attachments = []
    if photo:
        attachments.append({"type": "image", "payload": {"url": photo}})
    attachments.append(
        {
            "type": "inline_keyboard",
            "payload": {
                "buttons": [[{"type": "link", "text": BUTTON_TEXT, "url": link}]]
            },
        }
    )

    url = f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL}"
    headers = {"Authorization": MAX_TOKEN}
    payload = {"text": text, "attachments": attachments}

    try:
        result = http_json(url, payload, headers=headers)
        mid = (
            result.get("message", {}).get("body", {}).get("mid")
            if isinstance(result, dict)
            else None
        )
        if mid or result.get("message"):
            print("MAX OK:", mid or "sent")
            return True
        print("MAX unexpected response:", result)
        return False
    except Exception as e:
        print("MAX error:", e)
        return False


def main():
    now = datetime.now(TZ)
    print(f"Now MSK: {now.isoformat()}")

    posts = load_json(POSTS_FILE, [])
    state = load_json(
        STATE_FILE,
        {"last_post_at": None, "last_artist": None, "used_indices": []},
    )

    if not posts:
        print("No posts in posts.json")
        sys.exit(1)

    force = os.environ.get("FORCE_POST", "").strip() == "1"
    if not force and not should_post_now(state, now):
        print("No post this run")
        sys.exit(0)

    idx = pick_post(posts, state)
    post = posts[idx]
    title = post.get("title", f"#{idx}")
    artist = post.get("artist", "")
    print(f"Selected #{idx}: {title} ({artist})")

    ok_tg = post_telegram(post)
    ok_max = post_max(post)

    if not ok_tg and not ok_max:
        print("Both channels failed")
        sys.exit(1)

    # состояние обновляем, если хотя бы один канал принял пост
    used = list(state.get("used_indices", []))
    if idx not in used:
        used.append(idx)
    state["used_indices"] = used
    state["last_artist"] = artist
    state["last_post_at"] = now.isoformat()
    save_json(STATE_FILE, state)
    print(f"Done: {title} ({artist}) TG={ok_tg} MAX={ok_max}")


if __name__ == "__main__":
    main()
