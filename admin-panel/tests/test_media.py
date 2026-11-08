import asyncio
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
import media


class FakeResponse:
    def __init__(self, content):
        self.content = content

    def raise_for_status(self):
        return None


class FakeClient:
    def __init__(self, content, *args, **kwargs):
        self.content = content

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    async def get(self, *_args, **_kwargs):
        return FakeResponse(self.content)


class MediaTests(unittest.TestCase):
    def test_portrait_image_is_padded_not_cropped(self):
        src = BytesIO()
        Image.new("RGB", (300, 400), "#E33A1F").save(src, format="JPEG")
        with patch.object(media.httpx, "AsyncClient", lambda **kwargs: FakeClient(src.getvalue())):
            output = asyncio.run(media.normalized_image(
                "https://static.tildacdn.com/a/example.jpg"
            ))
        result = Image.open(BytesIO(output))
        self.assertEqual(result.size, (1080, 1350))
        self.assertEqual(result.getpixel((540, 675))[0] > 150, True)

    def test_block_other_image_hosts(self):
        with self.assertRaises(ValueError):
            asyncio.run(media.normalized_image("https://example.com/internal.png"))

if __name__ == "__main__":
    unittest.main()
