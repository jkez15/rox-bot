"""
quests.py – Quest automation for RöX using OCR text detection.

Quest cycle (three-step state machine per scan)
------------------------------------------------
  Step 0 — DIALOG ADVANCEMENT (highest priority)
    If an NPC conversation dialog is open (detected by dialogue button labels
    like 'Inquire', 'Next', 'Continue', or NPC speech text at the bottom of
    the screen), click the appropriate button to advance or close the dialog.

  Step 1 — INTERACTION CHECK
    If 'Examine' or 'Inspect' button is visible, click the icon button
    above it (yellow magnifying-glass).  This opens the NPC dialog.

  Step 2 — QUEST NAVIGATION (only if no dialog or interaction button found)
    Find the highest-priority quest row: [Main] > [Tutorial].
    Click it ONCE so the game sets it as the active navigation target.

Quest priority (strictly enforced):
  1. [Main]     — always preferred
  2. [Tutorial] — used only when no Main quest is visible
"""

from __future__ import annotations

import re
import time
from typing import Callable

from capture import capture_window
from ocr import read_window, find_text
from actions import click


# ── Config ───────────────────────────────────────────────────────────────────

# Quest types in strict priority order — first match wins.
QUEST_PRIORITY: list[tuple[str, str]] = [
    (r"\[Main\]",     "Main"),
    (r"\[Tutorial\]", "Tutorial"),
]

# Button labels that open NPC interaction (Examine screen).
INTERACTION_PATTERNS = [
    r"\bExamine\b",
    r"\bInspect\b",
    r"\bTalk\b",
]

# Skip button pattern — first preference when dialog is open.
SKIP_PATTERN = r"\bSkip\b"

# Choice / advance buttons on the RIGHT side of the screen (cx > DIALOG_CHOICE_X_MIN).
# These appear when the dialog offers selectable options with no Skip available.
DIALOG_CHOICE_PATTERNS = [
    r"Inquir",      # 'Inquire' — closes/completes quest conversation
    r"\bNext\b",    # advance dialogue line
    r"Continu",     # 'Continue'
    r"\bClose\b",   # dismiss after quest update
    r"\bOk\b",
    r"\bYes\b",
    r"\bAgree\b",
]

# Right-side choices have cx above this threshold (right portion of screen).
DIALOG_CHOICE_X_MIN = 650   # logical pixels

# NPC dialog is considered open when speech text appears near the bottom.
DIALOG_TEXT_Y_MIN = 600   # logical pixels

# Centre of the game world — used as spam-click fallback to advance dialog.
# Approximately mid-screen excluding the UI panels.
DIALOG_SPAM_X = 525   # logical pixels (centre x)
DIALOG_SPAM_Y = 420   # logical pixels (centre y)

# cx threshold: anything left of this is inside the quest-panel sidebar.
QUEST_PANEL_X_MAX = 260   # logical pixels

# Confidence floors
MIN_CONF_QUEST  = 0.40
MIN_CONF_BUTTON = 0.30   # lower — button labels are short and may be styled
MIN_CONF_DIALOG = 0.25   # very low — dialog buttons are styled/coloured


# ── Helpers ──────────────────────────────────────────────────────────────────

def _extract_target(text: str) -> str | None:
    """Parse 'Target location: Prontera South Gate' → 'Prontera South Gate'."""
    m = re.search(r"Target location\s*:\s*(.+)", text, re.IGNORECASE)
    return m.group(1).strip() if m else None


def _find_dialog_button(regions, bounds_w: int = 1051):
    """
    Determine what to do when an NPC dialog is open.

    Returns (cx, cy, label, action) where action is one of:
      'skip'   — Skip button found → click it
      'choice' — selectable option on right side → click first found
      'spam'   — no specific button; caller should spam-click centre
    Returns None if no dialog appears to be open.

    Dialog is detected when NPC speech text appears near the bottom of
    the screen (cy > DIALOG_TEXT_Y_MIN).
    """
    has_speech = any(
        r.cy > DIALOG_TEXT_Y_MIN and r.cx > QUEST_PANEL_X_MAX
        for r in regions
        if r.conf >= MIN_CONF_DIALOG
    )
    if not has_speech:
        return None

    # 1. Skip — highest preference, always click it if present
    skip_r = find_text(regions, SKIP_PATTERN, min_conf=MIN_CONF_DIALOG)
    if skip_r and skip_r.cx > QUEST_PANEL_X_MAX:
        return skip_r.cx, skip_r.cy, skip_r.text, "skip"

    # 2. Right-side choice buttons
    for pattern in DIALOG_CHOICE_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_DIALOG)
        if r and r.cx > DIALOG_CHOICE_X_MIN:
            return r.cx, r.cy, r.text, "choice"

    # 3. Fallback — spam-click centre of game world to advance
    return DIALOG_SPAM_X, DIALOG_SPAM_Y, "screen", "spam"


