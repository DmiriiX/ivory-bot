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

    def test_monday_november_ninth_kickoff_replaces_first_tuesday(self):
        campaign = dict(self.campaign, start_date="2026-11-09",
                        end_date="2026-12-08")
        self.assertTrue(due_now(campaign, "feed",
                                datetime(2026, 11, 9, 18, 20, tzinfo=MSK)))
        self.assertFalse(due_now(campaign, "feed",
                                 datetime(2026, 11, 10, 18, 20, tzinfo=MSK)))
        dates = []
        for day in range(9, 16):
            if due_now(campaign, "feed",
                       datetime(2026, 11, day, 18, 20, tzinfo=MSK)):
                dates.append(day)
        self.assertEqual(dates, [9, 12, 14, 15])
        self.assertFalse(due_now(campaign, "feed",
                                 datetime(2026, 12, 9, 18, 20, tzinfo=MSK)))

    def test_four_feed_days_per_week(self):
        actual = []
        for day in range(10, 17):
            stamp = datetime(2026, 11, day, 18, 25, tzinfo=MSK)
            if due_now(self.campaign, "feed", now=stamp):
                actual.append(day)
        self.assertEqual(actual, [10, 12, 14, 15])

    def test_late_github_cron_can_catch_evening_feed_only(self):
        self.assertFalse(due_now(self.campaign, "feed", datetime(2026, 11, 12, 18, 14, tzinfo=MSK)))
        self.assertTrue(due_now(self.campaign, "feed", datetime(2026, 11, 12, 23, 44, tzinfo=MSK)))
        self.assertFalse(due_now(self.campaign, "feed", datetime(2026, 11, 12, 23, 45, tzinfo=MSK)))
        self.assertFalse(due_now(self.campaign, "feed", datetime(2026, 11, 13, 0, 1, tzinfo=MSK)))

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

    def test_legacy_instagram_records_without_campaign_are_ignored(self):
        records = {
            "historic1": {"status": "sent"},
            "historic2": {"status": "sent", "campaign": None},
            "historic3": {"status": "sent", "campaign": False},
        }
        self.assertEqual(feed_format(records, {"reel", "carousel"}), "reel")

    def test_no_reel_fallback_to_carousel(self):
        self.assertEqual(feed_format({}, {"carousel"}), "carousel")


if __name__ == "__main__":
    unittest.main()
