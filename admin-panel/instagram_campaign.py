"""A bounded four-feed-posts-per-week Instagram recovery campaign.

Only fixed UTC-independent Moscow slots are eligible. No scheduling after end_date.
Stories are additional, not counted toward the four weekly feed publications.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

MSK = ZoneInfo("Europe/Moscow")
FEED_DAYS = (1, 3, 5, 6)  # Tuesday, Thursday, Saturday, Sunday
STORY_DAYS = (0, 2, 4)   # Monday, Wednesday, Friday
FEED_TIME = time(18, 15)
STORY_TIME = time(19, 15)


def campaign_window(state, now=None):
    start = date.fromisoformat(state.get("start_date", "2026-11-09"))
    end = date.fromisoformat(state.get("end_date", "2026-12-08"))
    if (end - start).days > 31 or end < start:
        raise ValueError("Invalid monthly campaign period")
    return start, end


def campaign_slot(state, kind="feed", now=None):
    """Next slot, or the current slot if within a 90-minute startup tolerance."""
    if not state.get("enabled", False):
        return {"next_at": None, "reason": "paused"}
    now = (now or datetime.now(MSK)).astimezone(MSK)
    start, end = campaign_window(state, now)
    if now.date() > end:
        return {"next_at": None, "reason": "finished"}
    weekdays, tm = ((FEED_DAYS, FEED_TIME) if kind == "feed"
                    else (STORY_DAYS, STORY_TIME))
    for offset in range(35):
        day = max(start, now.date()) + timedelta(days=offset)
        if day > end:
            break
        # Launch Monday Nov 9 instead of Tuesday Nov 10:
        # exactly four feed posts during the first calendar week.
        kickoff = kind == "feed" and start == date(2026, 11, 9)
        if kickoff and day == start:
            pass
        elif kickoff and day == start + timedelta(days=1):
            continue
        elif day.weekday() not in weekdays:
            continue
        slot = datetime.combine(day, tm, tzinfo=MSK)
        if slot + timedelta(minutes=90) > now:
            return {"next_at": slot.isoformat(), "reason": "scheduled",
                    "timezone": "Europe/Moscow",
                    "note": "Плановый слот, доставка зависит от Buffer"}
    return {"next_at": None, "reason": "finished"}


def due_now(state, kind="feed", now=None):
    now = (now or datetime.now(MSK)).astimezone(MSK)
    scheduled = campaign_slot(state, kind=kind, now=now)
    if not scheduled.get("next_at"):
        return False
    instant = datetime.fromisoformat(scheduled["next_at"])
    return instant <= now < instant + timedelta(minutes=90)


def feed_format(records, available):
    """Alternate 2 Reels and 2 carousels per week when prepared media allows."""
    published = sum(1 for v in records.values()
                    if v.get("status") in ("sent", "accepted")
                    and v.get("campaign") is True)
    desired = ("reel", "carousel", "reel", "carousel")[published % 4]
    if desired in available:
        return desired
    if "carousel" in available:
        return "carousel"
    if "reel" in available:
        return "reel"
    return "post"
