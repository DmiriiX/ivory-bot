#!/usr/bin/env python3
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_FILE = ROOT / "posts.json"
STATE_FILE = ROOT / "state.json"

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@ivoryartgallery").strip()

if not BOT_TOKEN:
    print("ERROR: BOT_TOKEN is not set")
    sys.exit(1)


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


def main():
    posts = load_json(POSTS_FILE, [])
    state = load_json(STATE_FILE, {"next_index": 0})

    if not posts:
        print("No posts in posts.json")
        sys.exit(1)

    idx = int(state.get("next_index", 0))
    if idx >= len(posts):
        idx = 0
        print("Reached end of list, starting over")

    post = posts[idx]
    caption = post.get("caption", post.get("title", ""))
    photo = post.get("photo", "")
    link = post.get("link", "https://ivory-art.com")

    keyboard = {
        "inline_keyboard": [
            [{"text": "🎨 Смотреть в галерее", "url": link}]
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

    state["next_index"] = idx + 1
    save_json(STATE_FILE, state)

    title = post.get("title", f"#{idx + 1}")
    print(f"OK: published post #{idx + 1}: {title}")


if __name__ == "__main__":
    main()
