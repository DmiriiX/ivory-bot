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

async def verify_github_oidc(token):
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
            and claims.get("workflow_ref") == WORKFLOW_REF
            and claims.get("event_name") in ("schedule", "workflow_dispatch")
            and claims.get("repository_owner") == "DmiriiX"):
        raise HTTPException(403, "Unauthorized GitHub workflow")
    return claims

def post_caption(post):
    raw = re.sub(r"<[^>]+>", "", post.get("caption") or "")
    raw = html.unescape(raw).strip()
    title = post.get("title") or ""
    artist = post.get("artist") or ""
    return (raw + "\n\n" + "Картины и скульптуры: ivory-art.com\n" +
            "#ivoryart #картины #живопись #искусство").strip()[:2100]

async def create_buffer_post(channel_id, post):
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
    payload = {
        "text": post_caption(post),
        "channelId": channel_id,
        "schedulingType": "automatic",
        "mode": "shareNow",
        "assets": [{"image": {"url": url}}],
        "metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}},
    }
    data = await graphql(mutation, {"input": payload})
    result = data.get("createPost") or {}
    if result.get("post", {}).get("id"):
        return result["post"]
    raise ValueError(str(result.get("message") or "Buffer rejected post")[:300])

async def get_buffer_status(buffer_post_id):
    data = await graphql(
        "query($id: PostId!) { post(input: {id: $id}) { id status sentAt externalLink } }",
        {"id": buffer_post_id},
    )
    return data["post"]

async def sync_instagram(read_file, update_file, identity):
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
    # Check previously accepted posts without creating duplicates.
    for item_id, record in list(records.items()):
        if record.get("status") == "accepted" and record.get("buffer_post_id"):
            try:
                remote = await get_buffer_status(record["buffer_post_id"])
                if remote.get("status") in ("sent", "failed"):
                    record["status"] = remote["status"]
                    record["external_link"] = remote.get("externalLink")
                    record["checked_at"] = datetime.now(timezone.utc).isoformat()
                    await update_file("paintings", "instagram_state.json", state, sha, "Update Instagram delivery status")
                    return {"ok": True, "checked": item_id, "status": record["status"]}
            except Exception:
                pass
    # Don't start a second submission if one is uncertain.
    if any(v.get("status") == "uncertain" for v in records.values()):
        return {"ok": False, "reason": "Uncertain delivery requires manual review"}
    new = next((p for p in posts if identity("paintings", p) in used and
                identity("paintings", p) not in ignored and identity("paintings", p) not in records), None)
    if not new:
        return {"ok": True, "reason": "No new confirmed painting to sync"}
    item_id = identity("paintings", new)
    # Write intent before network request; ambiguous failures never duplicate automatically.
    records[item_id] = {
        "title": new.get("title"), "status": "uncertain",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    updated = await update_file("paintings", "instagram_state.json", state, sha, "Reserve artwork for Instagram, prevent duplicates")
    new_sha = updated.get("content", {}).get("sha")
    if not new_sha:
        _, new_sha = await read_file("paintings", "instagram_state.json")
    try:
        remote = await create_buffer_post((await instagram_channel())["id"], new)
    except ValueError as exc:
        records[item_id]["status"] = "failed"
        records[item_id]["error"] = str(exc)[:250]
        await update_file("paintings", "instagram_state.json", state, new_sha, "Record Instagram validation failure")
        return {"ok": False, "reason": "Buffer rejected image/post", "id": item_id}
    except Exception:
        # Unknown outcome; keep uncertain for operator review.
        return {"ok": False, "reason": "Unknown Buffer delivery: inspect Buffer queue before retrying", "id": item_id}
    records[item_id]["status"] = "accepted"
    records[item_id]["buffer_post_id"] = remote["id"]
    records[item_id]["buffer_status"] = remote.get("status", "")
    await update_file("paintings", "instagram_state.json", state, new_sha, "Record Buffer accepted post")
    return {"ok": True, "id": item_id, "status": "accepted"}
