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
        self.assertTrue(msg.startswith('🎨 "Original Artwork"'))
        self.assertNotIn("<b>", msg)
        self.assertIn("ivory-art.com", msg)
        self.assertIn("#artgallery", msg)
        self.assertIn("#картины", msg)

    def test_english_before_russian_on_existing_catalog_artwork(self):
        msg = instagram.post_caption({
            "title": "Отражения",
            "artist": "Котунов Дмитрий",
            "caption": "🎨 <b>Отражения</b>\\nКотунов Дмитрий\\n\\nхолст, масло · 30 × 40 см",
        })
        self.assertTrue(msg.startswith('🎨 "Reflections"'))
        self.assertIn("Artist: Dmitry Kotunov", msg)
        self.assertIn("Oil on canvas · 30 × 40 cm", msg)
        self.assertIn("🇷🇺 «Отражения»", msg)
        self.assertIn("Холст, масло · 30 × 40 см", msg)
        self.assertLess(msg.index('🎨 "Reflections"'), msg.index("🇷🇺"))
        self.assertIn("#oilpainting", msg)
        self.assertIn("#живописьмаслом", msg)
        self.assertLess(len(msg), 2200)

    def test_curated_translations_cover_every_catalog_item(self):
        import json
        from instagram_translations import TITLES, ARTISTS
        posts = json.loads((HERE.parent / "posts.json").read_text(encoding="utf-8"))
        self.assertEqual(len(posts), 50)
        self.assertTrue(all(p["title"] in TITLES for p in posts))
        self.assertTrue(all(p["artist"] in ARTISTS for p in posts))

    def test_metrics_only_include_values_returned_by_buffer(self):
        import asyncio
        from unittest.mock import AsyncMock
        async def trial():
            payload = {"post": {"id": "buffer1", "status": "sent",
                "metricsUpdatedAt": "2026-11-09T07:00:00Z",
                "metrics": [{"type": "reach", "name": "Reach", "value": 55,
                             "unit": "count"}]}}
            with patch.object(instagram, "graphql", new=AsyncMock(return_value=payload)):
                data = await instagram.collect_post_metrics({"art1": {
                    "buffer_post_id": "buffer1", "status": "sent"}})
            self.assertEqual(data["art1"]["metrics"]["reach"]["value"], 55)
            self.assertNotIn("impressions", data["art1"]["metrics"])
        asyncio.run(trial())

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
