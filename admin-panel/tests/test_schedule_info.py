import sys
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from schedule_info import next_post, next_instagram_check, next_instagram_publication, MSK

class UpcomingScheduleTests(unittest.TestCase):
    def test_paintings_next_eligible_date_and_deterministic_hour(self):
        now=datetime(2026,11,9,0,10,tzinfo=MSK)
        x=next_post("paintings","2026-11-05T18:50:51+03:00",now=now)
        dt=datetime.fromisoformat(x["next_at"])
        self.assertEqual(dt.date().isoformat(),"2026-11-09")
        self.assertTrue(11 <= dt.hour < 20)
        self.assertEqual(dt.minute, 0)

    def test_facts_next_thursday(self):
        now=datetime(2026,11,9,0,10,tzinfo=MSK)
        x=next_post("facts","2026-09-24T19:17:40+03:00",now=now)
        dt=datetime.fromisoformat(x["next_at"])
        self.assertEqual(dt.date().isoformat(),"2026-11-12")
        self.assertTrue(18 <= dt.hour < 21)

    def test_pause_or_no_queue_has_no_time(self):
        self.assertEqual(next_post("paintings",paused=True)["reason"],"paused")
        self.assertEqual(next_post("paintings",remaining=0)["reason"],"empty")
        self.assertEqual(next_post("paintings",pending={"id":"x"})["reason"],"pending")

    def test_instagram_cadence_after_recent_sent_post(self):
        history = {"enabled": True, "records": {
            "art": {"status": "sent", "created_at": "2026-11-08T22:22:37+00:00"}}}
        now = datetime(2026, 11, 9, 9, 15, tzinfo=MSK)
        slot = next_instagram_publication(history, now=now)
        self.assertEqual(slot["next_at"], "2026-11-11T18:15:00+03:00")
        self.assertEqual(slot["reason"], "scheduled")

    def test_instagram_held_when_delivery_unknown(self):
        history = {"enabled": True, "records": {"a": {"status": "uncertain"}}}
        self.assertEqual(next_instagram_publication(history)["reason"], "pending")

    def test_instagram_held_until_buffer_confirms_delivery(self):
        history = {"enabled": True, "records": {"a": {"status": "accepted"}}}
        self.assertEqual(next_instagram_publication(history)["reason"], "pending")

    def test_instagram_check_is_not_publishing_promise(self):
        now=datetime(2026,11,9,17,55,tzinfo=MSK)
        slot=next_instagram_check(now=now)
        dt=datetime.fromisoformat(slot["next_at"])
        self.assertEqual((dt.hour,dt.minute),(18,15))
        self.assertEqual(slot["reason"],"check_only")

    def test_instagram_check_after_last_hour_rolls_to_tomorrow(self):
        now=datetime(2026,11,9,21,35,tzinfo=MSK)
        slot=next_instagram_check(now=now)
        dt=datetime.fromisoformat(slot["next_at"])
        self.assertEqual((dt.hour,dt.minute),(11,15))
        self.assertEqual(dt.date().isoformat(),"2026-11-10")

if __name__=="__main__":
    unittest.main()
