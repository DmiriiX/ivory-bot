#!/usr/bin/env python3
import json
import os
import random
import sys
import urllib.request
import ssl
ssl._create_default_https_context = ssl._create_unverified_context
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "posts.json"
STATE_FILE = ROOT / "state.json"

# Telegram
TG_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
TG_CHANNEL = os.environ.get("CHANNEL_ID", "@ivoryartgallery").strip()

# MAX
MAX_TOKEN = os.environ.get("MAX_BOT_TOKEN", "").strip()
MAX_CHANNEL = os.environ.get("MAX_CHANNEL_ID", "-73462616868288").strip()

TZ = ZoneInfo("Europe/Moscow")
POST_EVERY_DAYS = 3
WINDOW_START_HOUR = 11
WINDOW_END_HOUR = 20

def load_json(path, default):
    if path.exists():
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def http_json(url, payload=None, headers=None, method="GET"):
    data = None
    hdrs = headers or {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        hdrs = {**hdrs, "Content-Type": "application/json"}
        method = "POST"
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}

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
        print(f"Need {POST_EVERY_DAYS} days since last post")
        return False

    remaining = list(range(now.hour, WINDOW_END_HOUR))
    if not remaining:
        return False
    chosen = random.choice(remaining)
    print(f"Remaining {remaining}, chosen {chosen}, now {now.hour}")
    return now.hour == chosen

def pick_post(posts, state):
    used = set(state.get("used_indices", []))
    last_artist = (state.get("last_artist") or "").strip().lower()
    available = [i for i in range(len(posts)) if i not in used]
    if not available:
        used = set()
        available = list(range(len(posts)))
        print("Reset cycle")
    different = [
        i for i in available
        if (posts[i].get("artist") or "").strip().lower() != last_artist
    ]
    pool = different if different else available
    return random.choice(pool)

def post_telegram(post):
    if not TG_TOKEN:
        print("Skip Telegram: no BOT_TOKEN")
        return False
    caption = post.get("caption", post.get("title", ""))
    photo = post.get("photo", "")
    link = (post.get("link") or "https://ivory-art.com").strip()
    keyboard = {
        "inline_keyboard": [[{"text": "🖼 Смотреть эту работу", "url": link}]]
    }
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto"
    payload = {
        "chat_id": TG_CHANNEL,
        "photo": photo,
        "caption": caption,
        "parse_mode": "HTML",
        "reply_markup": keyboard,
    }
    if not photo:
        url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
        payload = {
            "chat_id": TG_CHANNEL,
            "text": caption,
            "parse_mode": "HTML",
            "reply_markup": keyboard,
        }
    result = http_json(url, payload)
    if not result.get("ok"):
        print("Telegram error:", result)
        return False
    print("Telegram OK")
    return True

def post_max(post):
    if not MAX_TOKEN:
        print("Skip MAX: no MAX_BOT_TOKEN")
        return False
    text = post.get("caption", post.get("title", ""))
    # MAX: убираем простые HTML-теги для надёжности
    for tag in ("<b>", "</b>", "<i>", "</i>"):
        text = text.replace(tag, "")
    photo = post.get("photo", "")
    link = (post.get("link") or "https://ivory-art.com").strip()

    attachments = []
    if photo:
        attachments.append({
            "type": "image",
            "payload": {"url": photo},
        })
    attachments.append({
        "type": "inline_keyboard",
        "payload": {
            "buttons": [[{
                "type": "link",
                "text": "Смотреть эту работу",
                "url": link,
            }]]
        },
    })

    url = f"https://platform-api2.max.ru/messages?chat_id={MAX_CHANNEL}"
    headers = {"Authorization": MAX_TOKEN}
    # некоторые кабинеты ждут Bearer
    if not MAX_TOKEN.lower().startswith("bearer "):
        headers["Authorization"] = MAX_TOKEN

    payload = {"text": text, "attachments": attachments, "format": "html"}
    try:
        result = http_json(url, payload, headers=headers)
        print("MAX response:", result)
        print("MAX OK")
        return True
    except Exception as e:
        # повтор с Bearer
        headers["Authorization"] = f"Bearer {MAX_TOKEN}"
        try:
            result = http_json(url, payload, headers=headers)
            print("MAX response (Bearer):", result)
            print("MAX OK")
            return True
        except Exception as e2:
            print("MAX error:", e2)
            return False

def main():
    now = datetime.now(TZ)
    print(f"Now MSK: {now.isoformat()}")

    posts = load_json(POSTS_FILE, [])
    state = load_json(STATE_FILE, {
        "last_post_at": None,
        "last_artist": None,
        "used_indices": [],
    })

    if not posts:
        print("No posts")
        sys.exit(1)

    # ручной запуск workflow_dispatch всегда публикует (для теста)
    force = os.environ.get("FORCE_POST", "").strip() == "1"
    if not force and not should_post_now(state, now):
        print("No post this run")
        sys.exit(0)

    idx = pick_post(posts, state)
    post = posts[idx]
    title = post.get("title", str(idx))
    artist = post.get("artist", "")

    ok_tg = post_telegram(post)
    ok_max = post_max(post)

    if not ok_tg and not ok_max:
        print("Both failed")
        sys.exit(1)

    used = list(state.get("used_indices", []))
    if idx not in used:
        used.append(idx)
    state["used_indices"] = used
    state["last_artist"] = artist
    state["last_post_at"] = now.isoformat()
    save_json(STATE_FILE, state)
    print(f"Done: {title} ({artist})")

if __name__ == "__main__":
    main()
