"""
ocr.py - OCR text recognition for the RoX game window.

Uses EasyOCR to read text directly from the captured window image.
This is more robust than template matching — it detects quest text like
"[Main]", "[Tutorial]", "Distance to target:" regardless of font size,
colour shifts, or UI position changes after game updates.

The OCR reader is a singleton (loaded once, reused every cycle) because
loading the neural network model takes ~2 seconds.
"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from typing import Sequence

import numpy as np
from PIL import Image

# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class TextRegion:
    text:  str          # recognised text string
    x:     int          # left edge (window-relative logical pixels)
    y:     int          # top edge
    w:     int          # width
    h:     int          # height
    conf:  float        # confidence 0.0–1.0

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    def __repr__(self) -> str:
        return f'TextRegion({self.text!r} conf={self.conf:.0%} at ({self.cx},{self.cy}))'


# ── Singleton OCR reader ─────────────────────────────────────────────────────

_reader = None
_reader_lock = threading.Lock()


def _get_reader():
    global _reader
    if _reader is None:
        with _reader_lock:
            if _reader is None:
                import easyocr
                print("[OCR] Loading EasyOCR model (first run only)…")
                _reader = easyocr.Reader(["en"], verbose=False)
                print("[OCR] Model ready.")
    return _reader


# ── Public API ───────────────────────────────────────────────────────────────

def read_window(image: Image.Image, min_conf: float = 0.35) -> list[TextRegion]:
    """
    Run OCR on a PIL image and return all detected TextRegion objects.

    image     : logical-resolution PIL Image (from capture_window)
    min_conf  : discard results below this confidence
    """
    reader = _get_reader()
    arr = np.array(image)
    raw = reader.readtext(arr, detail=1)

    regions: list[TextRegion] = []
    for bbox, text, conf in raw:
        if conf < min_conf:
            continue
        x = int(min(p[0] for p in bbox))
        y = int(min(p[1] for p in bbox))
        w = int(max(p[0] for p in bbox)) - x
        h = int(max(p[1] for p in bbox)) - y
        regions.append(TextRegion(text=text.strip(), x=x, y=y, w=w, h=h, conf=conf))

    return regions


def find_text(
    regions: list[TextRegion],
    pattern: str,
    min_conf: float = 0.40,
    flags: int = re.IGNORECASE,
) -> TextRegion | None:
    """
    Return the first TextRegion whose text matches `pattern` (regex).
    Sorted by confidence descending.
    """
    compiled = re.compile(pattern, flags)
    matches = [r for r in regions if compiled.search(r.text) and r.conf >= min_conf]
    return max(matches, key=lambda r: r.conf) if matches else None


def find_all_text(
    regions: list[TextRegion],
    pattern: str,
    min_conf: float = 0.40,
    flags: int = re.IGNORECASE,
) -> list[TextRegion]:
    """Return ALL TextRegions matching `pattern`, sorted top-to-bottom."""
    compiled = re.compile(pattern, flags)
    matches = [r for r in regions if compiled.search(r.text) and r.conf >= min_conf]
    return sorted(matches, key=lambda r: r.y)


def annotate_ocr(
    image: Image.Image,
    regions: list[TextRegion],
    highlights: Sequence[TextRegion] = (),
) -> Image.Image:
    """
    Draw all OCR bounding boxes on a copy of the image.
    `highlights` are drawn in a different colour (used for click targets).
    """
    from PIL import ImageDraw
    img = image.copy()
    draw = ImageDraw.Draw(img)

    highlight_set = set(id(r) for r in highlights)
    for r in regions:
        colour = "cyan" if id(r) in highlight_set else (255, 255, 100, 180)
        draw.rectangle([r.x, r.y, r.x + r.w, r.y + r.h], outline=colour, width=2)
        draw.text((r.x, r.y - 12), f"{r.conf:.0%} {r.text[:30]}", fill=colour)

    for r in highlights:
        # Draw a crosshair on the click centre
        cx, cy = r.cx, r.cy
        draw.ellipse([cx - 14, cy - 14, cx + 14, cy + 14], outline="red", width=3)
        draw.line([cx - 20, cy, cx + 20, cy], fill="red", width=2)
        draw.line([cx, cy - 20, cx, cy + 20], fill="red", width=2)

    return img
