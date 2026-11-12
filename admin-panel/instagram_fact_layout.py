"""Paginate complete bilingual fact copy for the two cards in each language."""
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import ImageFont

FONT_DIR = Path(__file__).with_name("fact_fonts")
BODY_FONT = "NotoSans-Regular.ttf"
BODY_WIDTH = 900
BODY_HEIGHT = 925
PARAGRAPH_GAP = 28
MAX_SLIDE_TEXT_LENGTH = 1000

_KEEP_WITH_NEXT = frozenset(("а", "в", "и", "к", "о", "с", "у", "на", "по", "из", "за", "со", "от", "не"))
_NATURAL_BREAK = re.compile(r"\n+|(?<=[.!?…])\s+")


@dataclass(frozen=True)
class FactTextPage:
    paragraphs: tuple[tuple[str, ...], ...]
    font_size: int
    footer: str = ""


@lru_cache(maxsize=64)
def fact_font(filename, size):
    return ImageFont.truetype(str(FONT_DIR / filename), size)


def line_height(size):
    return round(size * 1.19)


def _wrap(paragraph, face):
    groups = []
    pending = []
    for word in paragraph.split():
        if word == "-" and groups and not pending:
            groups[-1] += " -"
            continue
        pending.append(word)
        if word.lower() not in _KEEP_WITH_NEXT:
            groups.append(" ".join(pending))
            pending.clear()
    if pending:
        groups.append(" ".join(pending))

    rows = []
    row = groups[0]
    for group in groups[1:]:
        candidate = row + " " + group
        if face.getlength(candidate) <= BODY_WIDTH - 3:
            row = candidate
        else:
            rows.append(row)
            row = group
    return tuple([*rows, row])


def _layout(page, size):
    face = fact_font(BODY_FONT, size)
    paragraphs = tuple(_wrap(part, face) for part in page.split("\n\n") if part.strip())
    height = sum(len(lines) for lines in paragraphs) * line_height(size)
    height += PARAGRAPH_GAP * (len(paragraphs) - 1)
    if height > BODY_HEIGHT or any(face.getlength(line) > BODY_WIDTH - 3
                                   for paragraph in paragraphs for line in paragraph):
        return None
    return paragraphs


def fact_text_pages(value):
    """Keep all words in order, preferring a paragraph or sentence boundary."""
    value = value.strip()
    body, divider, tail = value.rpartition("\n\n")
    if not divider or not tail.split() or not all(word.startswith("#") for word in tail.split()):
        body, tail = value, ""
    elif fact_font(BODY_FONT, 24).getlength(tail) > BODY_WIDTH - 100:
        body, tail = value, ""

    body = body.strip()
    midpoint = len(body) / 2
    natural = sorted(_NATURAL_BREAK.finditer(body), key=lambda match: abs(match.start() - midpoint))
    word_breaks = sorted(re.finditer(r"\s+", body), key=lambda match: abs(match.start() - midpoint))
    splits = [(body[:match.start()].strip(), body[match.end():].strip())
              for match in (*natural, *word_breaks[:8]) if match.start() and match.end() < len(body)]
    if not splits:
        raise ValueError("Fact text needs a break between the two cards")

    for size in range(52, 45, -1):
        for first, second in splits:
            left, right = _layout(first, size), _layout(second, size)
            if left and right:
                return FactTextPage(left, size), FactTextPage(right, size, tail)
    raise ValueError("Fact text does not fit two readable cards")
