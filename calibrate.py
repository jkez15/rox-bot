"""
calibrate.py - Visual calibration and self-test tool for the RoX bot.

Run this BEFORE running main.py whenever:
  - The game updates its UI
  - A template is not matching correctly
  - You add a new automation feature

What it does:
  1. Captures the current RoX window
  2. Runs all registered template matches
  3. Draws annotated circles on the screenshot showing EXACTLY what would be clicked
  4. Prints a pass/fail report for every template
  5. Saves debug_calibration.png so you can visually verify each target

Usage:
    source .venv/bin/activate
    python calibrate.py
"""

from __future__ import annotations

import os
import sys
from datetime import datetime

from PIL import ImageDraw

# ── OCR text targets ─────────────────────────────────────────────────────────
# Each entry is a regex pattern the OCR must find in the game window.
# Add new entries here when you add new automation features.

OCR_TARGETS = [
    {
        "name":     "Main Quest marker",
        "pattern":  r"\[Main\]",
        "required": False,
        "colour":   "lime",
    },
    {
        "name":     "Tutorial Quest marker",
        "pattern":  r"\[Tutorial\]",
        "required": False,
        "colour":   "cyan",
    },
    {
        "name":     "Any quest visible (Main OR Tutorial)",
        "pattern":  r"\[Main\]|\[Tutorial\]",
        "required": True,
        "colour":   "lime",
    },
    {
        "name":     "Distance / target indicator",
        "pattern":  r"Distance to target|Target location",
        "required": False,
        "colour":   "yellow",
    },
    # ── Add new OCR targets below as you build new automation ────────────────
    # {
    #     "name":     "HP bar label",
    #     "pattern":  r"\d+/\d+",
    #     "required": False,
    #     "colour":   "orange",
    # },
]


# ── Helpers ──────────────────────────────────────────────────────────────────

def draw_target(draw: ImageDraw.ImageDraw, cx: int, cy: int,
                label: str, colour: str, conf: float) -> None:
    r = 18
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=colour, width=3)
    draw.line([cx - r - 10, cy, cx + r + 10, cy], fill=colour, width=2)
    draw.line([cx, cy - r - 10, cx, cy + r + 10], fill=colour, width=2)
    draw.rectangle([cx + r + 4, cy - 14, cx + r + 4 + len(label) * 7 + 60, cy + 14],
                   fill=(0, 0, 0, 180))
    draw.text((cx + r + 8, cy - 11), f"{label}  {conf:.0%}", fill=colour)


# ── Main ─────────────────────────────────────────────────────────────────────

def run_calibration() -> bool:
    """
    Returns True if all required OCR targets were found, False otherwise.
    """
    print("\n" + "=" * 62)
    print("  RoX Bot — OCR Calibration & Self-Test")
    print("=" * 62)

    # 1. Capture the window (works even if RoX is behind other apps)
    print("\n[1/3] Capturing RoX window (background capture)…")
    try:
        from capture import capture_window
        screenshot, bounds = capture_window()
    except Exception as e:
        print(f"  ✗  Capture failed: {e}")
        return False

    if screenshot is None:
        print("  ✗  Could not capture window — is RoX running?")
        return False

    print(f"  ✓  Captured {screenshot.width}×{screenshot.height}px  "
          f"window at screen ({bounds['X']:.0f}, {bounds['Y']:.0f})")

    # 2. Run OCR
    print("\n[2/3] Running OCR text recognition…\n")
    from ocr import read_window, find_text, annotate_ocr

    regions = read_window(screenshot, min_conf=0.35)
    print(f"  ✓  OCR found {len(regions)} text regions")
    print()

    all_passed = True
    hit_regions = []
    results = []

    for target in OCR_TARGETS:
        region = find_text(regions, target["pattern"], min_conf=0.35)
        status = "PASS" if region else "FAIL"
        required = target["required"]
        if status != "PASS" and required:
            all_passed = False

        results.append((target, region, status))
        icon = "✓" if status == "PASS" else "✗"
        tag  = "[REQUIRED]" if required else "[optional]"
        pos  = f"at ({region.cx},{region.cy}) conf={region.conf:.0%}" if region else "not found"
        print(f"  {icon}  {tag}  {target['name']}")
        print(f"       pattern: {target['pattern']}  →  {pos}")
        if region:
            hit_regions.append(region)

    # 3. Save annotated image
    print("\n[3/3] Saving annotated calibration image…")
    annotated = annotate_ocr(screenshot, regions, highlights=hit_regions)

    # Add timestamp banner
    banner_draw = ImageDraw.Draw(annotated)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    banner_text = f"RoX Bot OCR Calibration  |  {ts}  |  Window {screenshot.width}x{screenshot.height}"
    banner_draw.rectangle([0, 0, annotated.width, 24], fill=(20, 20, 40))
    banner_draw.text((8, 4), banner_text, fill=(200, 200, 200))

    out_path = "debug_calibration.png"
    annotated.save(out_path)
    print(f"  ✓  Saved {out_path}")

    import subprocess
    subprocess.run(["open", out_path])

    # 4. Summary
    print("\n" + "─" * 62)
    if all_passed:
        print("  ✅  All required text patterns found — bot is ready.")
        print("      Run: python main.py")
    else:
        failed = [r[0]["name"] for r in results if r[2] != "PASS" and r[0]["required"]]
        print("  ❌  Required text patterns NOT found:")
        for name in failed:
            print(f"       • {name}")
        print()
        print("  This means the quest panel is not currently visible in RoX,")
        print("  or the game UI has changed. Open the quest panel and re-run.")
    print("─" * 62 + "\n")
    return all_passed


if __name__ == "__main__":
    ok = run_calibration()
    sys.exit(0 if ok else 1)
