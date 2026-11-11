"""Buffer Instagram integration for IVORY-ART.

Uses only server-side Buffer and GitHub credentials. Never exposes either to the browser.
A signed GitHub Actions OIDC token authenticates the scheduled sync request.
"""
import asyncio
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from schedule_info import next_instagram_publication
from instagram_campaign import due_now, feed_format
import base64
from media import normalized_image
from instagram_translations import TITLES, ARTISTS

import httpx
import jwt
from jwt import PyJWKClient
from fastapi import HTTPException

BUFFER_API = "https://api.buffer.com"
AUDIENCE = "ivory-art-instagram-sync"
REPOSITORY_ID = "1345393882"
WORKFLOW_REF = "DmiriiX/ivory-bot/.github/workflows/instagram-sync.yml@refs/heads/main"
OIDC_KEYS = PyJWKClient("https://token.actions.githubusercontent.com/.well-known/jwks", cache_jwk_set=True, lifespan=3600)

def token_available():
    return bool(os.environ.get("BUFFER_API_KEY", "").strip())

async def graphql(query, variables=None):
    token = os.environ.get("BUFFER_API_KEY", "").strip()
    if not token:
        raise RuntimeError("Buffer key is not configured")
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            BUFFER_API,
            headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
            json={"query": query, "variables": variables or {}},
        )
    if response.status_code != 200:
        raise RuntimeError("Buffer returned HTTP " + str(response.status_code))
    data = response.json()
    if data.get("errors"):
        raise RuntimeError("Buffer GraphQL: " + "; ".join(str(x.get("message", ""))[:120] for x in data["errors"]))
    if not isinstance(data.get("data"), dict):
        raise RuntimeError("Invalid Buffer response")
    return data["data"]

async def instagram_channel():
    account = await graphql("query { account { organizations { id name } } }")
    organizations = account.get("account", {}).get("organizations") or []
    matches = []
    for org in organizations:
        result = await graphql(
            "query($id: OrganizationId!) { channels(input: {organizationId: $id}) { id name service } }",
            {"id": org["id"]},
        )
        for channel in result.get("channels") or []:
            if channel.get("service") == "instagram":
                matches.append(channel)
    matched = [c for c in matches if c.get("name", "").lstrip("@").casefold() == "ivoryartgallery"]
    if len(matched) != 1:
        raise RuntimeError("Expected exactly one Instagram channel @ivoryartgallery; found " + str(len(matched)))
    return matched[0]

async def inspection():
    if not token_available():
        return {"configured": False, "connected": False, "error": "BUFFER_API_KEY missing"}
    try:
        channel = await instagram_channel()
        return {"configured": True, "connected": True, "name": channel["name"]}
    except Exception as exc:
        return {"configured": True, "connected": False, "error": str(exc)[:240]}

async def list_recent_instagram_posts(first=30):
    """Read-only Buffer audit to resolve interrupted sends safely."""
    channel = await instagram_channel()
    account = await graphql("query { account { organizations { id name } } }")
    matches = []
    for org in (account.get("account") or {}).get("organizations") or []:
        query = """query($org: OrganizationId!) {
          posts(first: 30, input: {
            organizationId: $org,
            filter: {channelIds: [CHANNEL_PLACEHOLDER]},
            sort: [{field: createdAt, direction: desc}]
          }) { edges { node { id text status createdAt externalLink } } }
        }""".replace("CHANNEL_PLACEHOLDER", json.dumps(channel["id"]))
        response = await graphql(query, {"org": org["id"]})
        matches.extend([x["node"] for x in (response.get("posts") or {}).get("edges") or [] if x.get("node")])
    return matches


async def verify_github_oidc(token, workflow=WORKFLOW_REF):
    if not token:
        raise HTTPException(401, "GitHub OIDC token required")
    try:
        def decode():
            key = OIDC_KEYS.get_signing_key_from_jwt(token).key
            return jwt.decode(token, key, algorithms=["RS256"], audience=AUDIENCE,
                              issuer="https://token.actions.githubusercontent.com",
                              options={"require": ["exp", "iat", "sub", "aud", "iss"]},
                              leeway=30)
        claims = await asyncio.to_thread(decode)
    except Exception as exc:
        raise HTTPException(401, "GitHub OIDC verification failed") from exc
    if not (str(claims.get("repository_id")) == REPOSITORY_ID
            and claims.get("repository") == "DmiriiX/ivory-bot"
            and claims.get("ref") == "refs/heads/main"
            and claims.get("workflow_ref") == workflow
            and claims.get("event_name") in ("schedule", "workflow_dispatch", "push")
            and claims.get("repository_owner") == "DmiriiX"):
        raise HTTPException(403, "Unauthorized GitHub workflow")
    return claims

