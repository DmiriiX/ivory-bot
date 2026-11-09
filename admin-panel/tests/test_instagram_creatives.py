import sys
import tempfile
import unittest
import wave
from io import BytesIO
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from instagram_story import story_image
from instagram_reel import original_ambient_audio


class CreativeSafetyTests(unittest.TestCase):
    def test_branded_story_is_vertical_and_self_contained(self):
        src = BytesIO()
        Image.new("RGB", (600, 400), "#a29680").save(src, "JPEG")
        rendered = story_image(src.getvalue(), "Original Artwork", "Artist")
        image = Image.open(BytesIO(rendered))
        self.assertEqual(image.size, (1080, 1920))
        self.assertEqual(image.format, "JPEG")

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
