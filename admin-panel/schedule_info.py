"""Predict the next eligible GitHub Actions publishing slot in Moscow time.

Prediction mirrors scripts/post_once.py due() exactly; GitHub Actions may
start later or fail, and a manual post can change the next eligible date.
"""
import hashlib
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")


def next_post(kind, last_post_at=None, paused=False, pending=None,
              remaining=1, now=None):
    if paused:
        return {"next_at": None, "reason": "paused"}
    if pending:
        return {"next_at": None, "reason": "pending"}
    if remaining <= 0:
        return {"next_at": None, "reason": "empty"}
    now = (now or datetime.now(MSK)).astimezone(MSK)
    last_date = None
    if last_post_at:
        try:
            value = datetime.fromisoformat(last_post_at)
            if value.tzinfo is None:
                value = value.replace(tzinfo=MSK)
            last_date = value.astimezone(MSK).date()
        except (TypeError, ValueError):
            pass
    facts = kind == "facts"
    start, end = (18, 21) if facts else (11, 20)
    interval = 7 if facts else 3
    for day_offset in range(0, 120):
        day = now.date() + timedelta(days=day_offset)
        if facts and day.weekday() != 3:
            continue
        if last_date and (day - last_date).days < interval:
            continue
        date_key = ("facts:" if facts else "paintings:") + str(day)
        hour = start + int(hashlib.sha256(date_key.encode()).hexdigest(), 16) % (end - start)
        candidate = datetime.combine(day, time(hour, 0), tzinfo=MSK)
        if candidate <= now:
            continue
        return {
            "next_at": candidate.isoformat(),
            "reason": "scheduled",
            "timezone": "Europe/Moscow",
            "note": "Расчётное время запуска GitHub Actions, не гарантия доставки",
        }
    return {"next_at": None, "reason": "unavailable"}


def next_instagram_check(now=None, enabled=True):
    if not enabled:
        return {"next_at": None, "reason": "paused"}
    now = (now or datetime.now(MSK)).astimezone(MSK)
    # GitHub cron: 08:15-18:15 UTC == 11:15-21:15 Moscow.
    for d in range(3):
        date = now.date() + timedelta(days=d)
        for hour in range(11, 22):
            slot = datetime.combine(date, time(hour, 15), tzinfo=MSK)
            if slot > now:
                return {"next_at": slot.isoformat(), "reason": "check_only",
                        "timezone": "Europe/Moscow"}
    return {"next_at": None, "reason": "unavailable"}



def next_instagram_publication(history, now=None):
    """Report campaign's four feed slots/week or legacy Instagram cadence."""
    if not history.get("enabled", False):
        return {"next_at": None, "reason": "paused"}
    if (history.get("campaign") or {}).get("enabled", False):
        from instagram_campaign import campaign_slot
        current = (now or datetime.now(MSK)).astimezone(MSK)
        reserved = {v.get("campaign_date") for v in (history.get("records") or {}).values()}
        slot = campaign_slot(history["campaign"], "feed", current)
        if slot.get("next_at") and datetime.fromisoformat(slot["next_at"]).date().isoformat() in reserved:
            return campaign_slot(history["campaign"], "feed", current + timedelta(days=1))
        return slot
    now = (now or datetime.now(MSK)).astimezone(MSK)
    if not history.get("enabled", False):
        return {"next_at": None, "reason": "paused"}
    records = history.get("records") or {}
    if any(v.get("status") == "uncertain" for v in records.values()):
        return {"next_at": None, "reason": "pending"}
    if any(v.get("status") == "accepted" for v in records.values()):
        # Wait for Buffer to confirm the previous post before scheduling another.
        return {"next_at": None, "reason": "pending"}
    latest = None
    for record in records.values():
        if record.get("status") != "sent":
            continue
        try:
            stamp = datetime.fromisoformat(record["created_at"])
            stamp = stamp.replace(tzinfo=MSK) if stamp.tzinfo is None else stamp
            latest = max(latest, stamp.astimezone(MSK)) if latest else stamp.astimezone(MSK)
        except (KeyError, TypeError, ValueError):
            continue
    earliest = latest.date() + timedelta(days=2) if latest else now.date()
    for offset in range(120):
        day = max(now.date(), earliest) + timedelta(days=offset)
        slot = datetime.combine(day, time(18, 15), tzinfo=MSK)
        if slot > now:
            return {"next_at": slot.isoformat(), "reason": "scheduled",
                    "timezone": "Europe/Moscow",
                    "note": "Только при наличии новой картины, опубликованной в Telegram и MAX"}
    return {"next_at": None, "reason": "unavailable"}


def next_instagram_story(history, now=None):
    """Upcoming Instagram Story slot during the monthly recovery campaign."""
    from instagram_campaign import campaign_slot
    if not history.get("enabled", False):
        return {"next_at": None, "reason": "paused"}
    campaign = history.get("campaign") or {}
    current = (now or datetime.now(MSK)).astimezone(MSK)
    # Once all three frames were accepted for today, the current slot is
    # finished. Never keep showing "awaiting launch" after successful handoff.
    today = current.date().isoformat()
    today_records = [v for v in (history.get("story_records") or {}).values()
                     if v.get("campaign_date") == today]
    if (len(today_records) >= 3 and
        all(v.get("status") in ("accepted", "sent") for v in today_records)):
        from datetime import timedelta
        current = datetime.combine(current.date() + timedelta(days=1),
                                   time(0, 0), tzinfo=MSK)
    return campaign_slot(campaign, "story", current)
