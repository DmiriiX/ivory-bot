import sys
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instagram_story import story_image, story_triptych
from instagram_editorial import draw_frame
from instagram_reel import original_ambient_audio


class CreativeSafetyTests(unittest.TestCase):
    def test_branded_story_is_vertical_and_self_contained(self):
        src = BytesIO()
        Image.new("RGB", (600, 400), "#a29680").save(src, "JPEG")
        rendered = story_image(src.getvalue(), "Original Artwork", "Artist")
        image = Image.open(BytesIO(rendered))
        self.assertEqual(image.size, (1080, 1920))
        self.assertEqual(image.format, "JPEG")

    def test_triptych_has_three_unique_artwork_preserving_frames(self):
        source = BytesIO()
        Image.new("RGB", (740, 490), "#a29680").save(source, "JPEG")
        frames = story_triptych([source.getvalue(), source.getvalue()],
                               "Original Artwork", "Artist", "60 × 80 см")
        self.assertEqual(len(frames), 3)
        self.assertEqual(len(set(frames)), 3)
        for jpeg in frames:
            with Image.open(BytesIO(jpeg)) as img:
                self.assertEqual(img.size, (1080, 1920))
                self.assertEqual(img.format, "JPEG")

    def test_luxury_and_cinematic_reels_use_distinct_frames(self):
        art = Image.new("RGB", (580, 420), "#ab9582")
        f1 = draw_frame(4, [art, art], "Artwork", "Artist", "cinematic")
        f2 = draw_frame(4, [art, art], "Artwork", "Artist", "luxury")
        self.assertEqual(f1.size, (720, 1280))
        self.assertEqual(f2.size, (720, 1280))
        self.assertNotEqual(f1.tobytes(), f2.tobytes())

    def test_cinematic_and_luxury_music_are_not_identical(self):
        with tempfile.TemporaryDirectory() as folder:
            a = Path(folder)/"a.wav"
            b = Path(folder)/"b.wav"
            original_ambient_audio(a, 2.5, "cinematic")
            original_ambient_audio(b, 2.5, "luxury")
            self.assertNotEqual(a.read_bytes(), b.read_bytes())

    def test_original_ambient_soundtrack_contains_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "ambient.wav"
            original_ambient_audio(target, 3)
            with wave.open(str(target), "rb") as audio:
                self.assertEqual(audio.getnchannels(), 1)
                self.assertEqual(audio.getframerate(), 22050)
                self.assertGreater(audio.getnframes(), 60000)
                samples = audio.readframes(10000)
                self.assertNotEqual(set(samples), {0})


if __name__ == "__main__":
    unittest.main()