def post_caption(post):
    """Instagram only: English first, Russian second, bilingual hashtags.

    The catalog remains untouched. Never assume a translation of an unseen
    painting title: use a neutral English heading instead of inventing facts.
    """
    title_ru = html.unescape(str(post.get("title") or "")).strip()
    artist_ru = html.unescape(str(post.get("artist") or "")).strip()
    raw = html.unescape(re.sub(r"<[^>]*>", "", str(post.get("caption") or "")))

    # Extract media and dimensions only when they are present in source data.
    dimensions = re.search(r"(\d{1,4})\s*[×xхХ]\s*(\d{1,4})\s*см", raw, re.IGNORECASE)
    dims_en = (f"{dimensions.group(1)} × {dimensions.group(2)} cm" if dimensions else "")
    dims_ru = (f"{dimensions.group(1)} × {dimensions.group(2)} см" if dimensions else "")
    source = raw.casefold()
    if "акварель" in source and "бумага" in source:
        medium_en = "Watercolor on paper"
        medium_ru = "Бумага, акварель"
        if "карандаш" in source:
            medium_en = "Watercolor and colored pencil on paper"
            medium_ru = "Бумага, акварель, цветной карандаш"
        tags_en = "#watercolor #watercolorpainting"
        tags_ru = "#акварель"
    elif "акрил" in source:
        medium_en, medium_ru = "Acrylic on canvas", "Холст, акрил"
        tags_en, tags_ru = "#acrylicpainting", "#акрил"
    elif "смешан" in source:
        medium_en, medium_ru = "Mixed media on canvas", "Холст, смешанная техника"
        tags_en, tags_ru = "#mixedmediaart", "#смешаннаятехника"
    elif "масло" in source:
        medium_en, medium_ru = "Oil on canvas", "Холст, масло"
        tags_en, tags_ru = "#oilpainting", "#живописьмаслом"
    else:
        medium_en, medium_ru = "Original artwork", ""
        tags_en, tags_ru = "#originalart", "#авторскаяработа"

    title_en = TITLES.get(title_ru, "Original Artwork")
    artist_en = ARTISTS.get(artist_ru, "IVORY-ART Gallery")

    # Curated, verifiable editorial hooks: no fabricated life story or provenance.
    # Deterministic per artwork, so updates do not randomly alter future copy.
    hooks = (
        ("Explore an original artwork and its fine details.",
         "Рассмотрите оригинальную работу и её детали."),
        ("A closer look at the composition and technique.",
         "Присмотритесь к композиции и технике исполнения."),
        ("Discover the work through its colours and textures.",
         "Откройте для себя работу через её цвета и фактуру."),
        ("An original work of art, presented by IVORY-ART Gallery.",
         "Оригинальное произведение искусства из коллекции IVORY-ART."),
    )
    source_id = str(post.get("link") or title_ru)
    hook_index = int(hashlib.sha256(source_id.encode("utf-8")).hexdigest(), 16) % len(hooks)
    intro_en, intro_ru = hooks[hook_index]

    # Genre tags are added only for explicitly listed titles whose subjects
    # are evident; unknown titles retain neutral medium-based tags.
    landscape_titles = {
        "Крым. Бабье лето - 30х50 см", "Альпы", "Горное озеро",
        "Река", "Закат над городом", "Закат", "Гриновский Крым. Балаклава",
    }
    still_life_titles = {"Летний натюрморт", "Маки", "Зеленый чай"}
    genre_tags = (
        ("#landscapepainting", "#пейзаж") if title_ru in landscape_titles else
        ("#stilllifepainting", "#натюрморт") if title_ru in still_life_titles else
        ("", "")
    )

    english = [
        f'🎨 "{title_en}"',
        f'Artist: {artist_en}' if artist_ru and artist_ru != "IVORY-ART" else "IVORY-ART Gallery",
        " · ".join(x for x in [medium_en, dims_en] if x),
        intro_en,
        "",
        "Explore original artworks at ivory-art.com",
    ]
    russian = [
        f'🇷🇺 «{title_ru}»' if title_ru else "🇷🇺 Оригинальная картина",
        artist_ru,
        " · ".join(x for x in [medium_ru, dims_ru] if x),
        intro_ru,
        "",
        "Откройте коллекцию оригинальных произведений на ivory-art.com",
    ]
    tags = " ".join([
        "#ivoryart", "#artgallery", "#contemporaryart", "#originalart",
        tags_en, "#russianart",
        "#картины", "#искусство", "#художники", tags_ru, "#галереякартин",
        *genre_tags,
    ])
    return ("\n".join(english) + "\n\n" + "\n".join(russian)
            + "\n\n" + " ".join(tags.split())).strip()[:2100]

