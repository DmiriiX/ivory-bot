"""Regression tests: new button links must never reset published history."""
import json
import re
import unittest
from pathlib import Path
from unittest.mock import patch
import os

from test_posting import load

ROOT = Path(__file__).resolve().parents[1]


class CurrentCatalogLinksTests(unittest.TestCase):
    def test_all_fifty_have_validated_homepage_hash_links(self):
        posts = json.loads((ROOT / "posts.json").read_text(encoding="utf-8"))
        self.assertEqual(len(posts), 50)
        ids = set()
        for p in posts:
            old = re.search(r"/shop/tproduct/521041493-(\d+)-", p["link"])
            new = re.fullmatch(r"https://ivory-art[.]com/#ia-product-([0-9]+)", p["public_link"])
            self.assertIsNotNone(old, p["title"])
            self.assertIsNotNone(new, p["title"])
            self.assertEqual(old.group(1), new.group(1), p["title"])
            self.assertNotIn(new.group(1), ids)
            ids.add(new.group(1))

    def test_all_used_post_ids_remain_unchanged(self):
        posts = json.loads((ROOT / "posts.json").read_text(encoding="utf-8"))
        state = json.loads((ROOT / "state.json").read_text(encoding="utf-8"))
        bot = load("paintings")
        for i, item_id in zip(state["used_indices"], [
            "e63bc6c81d88e3327f657bc4",
            "dfc448216171e629b20e8c5a",
            "c4c1e41d8b62058571526ab4",
            "3b539193b85b606dcd1e043c",
        ]):
            self.assertEqual(bot.key(posts[i]), item_id)
            self.assertIn(bot.key(posts[i]), state["used_ids"])

    def test_telegram_and_max_buttons_use_public_link(self):
        bot = load("paintings")
        post = {"link": "https://ivory-art.com/shop/tproduct/521041493-769304391932-ekzotichnii-ekzemplyar",
                "public_link": "https://ivory-art.com/#ia-product-769304391932",
                "caption": "Test", "title": "Test"}
        with patch.dict(os.environ, {"BOT_TOKEN": "token", "CHANNEL_ID": "@channel"}):
            with patch.object(bot, "multipart", return_value=({}, False)) as sent:
                bot.telegram(post, (b"test", "image/jpeg"))
                self.assertIn(post["public_link"], sent.call_args.args[1]["reply_markup"])
        with patch.dict(os.environ, {"MAX_BOT_TOKEN": "token", "MAX_CHANNEL_ID": "chat"}):
            with patch.object(bot, "max_upload", return_value="photo_token"):
                with patch.object(bot, "call", return_value=({}, False)) as sent:
                    bot.max_send(post, (b"test", "image/jpeg"))
                    payload = sent.call_args.args[1]
                    self.assertEqual(payload["attachments"][1]["payload"]["buttons"][0][0]["url"], post["public_link"])

    def test_legacy_link_is_forced_to_new_product_modal(self):
        bot = load("paintings")
        old_post = {
            "link": "https://ivory-art.com/shop/tproduct/521041493-769304391932-ekzotichnii-ekzemplyar",
            "public_link": "https://ivory-art.com/tproduct/1-769304391932-ekzotichnii-ekzemplyar",
        }
        self.assertEqual(bot.artwork_url(old_post),
                         "https://ivory-art.com/#ia-product-769304391932")

    def test_missing_product_id_cannot_make_broken_post_link(self):
        bot = load("paintings")
        with self.assertRaises(ValueError):
            bot.artwork_url({"link": "https://ivory-art.com/shop/tproduct/bad"})


if __name__ == "__main__":
    unittest.main()
