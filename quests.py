"""
quests.py - Quest automation for RoX using OCR text detection.

Instead of image template matching, we READ the quest text directly from
the game window (e.g. "[Main] All Must be Found!") and click on it.
This means the bot works correctly regardless of:
  - Quest text changes as quests progress
  - Window position / resize
  - Minor UI updates from game patches

Detection priority:
  1. [Main] quest  - highest priority, click first
  2. [Tutorial] quest - click if no Main quest visible
"""

from __future__ import annotations

import time
from typing import Callable

from capture import capture_window
from ocr import read_window, find_text, find_all_text
from actions import click


# Text patterns that identify a clickable quest row.
# Order = priority (first match wins).
QUEST_PATTERNS = [
    r"\[Main\]",       # Main quest - highest priority
    r"\[Tutorial\]",   # Tutorial quest
    r"Distance to target",   # visible when quest is active
    r"Target location",      # visible when quest is active
]


def run_quest_cycle(status_cb: Callable[[str], None] = print) -> bool:
    """
    Capture the RoX window, read text via OCR, find a quest entry and click it.
    Returns True if a quest was clicked.
    """
    screenshot, bounds = capture_window()
    if screenshot is None or bounds is None:
        status_cb("Cannot capture RoX window")
        return False

    status_cb("Reading game window text...")
    regions = read_window(screenshot, min_conf=0.40)

    if not regions:
        status_cb("No text detected in window")
        return False

    # Try each pattern in priority order
    for pattern in QUEST_PATTERNS:
        region = find_text(regions, pattern, min_conf=0.40)
        if region:
            status_cb(
                f"Found quest text: \"{region.text}\"  "
                f"conf={region.conf:.0%}  clicking at ({region.cx}, {region.cy})"
            )
            click(region.cx, region.cy, bounds)
            time.sleep(0.3)
            return True

    # Log what WAS found so the user can tune patterns
    found_texts = [r.text for r in regions[:8]]
    status_cb(f"No quest text detected. Visible: {found_texts}")
    return False


def get_quest_info(status_cb: Callable[[str], None] = print) -> dict | None:
    """
    Return a dict with current quest details read from the screen, or None.
    Useful for the dashboard to show what quest is active.

    Returns: {
        'type':     'Main' | 'Tutorial' | 'Unknown',
        'title':    str,
        'objective': str,
        'distance': str | None,
    }
    """
    screenshot, bounds = capture_window()
    if screenshot is None:
        return None

    regions = read_window(screenshot, min_conf=0.35)

    quest_type = "Unknown"
    title = ""
    objective = ""
    distance = None

    main_r = find_text(regions, r"\[Main\]")
    tutorial_r = find_text(regions, r"\[Tutorial\]")
    dist_r = find_text(regions, r"Distance to target")
    loc_r = find_text(regions, r"Target location")

    if main_r:
        quest_type = "Main"
        title = main_r.text
    elif tutorial_r:
        quest_type = "Tutorial"
        title = tutorial_r.text

    if dist_r:
        distance = dist_r.text
    elif loc_r:
        distance = loc_r.text

    if not title:
        return None

    return {
        "type":      quest_type,
        "title":     title,
        "objective": objective,
        "distance":  distance,
    }
