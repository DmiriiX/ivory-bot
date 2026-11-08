import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import instagram


class InstagramSafetyTests(unittest.TestCase):
    def test_no_token_means_disabled(self):
        with patch.dict(os.environ, {"BUFFER_API_KEY": ""}):
            self.assertFalse(instagram.token_available())

    def test_html_not_forwarded_to_instagram(self):
        msg = instagram.post_caption({
            "title": "Example",
            "artist": "Artist",
            "caption": "🎨 <b>Art</b> &amp; sculpture",
        })
        self.assertIn("Art & sculpture", msg)
        self.assertNotIn("<b>", msg)
        self.assertIn("ivory-art.com", msg)

    def test_non_https_photo_rejected_before_network(self):
        import asyncio
        async def trial():
            with self.assertRaises(ValueError):
                await instagram.create_buffer_post("id", {"photo": "http://example.com/a.jpg"}, "https://example.com/stable.jpg")
        asyncio.run(trial())

    def test_unsigned_oidc_rejected(self):
        import asyncio
        async def trial():
            with self.assertRaises(Exception) as caught:
                await instagram.verify_github_oidc("")
            self.assertEqual(caught.exception.status_code, 401)
        asyncio.run(trial())

if __name__ == "__main__":
    unittest.main()
