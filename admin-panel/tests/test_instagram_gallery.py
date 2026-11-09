import asyncio
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instagram_gallery import extract_gallery, discover_gallery, format_for_gallery, approved_product_url


class TildaGalleryTests(unittest.TestCase):
    def test_product_schema_and_main_image(self):
        page = """<script type="application/ld+json">
        {"@type":"Product","image":["https://static.tildacdn.com/p/one.jpg",
        "https://static.tildacdn.com/p/two.jpg"]}</script>"""
        urls = extract_gallery(page, "https://static.tildacdn.com/p/one.jpg")
        self.assertEqual(len(urls), 2)
        self.assertEqual(format_for_gallery(urls), "carousel")

    def test_unrelated_webpage_images_not_included(self):
        page = '<img src="https://static.tildacdn.com/unrelated.jpg">'
        urls = extract_gallery(page, "https://static.tildacdn.com/painting.jpg")
        self.assertEqual(urls, ["https://static.tildacdn.com/painting.jpg"])

    def test_gallery_scoped_to_product(self):
        page = """<div class="t-store__prod-popup__slider">
        <img data-original="https://static.tildacdn.com/a.jpg">
        <img src="https://optim.tildacdn.com/b.jpg"></div>"""
        urls = extract_gallery(page, "https://static.tildacdn.com/main.jpg")
        self.assertEqual(len(urls), 3)

    def test_non_tilda_media_rejected(self):
        page = '<script type="application/ld+json">{"@type":"Product","image":["https://evil.example/a.jpg"]}</script>'
        self.assertEqual(len(extract_gallery(page, "https://static.tildacdn.com/main.jpg")), 1)

    def test_reject_external_url_and_redirects(self):
        with self.assertRaises(ValueError):
            approved_product_url("https://example.org/tproduct/1-2")
        with self.assertRaises(ValueError):
            approved_product_url("https://ivory-art.com/admin")

    def test_curated_gallery_without_remote_request(self):
        post = {"photo":"https://static.tildacdn.com/main.jpg",
                "gallery":["https://static.tildacdn.com/detail.jpg"],
                "public_link":"https://ivory-art.com/tproduct/1-2"}
        async def run():
            urls, origin = await discover_gallery(post)
            self.assertEqual(len(urls), 2)
            self.assertEqual(origin, "catalog")
        asyncio.run(run())


if __name__ == "__main__":
    unittest.main()
