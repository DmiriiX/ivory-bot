import sys
import unittest
from datetime import datetime
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instagram_campaign import MSK, campaign_slot, due_now, feed_format


class RecoveryCampaignTests(unittest.TestCase):
    def setUp(self):
        self.campaign = {"enabled": True, "start_date": "2026-11-10",
                         "end_date": "2026-12-09"}

    def test_four_feed_days_per_week(self):
        actual = []
        for day in range(10, 17):
            stamp = datetime(2026, 11, day, 18, 25, tzinfo=MSK)
            if due_now(self.campaign, "feed", now=stamp):
                actual.append(day)
        self.assertEqual(actual, [10, 12, 14, 15])

    def test_story_slots_do_not_count_as_feed(self):
        stamp = datetime(2026, 11, 11, 19, 25, tzinfo=MSK)
        self.assertTrue(due_now(self.campaign, "story", now=stamp))
        self.assertFalse(due_now(self.campaign, "feed", now=stamp))

    def test_campaign_ends_after_december_ninth(self):
        slot = campaign_slot(self.campaign, "feed",
                             datetime(2026, 12, 10, 10, 0, tzinfo=MSK))
        self.assertEqual(slot["reason"], "finished")
        self.assertFalse(due_now(self.campaign, "feed",
                                 datetime(2026, 12, 10, 18, 20, tzinfo=MSK)))

    def test_four_format_rotation(self):
        records = {}
        self.assertEqual(feed_format(records, {"reel", "carousel"}), "reel")
        for i, kind in enumerate(("reel", "carousel", "reel")):
            records[str(i)] = {"campaign": True, "status": "sent", "format": kind}
            self.assertEqual(feed_format(records, {"reel", "carousel"}),
                             ("carousel", "reel", "carousel")[i])

    def test_no_reel_fallback_to_carousel(self):
        self.assertEqual(feed_format({}, {"carousel"}), "carousel")


if __name__ == "__main__":
    unittest.main()
