#!/usr/bin/env python3
"""Stage Instagram carousel images, branded Stories and music Reels.

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
from instagram_editorial import make_editorial_reel
from instagram_story import story_triptych
from instagram_translations import TITLES, ARTISTS
from media import normalized_image

BASE_URL = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/"
INDEX_PATH = ROOT / "instagram_assets.json"
MEDIA_ROOT = ROOT / "instagram-media" / "prepared"


def identity(post):
    value = "painting:" + str(post.get("link") or post.get("title"))
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


async def prepare(post, existing, style):
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
    title_ru = post.get("title") or "Авторская картина"
    artist_ru = post.get("artist") or "IVORY ART"
    import re
    clean = re.sub(r"<[^>]+>", "", post.get("caption") or "")
    dims = re.search(r"\\d{1,4}\\s*[×xхХ]\\s*\\d{1,4}\\s*см", clean)
    sources = [await normalized_image(u) for u in images[:2]]
    pack = story_triptych(sources, title_ru, artist_ru,
                          dims.group(0) if dims else "")
    story_urls = []
    for slide, data in enumerate(pack, 1):
        story_path = f"instagram-media/prepared/{ident}-story-{slide}.jpg"
        (ROOT / story_path).write_bytes(data)
        story_urls.append(BASE_URL + story_path)
    reel = None
    try:
        video = await make_editorial_reel(images[:2],
                          TITLES.get(title_ru, title_ru),
                          ARTISTS.get(artist_ru, artist_ru), style)
        video_name = f"instagram-media/prepared/{ident}-{style}.mp4"
        (ROOT / video_name).write_bytes(video)
        reel = BASE_URL + video_name
    except Exception as exc:
        print("Editorial Reel unavailable:", ident, style, type(exc).__name__)
    return {"title": title_ru, "image_count": len(photos),
            "gallery_source": source, "images": photos, "reel": reel,
            "reel_style": style if reel else None,
            "stories": story_urls, "story": story_urls[0],
            "creative_version": 2,
            "music": "Original IVORY ART instrumental ambient",
            "reel_fps": 30 if reel else None}


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
               (not records[identity(p)].get("reel") or not records[identity(p)].get("story")
                or records[identity(p)].get("reel_fps", 0) < 23
                or records[identity(p)].get("creative_version", 0) < 2)]
    scan = retries[:12] + [posts[(cursor + offset) % len(posts)] for offset in range(min(12, len(posts)))]
    for post in scan:
        ident = identity(post)
        # Alternate catalogue positions: a balanced supply for both styles.
        style = 'cinematic' if posts.index(post) % 2 == 0 else 'luxury'
        if (ident in records and records[ident].get("reel") and records[ident].get("story")
                and records[ident].get("reel_fps", 0) >= 23
                and records[ident].get("creative_version", 0) >= 2):
            continue
        try:
            result = await prepare(post, records.get(ident), style)
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
    asyncio.run(main(max(1, min(args.limit, 12))))
