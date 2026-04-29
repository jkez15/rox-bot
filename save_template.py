"""
save_template.py – Helper script to capture a screenshot of the current
RoX window and save it as a PNG. Use this to build your templates/ library.

Usage:
    source venv/bin/activate
    python save_template.py            # saves timestamped full-window screenshot
    python save_template.py my_button  # saves as templates/my_button.png
"""

import sys
import time
from pathlib import Path
from datetime import datetime

from capture import capture_window

Path("templates").mkdir(exist_ok=True)

print("Capturing RoX window in 2 seconds... (switch to RoX now!)")
time.sleep(2)

img, bounds = capture_window()
if img is None:
    print("❌  Could not capture window. Is RoX open and visible?")
    sys.exit(1)

if len(sys.argv) > 1:
    name = sys.argv[1]
    out = f"templates/{name}.png" if not name.endswith(".png") else f"templates/{name}"
else:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = f"templates/screenshot_{ts}.png"

img.save(out)
print(f"✅  Saved → {out}  ({img.width}×{img.height} px)")
print(f"   Window bounds: x={bounds['X']} y={bounds['Y']} w={bounds['Width']} h={bounds['Height']}")