async def ensure_public_image(post, item_id, github_api):
    """Commit an image to public GitHub storage before Buffer reads it."""
    filename = "instagram-media/" + item_id + ".jpg"
    public_url = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/" + filename

    async def available():
        async with httpx.AsyncClient(timeout=25) as client:
            try:
                response = await client.head(public_url, follow_redirects=True)
                return response.status_code == 200 and response.headers.get("content-type", "").startswith("image/")
            except httpx.HTTPError:
                return False

    if await available():
        return public_url
    image_bytes = await normalized_image(post.get("photo") or "")
    await github_api("PUT", "paintings", "contents/" + filename, body={
        "message": "Store stable Instagram artwork " + item_id,
        "content": base64.b64encode(image_bytes).decode("ascii"),
        "branch": "main",
    })
    for _ in range(8):
        if await available():
            return public_url
        await asyncio.sleep(2)
    raise RuntimeError("GitHub-hosted artwork has not yet become publicly accessible")


def rich_media_assets(media, kind):
    """Build verified Buffer assets from pre-rendered public GitHub media."""
    if kind not in ("carousel", "reel"):
        raise ValueError("Unsupported Instagram media format")
    prefix = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/prepared/"
    if kind == "reel":
        link = media.get("reel") or ""
        if not link.startswith(prefix) or not link.endswith(".mp4"):
            raise ValueError("No prepared Reel is available")
        return [{"video": {"url": link}}]
    links = media.get("images") or []
    if not 2 <= len(links) <= 5 or not all(isinstance(url, str) and url.startswith(prefix) and url.endswith(".jpg") for url in links):
        raise ValueError("Carousel photos are unavailable")
    return [{"image": {"url": link}} for link in links]


async def prepared_media_ready(media, kind):
    """Buffer can only fetch media at publicly reachable URLs."""
    assets = rich_media_assets(media, kind)
    urls = [a.get("image", a.get("video"))["url"] for a in assets]
    async with httpx.AsyncClient(timeout=12, follow_redirects=True) as client:
        for link in urls:
            try:
                res = await client.head(link)
                if res.status_code != 200:
                    return False
            except httpx.HTTPError:
                return False
    return True


async def create_buffer_post(channel_id, post, image_url, media=None, kind='post'):
    url = post.get("photo", "")
    if not url.startswith("https://"):
        raise ValueError("Artwork needs a publicly accessible HTTPS image")
    mutation = """
    mutation($input: CreatePostInput!) {
      createPost(input: $input) {
        ... on PostActionSuccess { post { id status channelId } }
        ... on MutationError { message }
      }
    }
    """
    if kind == "story":
        prefix = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/prepared/"
        story_url = (media or {}).get("story") or ""
        if (not story_url.startswith(prefix)
                or not (story_url.endswith("-story.jpg") or any(story_url.endswith(f"-story-{n}.jpg") for n in (1, 2, 3)))):
            raise ValueError("Prepared Story is missing")
        assets = [{"image": {"url": story_url}}]
    elif media is not None:
        assets = rich_media_assets(media, kind)
    else:
        assets = [{"image": {"url": image_url}}]
        kind = "post"
    payload = {
        "text": "" if kind == "story" else post_caption(post),
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow",
        "assets": assets,
        "metadata": {"instagram": {"type": kind, "shouldShareToFeed": kind != "story"}},
    }
    data = await graphql(mutation, {"input": payload})
    result = data.get("createPost") or {}
    if result.get("post", {}).get("id"):
        return result["post"]
    raise ValueError(str(result.get("message") or "Buffer rejected post")[:300])

