"""Generate a minimal, music-backed Instagram Reel from real artwork photographs.

No AI-generated fake angles or altered painting content. Rendered on demand;
this is a preview only, not a publicly hosted Buffer asset.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
import math
import wave
import struct
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



def original_ambient_audio(destination, duration):
    """Generate original instrumental audio, no third-party music or rights claims.

    Warm synth pads and softly plucked notes based on a simple original pattern.
    Written from scratch using Python's standard library. Commercial use permitted.
    """
    sample_rate = 22050
    # This is an original soundscape, not a recording or cover.
    progression = [(220.0, 261.63, 329.63), (196.0, 246.94, 293.66),
                   (174.61, 220.0, 261.63), (196.0, 246.94, 329.63)]
    total = int(duration * sample_rate)
    with wave.open(str(destination), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        block = bytearray()
        for i in range(total):
            t = i / sample_rate
            step = min(3, int(t / max(0.1, duration / 4)))
            notes = progression[step]
            # Rounded, layered pad with slow vibrato and low amplitude.
            pad = sum(math.sin(2 * math.pi * n * t + 0.06 * math.sin(2 * math.pi * .21 * t))
                      for n in notes) / 3
            # Bell-like notes, short and restrained.
            pulse_pos = t % 1.5
            note = notes[int(t / 1.5) % 3] * 2
            pluck = (math.sin(2 * math.pi * note * t)
                     + .28 * math.sin(2 * math.pi * note * 2 * t)) * math.exp(-2.5 * pulse_pos)
            fade = min(1.0, t / 1.4, max(0.0, (duration - t) / 1.5))
            val = max(-1.0, min(1.0, (pad * .15 + pluck * .095) * fade))
            block += struct.pack("<h", int(val * 32767))
            if len(block) >= 65536:
                output.writeframesraw(block)
                block.clear()
        if block:
            output.writeframesraw(block)



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
    audio_file = output.parent / "ivory-original-ambient.wav"
    original_ambient_audio(audio_file, count * 3)
    args += ["-i", str(audio_file)]
    args += ["-filter_complex", ";".join(filters),
             "-map", "[out]", "-r", str(FPS), "-c:v", "libx264",
             "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p",
             "-movflags", "+faststart", "-map", f"{count}:a:0",
             "-c:a", "aac", "-b:a", "128k", "-shortest", str(output)]
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
            frame = await asyncio.to_thread(frame_image, data)
            frame.save(p, "JPEG", quality=88)
            files.append(p)
        return await asyncio.to_thread(encode_reel, files, root / "preview.mp4")
