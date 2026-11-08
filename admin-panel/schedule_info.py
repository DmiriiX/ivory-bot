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