async def get_buffer_status(buffer_post_id):
    data = await graphql(
        "query($id: PostId!) { post(input: {id: $id}) { id status sentAt externalLink error { message supportUrl } } }",
        {"id": buffer_post_id},
    )
    return data["post"]

async def sync_instagram(read_file, update_file, identity, github_api):
    """One accepted post maximum per run; never resubmit uncertain or accepted IDs."""
    state, sha = await read_file("paintings", "instagram_state.json")
    result = await inspection()
    if not result["connected"]:
        return {"ok": False, "reason": result.get("error", "not connected")}
    if not state.get("enabled", False):
        return {"ok": True, "enabled": False, "reason": "Instagram activation is pending"}
    current, _ = await read_file("paintings", "state.json")
    posts, _ = await read_file("paintings", "posts.json")
    control, _ = await read_file("paintings", "control.json")
    if control.get("paused"):
        return {"ok": True, "reason": "The publisher is paused"}
    used = set(current.get("used_ids") or [])
    used.update(identity("paintings", posts[i]) for i in current.get("used_indices", []) if type(i) is int and 0 <= i < len(posts))
    ignored = set(state.get("baseline_ids") or [])
    records = state.setdefault("records", {})
    # Optional staged media extension. Default false until verified on actual products.
    rich_index = {"artworks": {}}
    if state.get("rich_media_enabled", False):
        try:
            rich_index, _ = await read_file("paintings", "instagram_assets.json")
        except Exception:
            rich_index = {"artworks": {}}

    # Check previously accepted posts without creating duplicates.
    for item_id, record in list(records.items()):
        if record.get("status") == "accepted" and record.get("buffer_post_id"):
            try:
                remote = await get_buffer_status(record["buffer_post_id"])
                if remote.get("status") in ("sent", "error", "failed"):
                    record["status"] = remote["status"]
                    record["external_link"] = remote.get("externalLink")
                    record["checked_at"] = datetime.now(timezone.utc).isoformat()
                    latest = await update_file("paintings", "instagram_state.json", state, sha, "Update Instagram delivery status")
                    sha = (latest.get("content") or {}).get("sha") or (await read_file("paintings", "instagram_state.json"))[1]
            except Exception:
                pass
    # Don't start a second submission if one is uncertain.
    if any(v.get("status") == "uncertain" for v in records.values()):
        return {"ok": False, "reason": "Uncertain delivery requires manual review"}
    if any(v.get("status") == "accepted" for v in records.values()):
        return {"ok": True, "reason": "Previous Buffer publication awaits delivery confirmation"}
    campaign = state.get("campaign") or {}
    in_campaign = bool(campaign.get("enabled"))
    now_msk = datetime.now(ZoneInfo("Europe/Moscow"))
    if in_campaign:
        if not due_now(campaign, "feed", now_msk):
            return {"ok": True, "reason": "No campaign feed slot today",
                    "next_publication": next_instagram_publication(state)}
        if any((rec.get("campaign_date") == now_msk.date().isoformat())
               for rec in records.values()):
            return {"ok": True, "reason": "Feed slot already reserved today"}
    else:
        today_slot = next_instagram_publication(
            state, now=now_msk.replace(hour=18, minute=14, second=0, microsecond=0))
        if (now_msk.hour != 18 or now_msk.minute < 15
                or not today_slot.get("next_at")
                or datetime.fromisoformat(today_slot["next_at"]).date() != now_msk.date()):
            return {"ok": True, "reason": "Instagram cadence: next publishing slot",
                    "next_publication": next_instagram_publication(state)}
    one_shot_id = state.get("test_post_id")
    test_candidate = next((p for p in posts if identity("paintings", p) == one_shot_id
                           and one_shot_id in used and one_shot_id not in records), None)
    available = {k: v for k, v in (rich_index.get("artworks") or {}).items()
                 if len(v.get("images") or []) >= 2}
    if in_campaign:
        # Reels alternate Cinematic / Luxury; only choose prepared artwork with
        # the next style if available, never repeat a previous product.
        next_format = feed_format(records, {"carousel", "reel"})
        reel_count = sum(1 for v in records.values()
                         if v.get("campaign") is True and v.get("status") in ("sent", "accepted")
                         and v.get("format") == "reel")
        preferred_style = ("cinematic", "luxury")[reel_count % 2]
        candidates = [p for p in posts
                      if identity("paintings", p) not in records
                      and identity("paintings", p) not in ignored]
        if next_format == "reel":
            new = next((p for p in candidates
                        if available.get(identity("paintings", p), {}).get("reel_style") == preferred_style
                        and available.get(identity("paintings", p), {}).get("reel")), None)
            if not new:
                new = next((p for p in candidates
                            if available.get(identity("paintings", p), {}).get("reel")), None)
        else:
            new = next((p for p in candidates if identity("paintings", p) in available), None)
        if not new:
            new = candidates[0] if candidates else None
    else:
        new = test_candidate or next((p for p in posts if identity("paintings", p) in used and
                    identity("paintings", p) not in ignored and identity("paintings", p) not in records), None)
    if not new:
        return {"ok": True, "reason": "No eligible artwork to publish"}
    item_id = identity("paintings", new)
    # Write intent before network request; ambiguous failures never duplicate automatically.
    records[item_id] = {
        "title": new.get("title"), "status": "uncertain",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "campaign": in_campaign,
        "campaign_date": now_msk.date().isoformat() if in_campaign else None,
    }
    updated = await update_file("paintings", "instagram_state.json", state, sha, "Reserve artwork for Instagram, prevent duplicates")
    new_sha = updated.get("content", {}).get("sha")
    if not new_sha:
        _, new_sha = await read_file("paintings", "instagram_state.json")
    try:
        prepared = (rich_index.get("artworks") or {}).get(item_id)
        chosen = "post"
        if prepared and prepared.get("image_count", 0) >= 2:
            if in_campaign:
                available_formats = {"carousel"}
                if prepared.get("reel"):
                    available_formats.add("reel")
                chosen = feed_format(records, available_formats)
            else:
                rich_count = sum(1 for rec in records.values() if rec.get("format") in ("carousel", "reel"))
                chosen = "reel" if rich_count % 3 == 2 and prepared.get("reel") else "carousel"
            if not await prepared_media_ready(prepared, chosen):
                chosen = "post"
        image_url = None
        if chosen == "post":
            image_url = await ensure_public_image(new, item_id, github_api)
        remote = await create_buffer_post(
            (await instagram_channel())["id"], new, image_url,
            media=prepared if chosen != "post" else None, kind=chosen)
        records[item_id]["format"] = chosen
        if chosen == "reel" and prepared:
            records[item_id]["reel_style"] = prepared.get("reel_style", "legacy")
    except ValueError as exc:
        records[item_id]["status"] = "failed"
        records[item_id]["error"] = str(exc)[:250]
        await update_file("paintings", "instagram_state.json", state, new_sha, "Record Instagram validation failure")
        return {"ok": False, "reason": "Buffer rejected image/post", "id": item_id}
    except Exception as exc:
        # Do not blindly retry an ambiguous network/Buffer outcome.
        # Record only a bounded diagnostic and preserve the reservation.
        records[item_id]["failure_type"] = type(exc).__name__
        records[item_id]["failure_message"] = str(exc)[:300]
        print("Instagram media request failed:", type(exc).__name__, str(exc)[:300])
        try:
            await update_file("paintings", "instagram_state.json", state, new_sha,
                              "Record uncertain Buffer media failure without retries")
        except Exception:
            pass
        return {"ok": False, "reason": "Unknown Buffer delivery: inspect Buffer queue before retrying", "id": item_id}
    records[item_id]["buffer_post_id"] = remote["id"]
    records[item_id]["buffer_status"] = remote.get("status", "")
    if remote.get("status") in ("error", "failed"):
        records[item_id]["status"] = "failed"
        await update_file("paintings", "instagram_state.json", state, new_sha, "Record Buffer media delivery error")
        return {"ok": False, "id": item_id, "reason": "Buffer failed to publish the image"}
    records[item_id]["status"] = "accepted"
    await update_file("paintings", "instagram_state.json", state, new_sha, "Record Buffer accepted Instagram post")
    return {"ok": True, "id": item_id, "status": "accepted"}


