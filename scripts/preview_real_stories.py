"""Produce a no-posting IVORY-ART Story demo from real gallery JPEGs.

Usage: python scripts/preview_real_stories.py
Only reads committed photographs; does not call Instagram or Buffer.
"""
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"admin-panel"))
from instagram_story import story_triptych

ID="07cf3fcfca91eb5d4197b40f"
photo_paths=[
    ROOT/"instagram-media"/"prepared"/f"{ID}-1.jpg",
    ROOT/"instagram-media"/"prepared"/f"{ID}-2.jpg",
]
if __name__=="__main__":
    for file in photo_paths:
        if not file.is_file():
            raise SystemExit("Original catalogue photograph missing: "+str(file))
    slides=story_triptych(
        [p.read_bytes() for p in photo_paths],
        title="Кафе в Венеции",
        artist="Владимир Кожевников",
        dimensions="110 × 90 см",
    )
    output=ROOT/"instagram-media"/"demo"
    output.mkdir(parents=True,exist_ok=True)
    for i,data in enumerate(slides,1):
        path=output/f"venice-real-story-{i}.jpg"
        path.write_bytes(data)
        print("Preview only:",path.relative_to(ROOT),len(data),"bytes")