# How many pixels above the "Examine" / "Inspect" text the icon button sits.
# Measured: Examine @ (713,279), yellow icon centroid @ (705,252) → 27px up.
INTERACTION_BUTTON_OFFSET_Y = -27


def _find_interaction_button(regions, screenshot=None):
    """
    Return (cx, cy, label) of the interaction button, or None.

    OCR finds the 'Examine' / 'Inspect' text label, then we shift up by
    INTERACTION_BUTTON_OFFSET_Y pixels to land on the icon button above it.
    """
    for pattern in INTERACTION_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_BUTTON)
        if r and r.cx > QUEST_PANEL_X_MAX:
            cx = r.cx
            cy = r.cy + INTERACTION_BUTTON_OFFSET_Y
            return cx, cy, r.text
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def do_quest_scan(
    status_cb: Callable[[str], None] = print,
) -> tuple[dict | None, bool]:
    """
    Single OCR pass: capture → read text → act.

    Returns
    -------
    quest_info : dict | None
        Keys: type, title, distance, target  (for the dashboard)
    clicked : bool
        True if any click was sent this cycle.
    """
    screenshot, bounds = capture_window()
    if screenshot is None or bounds is None:
        status_cb("⚠  Cannot capture RöX window")
        return None, False

    status_cb("🔍 Scanning screen…")
    regions = read_window(screenshot, min_conf=min(MIN_CONF_QUEST, MIN_CONF_BUTTON))

    if not regions:
        status_cb("No text detected in window")
        return None, False

    # ── Step 0: Dialog advancement (highest priority) ─────────────────────
    dlg = _find_dialog_button(regions)
    if dlg:
        dx, dy, dlabel, action = dlg
        if action == "skip":
            status_cb(f"💬 Dialog — clicking Skip at ({dx}, {dy})")
        elif action == "choice":
            status_cb(f"💬 Dialog choice — clicking \"{dlabel}\" at ({dx}, {dy})")
        else:
            status_cb(f"💬 Dialog — no button found, clicking centre ({dx}, {dy})")
        click(dx, dy, bounds)
        time.sleep(0.5)
        quest_info = _build_quest_info(regions)
        return quest_info, True

    # ── Step 1: Interaction button check ────────────────────────────────────
    btn = _find_interaction_button(regions, screenshot)
    if btn:
        bx, by, blabel = btn
        status_cb(
            f"🖱  Found \"{blabel}\" at ({bx}, {by}) — clicking to complete interaction"
        )
        click(bx, by, bounds)
        time.sleep(0.4)
        quest_info = _build_quest_info(regions)
        return quest_info, True

    # ── Step 2: Quest row navigation ─────────────────────────────────────────
    active_region = None
    quest_type    = None

    for pattern, qtype in QUEST_PRIORITY:
        r = find_text(regions, pattern, min_conf=MIN_CONF_QUEST)
        if r:
            active_region = r
            quest_type    = qtype
            status_cb(f"🎯 Active quest ({qtype}): \"{r.text}\"  conf={r.conf:.0%}")
            break   # strict priority — stop at first match

    quest_info = _build_quest_info(regions, active_region, quest_type)

    if active_region:
        status_cb(
            f"👆 Clicking quest row \"{active_region.text}\" "
            f"at ({active_region.cx}, {active_region.cy}) to set navigation target"
        )
        click(active_region.cx, active_region.cy, bounds)
        time.sleep(0.3)
        return quest_info, True

    # Nothing found
    visible = [r.text for r in regions[:8]]
    status_cb(f"No quest or button found. Visible text: {visible}")
    return quest_info, False


# ── Internal helpers ──────────────────────────────────────────────────────────

def _build_quest_info(
    regions,
    active_region=None,
    quest_type: str | None = None,
) -> dict | None:
    """Build the quest info dict shown in the dashboard."""
    dist_r   = find_text(regions, r"Distance to target", min_conf=0.35)
    target_r = find_text(regions, r"Target location",    min_conf=0.35)

    target_name: str | None = None
    if target_r:
        target_name = _extract_target(target_r.text)

    # If no explicit active region, try to find any quest passively
    if active_region is None:
        for pattern, qtype in QUEST_PRIORITY:
            r = find_text(regions, pattern, min_conf=0.30)
            if r:
                active_region = r
                quest_type    = qtype
                break

    if active_region is None:
        return None

    return {
        "type":     quest_type,
        "title":    active_region.text,
        "distance": dist_r.text if dist_r else None,
        "target":   target_name,
    }