async def sync_instagram_story(read_file, update_file, identity):
    """Publish an editorial three-slide Story sequence, never repeating uncertain sends.

    Each slide has its own durable reservation/Buffer ID on the runtime-only
    branch. Re-entry continues only missing slides of the SAME selected artwork.
    """
    state, sha = await read_file("paintings", "instagram_state.json")
    campaign = state.get("campaign") or {}
    now_msk = datetime.now(ZoneInfo("Europe/Moscow"))
    if not state.get("enabled") or not due_now(campaign, "story", now_msk):
        return {"ok": True, "reason": "No Story campaign slot"}

    today = now_msk.date().isoformat()
    records = state.setdefault("story_records", {})
    # Reconcile earlier Buffer Story deliveries for honest panel statistics.
    # Never count accepted-as-sent unless Buffer confirms "sent".
    changed = False
    old_accepted = [(key, v) for key, v in records.items()
                    if v.get("status") == "accepted" and v.get("buffer_post_id")]
    for key, old in old_accepted[:8]:
        try:
            remote = await get_buffer_status(old["buffer_post_id"])
            status = remote.get("status")
            if status in ("sent", "error", "failed"):
                old["status"] = status
                old["external_link"] = remote.get("externalLink")
                old["checked_at"] = datetime.now(timezone.utc).isoformat()
                changed = True
        except Exception:
            # Keep the original accepted record if the status check fails.
            pass
    if changed:
        updated = await update_file(
            "paintings", "instagram_state.json", state, sha,
            "Reconcile earlier Instagram Story delivery statuses [skip ci]")
        sha = (updated.get("content") or {}).get("sha") or (
            await read_file("paintings", "instagram_state.json"))[1]
    # One attempted series per date; never silently substitute a second artwork.
    today_records = [v for v in records.values()
                     if v.get("campaign_date") == today]
    existing_artworks = {v.get("artwork_id") for v in today_records}
    if len(existing_artworks) > 1:
        return {"ok": False, "reason": "Conflicting Story series needs manual review"}
    if any(v.get("status") == "uncertain" for v in records.values()):
        return {"ok": False, "reason": "Uncertain Story delivery needs manual review"}
    if any(v.get("status") in ("failed", "error") for v in today_records):
        return {"ok": False, "reason": "Rejected Story slide needs manual review"}

    posts, _ = await read_file("paintings", "posts.json")
    rich, _ = await read_file("paintings", "instagram_assets.json")
    assets = rich.get("artworks") or {}
    if existing_artworks:
        selected = next(iter(existing_artworks))
    else:
        # Only work from already-confirmed Instagram feed publications.
        previously_used = {v.get("artwork_id") for v in records.values()}
        published = sorted(
            [(i, v) for i, v in (state.get("records") or {}).items()
             if v.get("status") == "sent"
             and i in assets and len(assets[i].get("stories") or []) == 3
             and i not in previously_used],
            key=lambda x: x[1].get("created_at", ""), reverse=True)
        selected = published[0][0] if published else None

    if not selected:
        return {"ok": True, "reason": "No confirmed artwork with a prepared three-slide Story"}
    post = next((p for p in posts if identity("paintings", p) == selected), None)
    slides = (assets.get(selected) or {}).get("stories") or []
    if not post or len(slides) != 3:
        return {"ok": False, "reason": "Three-slide Story media is not prepared"}

    prefix = "https://raw.githubusercontent.com/DmiriiX/ivory-bot/main/instagram-media/prepared/"
    if any(not isinstance(url, str) or not url.startswith(prefix)
           or not url.endswith("-story-" + str(i) + ".jpg")
           for i, url in enumerate(slides, 1)):
        return {"ok": False, "reason": "Invalid branded Story URLs"}

    # Check all three images BEFORE sending any of the sequence.
    async with httpx.AsyncClient(timeout=16, follow_redirects=True) as client:
        for url in slides:
            try:
                response = await client.head(url)
                if response.status_code != 200 or not response.headers.get("content-type", "").startswith("image/"):
                    return {"ok": False, "reason": "Branded Story images unavailable"}
            except httpx.HTTPError:
                return {"ok": False, "reason": "Branded Story images unavailable"}

    channel_id = (await instagram_channel())["id"]
    accepted = 0
    for i, image_url in enumerate(slides, 1):
        record_key = f"{today}:{selected}:slide-{i}"
        previous = records.get(record_key)
        if previous:
            if previous.get("status") in ("accepted", "sent") and previous.get("buffer_post_id"):
                accepted += 1
                continue
            # Prevent retries of uncertain or rejected individual frames.
            return {"ok": False, "reason": "Story slide needs manual review",
                    "slide": i, "accepted": accepted}

        records[record_key] = {
            "artwork_id": selected, "title": post.get("title"),
            "campaign_date": today, "slide": i, "total_slides": 3,
            "format": "story", "status": "uncertain",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        updated = await update_file(
            "paintings", "instagram_state.json", state, sha,
            f"Reserve Instagram Story frame {i}/3 without duplicates [skip ci]")
        sha = (updated.get("content") or {}).get("sha") or (
            await read_file("paintings", "instagram_state.json"))[1]
        try:
            remote = await create_buffer_post(
                channel_id, post, None,
                media={"story": image_url}, kind="story")
        except ValueError as exc:
            records[record_key]["status"] = "failed"
            records[record_key]["error"] = str(exc)[:230]
            await update_file(
                "paintings", "instagram_state.json", state, sha,
                f"Record Buffer rejected Story frame {i} [skip ci]")
            return {"ok": False, "reason": "Buffer rejected Story slide",
                    "slide": i, "accepted": accepted}
        except Exception as exc:
            # The request may have been accepted before a network failure.
            records[record_key]["failure_type"] = type(exc).__name__
            try:
                await update_file(
                    "paintings", "instagram_state.json", state, sha,
                    f"Record uncertain Story frame {i} [skip ci]")
            except Exception:
                pass
            return {"ok": False, "reason": "Story delivery uncertain; inspect Buffer",
                    "slide": i, "accepted": accepted}
        records[record_key]["status"] = "accepted"
        records[record_key]["buffer_post_id"] = remote["id"]
        records[record_key]["buffer_status"] = remote.get("status")
        updated = await update_file(
            "paintings", "instagram_state.json", state, sha,
            f"Record accepted Instagram Story frame {i}/3 [skip ci]")
        sha = (updated.get("content") or {}).get("sha") or (
            await read_file("paintings", "instagram_state.json"))[1]
        accepted += 1

    return {"ok": True, "status": "accepted", "format": "story_triptych",
            "artwork_id": selected, "slides_accepted": accepted,
            "note": "Buffer acceptance is not proof of Instagram delivery"}


async def collect_post_metrics(records):
    """Read-only experimental Buffer metrics; absence means unknown, never zero."""
    results = {}
    for artwork_id, record in records.items():
        post_id = record.get("buffer_post_id")
        if not post_id or record.get("status") not in ("sent", "accepted"):
            continue
        try:
            data = await graphql(
                """query($id: PostId!) {
                  post(input: {id: $id}) {
                    id status metrics { type name value unit } metricsUpdatedAt
                  }
                }""",
                {"id": post_id},
            )
            item = data.get("post") or {}
            result = {"status": item.get("status"),
                      "metrics_updated_at": item.get("metricsUpdatedAt"),
                      "metrics": {}}
            for metric in item.get("metrics") or []:
                kind = metric.get("type")
                value = metric.get("value")
                if kind and isinstance(value, (int, float)) and not isinstance(value, bool):
                    result["metrics"][kind] = {"value": value,
                                               "unit": metric.get("unit") or "count"}
            results[artwork_id] = result
        except Exception as exc:
            results[artwork_id] = {"error": str(exc)[:180], "metrics": {},
                                   "metrics_updated_at": None}
    return results
