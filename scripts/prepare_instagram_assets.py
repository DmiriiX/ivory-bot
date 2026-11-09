#!/usr/bin/env python3
"""Stage Instagram carousel images and silent Reels as durable GitHub assets.

Run from repository root in GitHub Actions. Writes only assets and an index,
never posts to Instagram or touches Telegram/MAX state.
"""
import argparse
import asyncio
import hashlib
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin-panel"))
from instagram_gallery import discover_gallery
from instagram_reel import make_reel
from media import normalized_image

BASE_URL = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/"
INDEX_PATH = ROOT / "instagram_assets.json"
MEDIA_ROOT = ROOT / "instagram-media" / "prepared"


def identity(post):
    value = "painting:" + str(post.get("link") or post.get("title"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


async def prepare(post, existing):
    ident = identity(post)
    images, source = await discover_gallery(post)
    if len(images) < 2:
        return None  # Never fake a multi-photo gallery.
    photos = []
    for number, url in enumerate(images[:5]):
        filename = f"instagram-media/prepared/{ident}-{number+1}.jpg"
        target = ROOT / filename
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(await normalized_image(url))
        photos.append(BASE_URL + filename)
    reel = None
    try:
        video = await make_reel(images[:4])
        video_name = f"instagram-media/prepared/{ident}.mp4"
        (ROOT / video_name).write_bytes(video)
        reel = BASE_URL + video_name
    except Exception as exc:
        # A carousel may still be usable even when video preparation fails.
        print("Reel unavailable:", ident, type(exc).__name__)
    return {"title": post.get("title"), "image_count": len(photos),
            "gallery_source": source, "images": photos, "reel": reel}


async def main(limit):
    posts = json.loads((ROOT / "posts.json").read_text(encoding="utf-8"))
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {"version": 1, "artworks": {}}
    records = index.setdefault("artworks", {})
    handled = 0
    for post in posts:
        ident = identity(post)
        if ident in records:
            continue
        try:
            result = await prepare(post, records.get(ident))
        except Exception as exc:
            print("Skipped unavailable media:", ident, type(exc).__name__)
            continue
        if result is None:
            # Don't permanently cache single-photo results: gallery may grow later.
            continue
        records[ident] = result
        handled += 1
        print("Prepared", ident, result["image_count"], "photos; Reel", bool(result["reel"]))
        if handled >= limit:
            break
    INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Prepared:", handled, "multi-image artworks")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=3)
    args = parser.parse_args()
    asyncio.run(main(max(1, min(args.limit, 5))))
