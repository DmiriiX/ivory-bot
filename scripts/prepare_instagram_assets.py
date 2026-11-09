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
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "admin-panel"))
from instagram_gallery import discover_gallery, product_uid
from instagram_reel import make_reel
from instagram_story import story_image
from instagram_translations import TITLES, ARTISTS
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
    story_path = f"instagram-media/prepared/{ident}-story.jpg"
    story_bytes = story_image(await normalized_image(images[0]),
                               TITLES.get(post.get("title"), "Original Artwork"),
                               ARTISTS.get(post.get("artist"), "IVORY ART Gallery"))
    (ROOT / story_path).write_bytes(story_bytes)
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
            "gallery_source": source, "images": photos, "reel": reel,
            "story": BASE_URL + story_path, "music": "Original IVORY ART instrumental ambient"}


async def main(limit):
    posts = json.loads((ROOT / "posts.json").read_text(encoding="utf-8"))
    index = json.loads(INDEX_PATH.read_text(encoding="utf-8")) if INDEX_PATH.exists() else {"version": 1, "artworks": {}}
    records = index.setdefault("artworks", {})
    if os.environ.get("IVORY_MEDIA_DEBUG") == "1":
        print("Product UID examples:", [product_uid(p) for p in posts[:3]])
    handled = 0
    # Bound requests per scheduled run; rotate across the catalog.
    cursor = ((datetime.now(timezone.utc).date().toordinal() * 12) % max(1, len(posts)))
    retries = [p for p in posts if identity(p) in records and
               (not records[identity(p)].get("reel") or not records[identity(p)].get("story"))]
    scan = retries[:3] + [posts[(cursor + offset) % len(posts)] for offset in range(min(12, len(posts)))]
    for post in scan:
        ident = identity(post)
        if ident in records and records[ident].get("reel") and records[ident].get("story"):
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
