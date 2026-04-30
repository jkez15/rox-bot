"""
save_template.py – Capture the RöX window and save it to templates/<name>.png.

Usage
-----
    python save_template.py examine_icon
    python save_template.py my_button_name

Then open the saved file in Preview (Tools → Rectangular Selection) and crop
tightly around just the element you want to use as a template.  Save in-place.

After cropping, register it in calibrate.py and use it in quests.py:
    match = find_template(screenshot, "examine_icon.png", threshold=0.75)
"""

from __future__ import annotations

import sys
import os
from datetime import datetime

from capture import capture_window
from config import TEMPLATES_DIR


def save_template(name: str) -> None:
    if not name.endswith(".png"):
        name += ".png"

    screenshot, bounds = capture_window()
    if screenshot is None:
        print("❌  Could not capture RöX window. Is the game running?")
        sys.exit(1)

    os.makedirs(TEMPLATES_DIR, exist_ok=True)
    out_path = os.path.join(TEMPLATES_DIR, name)
    screenshot.save(out_path)

    w, h = screenshot.size
    print(f"✅  Saved {w}×{h} screenshot → {out_path}")
    print("   Open it in Preview, crop tightly around the element, then save.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        name = f"screenshot_{ts}"
        print(f"No name given — saving as {name}.png")
    else:
        name = sys.argv[1]

    save_template(name)
