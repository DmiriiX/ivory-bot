"""Generate a conservative, silent Instagram Reel from real product photographs.

No AI-generated fake angles or altered painting content. Rendered on demand;
this is a preview only, not a publicly hosted Buffer asset.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from io import BytesIO

from PIL import Image, ImageOps
from media import normalized_image

REEL_SIZE = (720, 1280)
FPS = 15


def frame_image(image_bytes):
    with Image.open(BytesIO(image_bytes)) as src:
        image = ImageOps.exif_transpose(src).convert("RGB")
        image.thumbnail((680, 1180), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", REEL_SIZE, (247, 245, 240))
        canvas.paste(image, ((720-image.width)//2, (1280-image.height)//2))
        return canvas


def encode_reel(files, output):
    if not shutil.which("ffmpeg"):
        raise RuntimeError("ffmpeg is not installed")
    count = len(files)
    if not 1 <= count <= 5:
        raise ValueError("Reel requires one to five images")
    args = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for p in files:
        args += ["-i", str(p)]
    filters = []
    for i in range(count):
        filters.append(
            f"[{i}:v]zoompan=z='min(zoom+0.0007,1.075)':d=45:s=720x1280:fps=15,"
            f"trim=duration=3,setpts=PTS-STARTPTS[v{i}]"
        )
    filters.append("".join(f"[v{i}]" for i in range(count)) +
                   f"concat=n={count}:v=1:a=0[out]")
    args += ["-filter_complex", ";".join(filters),
             "-map", "[out]", "-r", str(FPS), "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-an", str(output)]
    subprocess.run(args, check=True, timeout=100, capture_output=True)
    if not output.exists() or output.stat().st_size > 35_000_000:
        raise ValueError("Invalid reel output")
    return output.read_bytes()


async def make_reel(images):
    if not 1 <= len(images) <= 5:
        raise ValueError("Choose between 1 and 5 images")
    with tempfile.TemporaryDirectory(prefix="ivory-reel-") as location:
        root = Path(location)
        files = []
        for i, source in enumerate(images):
            # Strict Tilda domain allowlist and size constraints in normalized_image.
            data = await normalized_image(source)
            p = root / f"frame-{i}.jpg"
            await asyncio.to_thread(frame_image, data).save if False else asyncio.sleep(0)
            frame = await asyncio.to_thread(frame_image, data)
            frame.save(p, "JPEG", quality=88)
            files.append(p)
        return await asyncio.to_thread(encode_reel, files, root / "preview.mp4")
