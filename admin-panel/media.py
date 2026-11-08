"""Prepare artwork photographs for Instagram without cropping the painting."""
from io import BytesIO
from urllib.parse import urlsplit

import httpx
from PIL import Image, ImageOps

ALLOWED_HOSTS = {"static.tildacdn.com", "optim.tildacdn.com"}
WIDTH, HEIGHT = 1080, 1350


async def normalized_image(source: str) -> bytes:
    parsed = urlsplit(source)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("Invalid artwork media origin")
    async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
        response = await client.get(source, headers={"User-Agent": "Mozilla/5.0 (compatible; IvoryArt/1.0)"})
        response.raise_for_status()
        if len(response.content) > 15000000 or not response.content:
            raise ValueError("Image is empty or too large")
    with Image.open(BytesIO(response.content)) as opened:
        if opened.width * opened.height > 80_000_000:
            raise ValueError("Image dimensions too large")
        photo = ImageOps.exif_transpose(opened).convert("RGB")
        photo.thumbnail((1040, 1310), Image.Resampling.LANCZOS)
        # Neutral warm mat preserves the entire artwork, even if 3:4 or landscape.
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (247, 245, 240))
        x = (WIDTH - photo.width) // 2
        y = (HEIGHT - photo.height) // 2
        canvas.paste(photo, (x, y))
        output = BytesIO()
        canvas.save(output, format="JPEG", quality=90, optimize=True, progressive=False)
        return output.getvalue()
