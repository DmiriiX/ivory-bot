#!/usr/bin/env python3
import json
import os
import random
import sys
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "posts.json"
STATE_FILE = ROOT / "state.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@ivoryartgallery").strip()

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


def api(method, payload):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def should_post_now(state, now):
    if not (WINDOW_START_HOUR <= now.hour < WINDOW_END_HOUR):
        print(f"Outside window ({now.hour}:00 MSK), skip")
        return False

    last_raw = state.get("last_post_at")
    last = None
    if last_raw:
        try:
            last = datetime.fromisoformat(last_raw)
            if last.tzinfo is None:
                last = last.replace(tzinfo=TZ)
            else:
                last = last.astimezone(TZ)
        except Exception:
            last = None

    if last and last.date() == now.date():
        print("Already posted today, skip")
        return False

    if last:
        elapsed = now - last
        if elapsed < timedelta(days=POST_EVERY_DAYS):
            print(f"Only {elapsed} since last post, need {POST_EVERY_DAYS} days")
            return False

    remaining_hours = list(range(now.hour, WINDOW_END_HOUR))
    if not remaining_hours:
        return False

    chosen = random.choice(remaining_hours)
    print(f"Remaining: {remaining_hours}, chosen: {chosen}, now: {now.hour}")
    if now.hour != chosen:
        print("Not this hour, skip")
        return False

    return True


def pick_post(posts, state):
    """Случайный пост, художник не тот же, что в прошлый раз (если возможно)."""
    used = set(state.get("used_indices", []))
    last_artist = (state.get("last_artist") or "").strip().lower()

    # ещё не использованные
    available = [i for i in range(len(posts)) if i not in used]
    if not available:
        # всё показали — начинаем круг заново
        used = set()
        available = list(range(len(posts)))
        print("All posts used, resetting cycle")

    # предпочитаем другого художника
    different = []
    for i in available:
        artist = (posts[i].get("artist") or "").strip().lower()
        if artist and artist != last_artist:
            different.append(i)
        elif not last_artist:
            different.append(i)

    pool = different if different else available
    idx = random.choice(pool)
    return idx


def main():
    if not BOT_TOKEN:
        print("ERROR: BOT_TOKEN is not set")
        sys.exit(1)

    now = datetime.now(TZ)
    print(f"Now MSK: {now.isoformat()}")

    posts = load_json(POSTS_FILE, [])
    state = load_json(
        STATE_FILE,
        {
            "next_index": 0,
            "last_post_at": None,
            "last_artist": None,
            "used_indices": [],
        },
    )

    if not posts:
        print("No posts in posts.json")
        sys.exit(1)

    if not should_post_now(state, now):
        print("No post this run")
        sys.exit(0)

    idx = pick_post(posts, state)
    post = posts[idx]

    caption = post.get("caption", post.get("title", ""))
    photo = post.get("photo", "")
    # ссылка на конкретную работу; если нет — главная галерея
    link = (post.get("link") or "https://ivory-art.com").strip()
    artist = post.get("artist") or ""

    keyboard = {
        "inline_keyboard": [
            [{"text": "🖼 Смотреть эту работу", "url": link}]
        ]
    }

    if photo:
        result = api(
            "sendPhoto",
            {
                "chat_id": CHANNEL_ID,
                "photo": photo,
                "caption": caption,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            },
        )
    else:
        result = api(
            "sendMessage",
            {
                "chat_id": CHANNEL_ID,
                "text": caption,
                "parse_mode": "HTML",
                "reply_markup": keyboard,
            },
        )

    if not result.get("ok"):
        print("Telegram error:", result)
        sys.exit(1)

    used = list(state.get("used_indices", []))
    if idx not in used:
        used.append(idx)

    state["used_indices"] = used
    state["last_artist"] = artist
    state["last_post_at"] = now.isoformat()
    state["next_index"] = idx + 1  # для совместимости
    save_json(STATE_FILE, state)

    title = post.get("title", f"#{idx + 1}")
    print(f"OK: published #{idx + 1}: {title} ({artist})")


if __name__ == "__main__":
    main()
