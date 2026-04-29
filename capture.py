"""
capture.py – Captures the RöX window without needing it in the foreground.

Uses macOS `screencapture -l <windowID>` which reads the window composited
buffer directly — works even when RöX is behind other apps.
Returns a logical-resolution PIL Image (1× not 2×) and the window bounds dict.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import unicodedata

import numpy as np
from PIL import Image
import Quartz.CoreGraphics as CG

from config import APP_WINDOW_NAME

_APP_NAME_NFC = unicodedata.normalize("NFC", APP_WINDOW_NAME).lower()


def get_rox_window() -> tuple[int, dict] | tuple[None, None]:
    """
    Find the CGWindowID and bounds dict of the RöX window.
    Returns (window_id, bounds) or (None, None) if not found.
    bounds = {'X': float, 'Y': float, 'Width': float, 'Height': float}
    """
    windows = CG.CGWindowListCopyWindowInfo(
        CG.kCGWindowListOptionOnScreenOnly | CG.kCGWindowListExcludeDesktopElements,
        CG.kCGNullWindowID,
    )
    for w in windows:
        owner = w.get("kCGWindowOwnerName", "")
        owner_nfc = unicodedata.normalize("NFC", owner).lower()
        if _APP_NAME_NFC in owner_nfc:
            bounds = w.get("kCGWindowBounds")
            win_id = w.get("kCGWindowNumber")
            if bounds and win_id:
                return win_id, dict(bounds)
    return None, None


def capture_window() -> tuple[Image.Image, dict] | tuple[None, None]:
    """
    Capture the RöX window and return (PIL Image at logical resolution, bounds dict).

    Uses `screencapture -l <windowID>` which captures the window's own framebuffer
    directly — works even when the window is occluded by other apps (e.g. VS Code).

    The returned image is resized to logical pixel dimensions (bounds Width × Height)
    so template/OCR coordinates map 1:1 to click() window-relative coordinates.
    """
    win_id, bounds = get_rox_window()
    if win_id is None:
        return None, None

    tmp_path = f"/tmp/rox_capture_{os.getpid()}.png"
    try:
        result = subprocess.run(
            ["screencapture", "-l", str(win_id), "-x", "-o", tmp_path],
            capture_output=True,
            timeout=5,
        )
        if result.returncode != 0 or not os.path.exists(tmp_path):
            return None, None

        img = Image.open(tmp_path).convert("RGB")

        # Resize from Retina (2×) down to logical size so coords are 1:1 with clicks
        logical_w = int(bounds["Width"])
        logical_h = int(bounds["Height"])
        if img.width != logical_w or img.height != logical_h:
            img = img.resize((logical_w, logical_h), Image.LANCZOS)

        return img, bounds

    finally:
        try:
            os.remove(tmp_path)
        except FileNotFoundError:
            pass
