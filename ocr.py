"""
ocr.py — OCR text recognition using Apple Vision framework (macOS native).

Why Vision instead of EasyOCR
------------------------------
EasyOCR loads a full PyTorch neural network (~2 s startup, ~1 s/scan).
Apple Vision runs on the macOS Neural Engine — available on all Macs with
no extra packages (pyobjc is already a project dependency).

Benchmarks on M-series Mac:
  EasyOCR  : first scan ~2 s, subsequent ~1 s
  Vision   : first scan ~1 s (model load), subsequent ~190 ms  ← 5× faster

Accuracy improvements over EasyOCR for this game:
  - "Bernard's"  correctly read  (EasyOCR returned "Bernard'$")
  - All clear UI text at conf=100%
  - No false positives from styled / coloured font faces

Public API (unchanged — drop-in replacement)
---------------------------------------------
  read_window(image, min_conf)    → list[TextRegion]
  find_text(regions, pattern)     → TextRegion | None
  find_all_text(regions, pattern) → list[TextRegion]
  annotate_ocr(image, regions)    → PIL.Image
  TextRegion                      (dataclass, same fields)

Coordinate system
-----------------
Vision bounding boxes use normalised Core Graphics coords:
  origin = bottom-left, y increases upward, values 0.0–1.0
Converted to pixel coords with origin top-left (matching the rest of the
codebase):  px = x_norm * W,  py = (1 - y_norm - h_norm) * H
"""

from __future__ import annotations

import io
import re
import threading
from dataclasses import dataclass
from typing import Sequence

from PIL import Image

# ── Types ────────────────────────────────────────────────────────────────────

@dataclass
class TextRegion:
    text:  str      # recognised text string
    x:     int      # left edge  (window-relative, logical pixels, origin top-left)
    y:     int      # top edge
    w:     int      # width
    h:     int      # height
    conf:  float    # confidence 0.0–1.0

    @property
    def cx(self) -> int:
        return self.x + self.w // 2

    @property
    def cy(self) -> int:
        return self.y + self.h // 2

    def __repr__(self) -> str:
        return f'TextRegion({self.text!r} conf={self.conf:.0%} at ({self.cx},{self.cy}))'


# ── Lazy Vision imports ───────────────────────────────────────────────────────

_vision_ready = False
_vision_lock  = threading.Lock()
_Vision = _Cocoa = _Quartz = None


def _ensure_vision() -> None:
    global _vision_ready, _Vision, _Cocoa, _Quartz
    if _vision_ready:
        return
    with _vision_lock:
        if _vision_ready:
            return
        import Vision as V
        import Cocoa  as C
        import Quartz as Q
        _Vision, _Cocoa, _Quartz = V, C, Q
        _vision_ready = True


# ── Core scan ────────────────────────────────────────────────────────────────

def _run_vision(image: Image.Image) -> list[tuple[int, int, int, int, str, float]]:
    """
    Run VNRecognizeTextRequest on a PIL image.
    Returns list of (x, y, w, h, text, conf) in pixel coords, origin top-left.
    """
    _ensure_vision()
    W, H = image.width, image.height

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    ns_data = _Cocoa.NSData.dataWithBytes_length_(buf.getvalue(), len(buf.getvalue()))
    ci_image = _Quartz.CIImage.imageWithData_(ns_data)

    req = _Vision.VNRecognizeTextRequest.alloc().init()
    req.setRecognitionLevel_(_Vision.VNRequestTextRecognitionLevelAccurate)
    req.setUsesLanguageCorrection_(False)   # faster; game UI text needs no spell-check

    handler = _Vision.VNImageRequestHandler.alloc().initWithCIImage_options_(ci_image, {})
    ok, _ = handler.performRequests_error_([req], None)
    if not ok:
        return []

    out = []
    for obs in req.results() or []:
        candidates = obs.topCandidates_(1)
        if not candidates:
            continue
        best = candidates[0]
        text = best.string().strip()
        conf = float(best.confidence())
        bb   = obs.boundingBox()  # NSRect normalised, origin bottom-left

        # Normalised CG coords → pixel, flip Y
        px = int(bb.origin.x * W)
        py = int((1.0 - bb.origin.y - bb.size.height) * H)
        pw = int(bb.size.width  * W)
        ph = int(bb.size.height * H)
        out.append((px, py, pw, ph, text, conf))

    return out


# ── Public API ───────────────────────────────────────────────────────────────

def read_window(image: Image.Image, min_conf: float = 0.35) -> list[TextRegion]:
    """
    Scan a PIL image with Apple Vision and return all TextRegion objects.

    image    : logical-resolution PIL Image (from capture_window)
    min_conf : discard results below this confidence
    """
    regions: list[TextRegion] = []
    for (x, y, w, h, text, conf) in _run_vision(image):
        if conf < min_conf or not text:
            continue
        regions.append(TextRegion(text=text, x=x, y=y, w=w, h=h, conf=conf))
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
