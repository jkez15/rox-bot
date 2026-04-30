"""
quests.py – Quest automation for RöX using OCR text detection.

Quest cycle (priority-ordered state machine per scan)
-----------------------------------------------------
  Step 0 — PATHFINDING IDLE (highest priority)
    If 'Pathfinding' text is on screen, the character is auto-walking.
    Do NOTHING — no clicks at all — until it disappears.

  Step 1 — DIALOG ADVANCEMENT
    If an NPC conversation dialog is open (detected by dialogue button labels
    like 'Inquire', 'Next', 'Continue', or NPC speech text at the bottom of
    the screen), click the appropriate button to advance or close the dialog.

  Step 2 — INTERACTION CHECK
    If 'Examine' or 'Inspect' button is visible, click the icon button
    above it (yellow magnifying-glass).  This opens the NPC dialog.

  Step 3 — SMART ACTION BUTTONS
    Scan for ANY interactive button in the game-world area (right side of
    screen, outside the quest panel).  This catches quest-specific actions
    like 'Photograph', 'Collect', 'Use', 'Activate', 'Open', etc. without
    needing hardcoded support for every quest type.

  Step 4 — QUEST NAVIGATION (lowest priority)
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
from ocr import read_window, find_text, find_all_text
from actions import click


# ── Config ───────────────────────────────────────────────────────────────────

# ── Pathfinding detection ────────────────────────────────────────────────────
# When this text is visible the character is auto-walking to a destination.
# The bot must NOT click anything while pathfinding is active.
PATHFINDING_PATTERN = r"Pathfinding|Path\s*finding|Auto.?walk"
MIN_CONF_PATHFINDING = 0.30

# Quest types in strict priority order — first match wins.
# Only [Main] quests are pursued; all other quest types are ignored.
QUEST_PRIORITY: list[tuple[str, str]] = [
    (r"\[Main\]", "Main"),
]

# Button labels that open NPC interaction (Examine screen).
INTERACTION_PATTERNS = [
    r"\bExamine\b",
    r"\bInspect\b",
    r"\bTalk\b",
]

# ── Smart action-button patterns ─────────────────────────────────────────────
# Broad set of interactive button labels that quests might show in the game
# world area.  Adding a pattern here is all that's needed to handle a new
# quest action — no other code changes required.
#
# These are checked OUTSIDE the quest panel (cx > QUEST_PANEL_X_MAX) and
# ABOVE the dialog zone (cy < DIALOG_TEXT_Y_MIN) so they don't collide with
# dialog buttons or quest-row text.
ACTION_BUTTON_PATTERNS: list[str] = [
    # Show / present item quests  ← e.g. "Show the boy Veronica's Photograph"
    r"\bShow\b",
    r"\bPresent\b",
    r"\bDisplay\b",
    # Photography / camera quests
    r"\bPhotograph\b",
    r"\bPhoto\b",
    r"\bCapture\b",
    r"\bSnapshot\b",
    r"\bCamera\b",
    r"\bShoot\b",
    # Collection / gathering
    r"\bCollect\b",
    r"\bGather\b",
    r"\bPick\s*up\b",
    r"\bLoot\b",
    r"\bHarvest\b",
    # Interaction / activation
    r"\bActivate\b",
    r"\bUse\b",
    r"\bOpen\b",
    r"\bInteract\b",
    r"\bTouch\b",
    r"\bPress\b",
    r"\bPush\b",
    r"\bPull\b",
    r"\bPlace\b",
    r"\bDrop\b",
    r"\bInvestigate\b",
    r"\bInspect\b",
    r"\bCheck\b",
    # Combat / dungeon
    r"\bAttack\b",
    r"\bFight\b",
    r"\bEnter\b",
    r"\bChallenge\b",
    r"\bBegin\b",
    # Delivery / quest hand-in
    r"\bDeliver\b",
    r"\bGive\b",
    r"\bHand\s*over\b",
    r"\bSubmit\b",
    r"\bTurn\s*in\b",
    r"\bReport\b",
    # Miscellaneous quest actions
    r"\bRepair\b",
    r"\bCraft\b",
    r"\bBuild\b",
    r"\bSummon\b",
    r"\bPlay\b",
    r"\bRead\b",
    r"\bSearch\b",
    r"\bDig\b",
    r"\bFish\b",
    r"\bCook\b",
    r"\bBrew\b",
    r"\bAccept\b",
    r"\bConfirm\b",
    r"\bComplete\b",
    r"\bClaim\b",
    r"\bReceive\b",
    r"\bExchange\b",
    r"\bTrade\b",
    r"\bBuy\b",
    r"\bSell\b",
]

MIN_CONF_ACTION = 0.30   # action buttons may be styled / small

# Action buttons must be in this screen zone (game world, not quest panel,
# not dialog area).
ACTION_BUTTON_X_MIN = 260   # right of quest panel
ACTION_BUTTON_Y_MAX = 600   # above dialog zone

# Skip button pattern — first preference when dialog is open.
SKIP_PATTERN = r"\bSkip\b"

# Choice / advance buttons on the RIGHT side of the screen (cx > DIALOG_CHOICE_X_MIN).
# These appear when the dialog offers selectable options with no Skip available.
DIALOG_CHOICE_PATTERNS = [
    r"Inquir",          # 'Inquire' — closes/completes quest conversation
    r"\bNext\b",        # advance dialogue line
    r"Continu",         # 'Continue'
    r"\bClose\b",       # dismiss after quest update
    r"\bOk\b",
    r"\bOK\b",
    r"\bYes\b",
    r"\bAgree\b",
    r"Got\s*it",        # 'Got it' confirmation
    r"Understood",      # acknowledgement
    r"I\s*see",         # 'I see'
    r"\bConfirm\b",
    r"\bDone\b",
    r"\bFinish\b",
    r"\bLeave\b",       # leave dialog
    r"\bBye\b",
    r"\bThanks\b",
]

# Right-side choices: any button right of screen centre counts.
# Was 650 — lowered to 400 so buttons slightly right of centre are not missed.
DIALOG_CHOICE_X_MIN = 400   # logical pixels

# Dialog choice buttons can only appear in the MIDDLE portion of the screen.
# The top ~300px is occupied by permanent HUD elements (Leave dungeon, Backpack,
# minimap, HP/SP bars) that must NEVER be clicked as dialog choices.
DIALOG_CHOICE_Y_MIN = 300   # logical pixels — ignore anything above this

# NPC dialog is considered open when speech text appears near the bottom.
# Y range is bounded to exclude world chat (y > DIALOG_TEXT_Y_MAX).
DIALOG_TEXT_Y_MIN = 620   # logical pixels — above world chat
DIALOG_TEXT_Y_MAX = 760   # logical pixels — below this is world chat / UI bar

# NPC name patterns — a dialog is only treated as open if an NPC name label
# is detected in the speech zone.  This prevents world-chat text from
# falsely triggering dialog handling.
NPC_NAME_PATTERNS = [
    r"\bBoy\b",
    r"\bGirl\b",
    r"\bGuard\b",
    r"\bMerchant\b",
    r"\bVendor\b",
    r"\bKnight\b",
    r"\bSoldier\b",
    r"\bWizard\b",
    r"\bPriest\b",
    r"\bHunter\b",
    r"\bNPC\b",
]
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
    Determine what to do when an NPC conversation dialog is open.

    A dialog is active ONLY when at least one explicit dialog button
    (Skip, Inquire, Next, etc.) is found outside the sidebar.
    This avoids world-chat text at the bottom falsely triggering dialog mode.

    Returns (cx, cy, label, action) or None.
    """
    # Require an explicit button — don't rely on speech text presence alone.
    # 1. Skip — highest preference
    skip_r = find_text(regions, SKIP_PATTERN, min_conf=MIN_CONF_DIALOG)
    if skip_r and skip_r.cx > QUEST_PANEL_X_MAX:
        return skip_r.cx, skip_r.cy, skip_r.text, "skip"

    # 2. Right-side choice buttons (cx > DIALOG_CHOICE_X_MIN, y > DIALOG_CHOICE_Y_MIN)
    for pattern in DIALOG_CHOICE_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_DIALOG)
        if r and r.cx > DIALOG_CHOICE_X_MIN and r.cy > DIALOG_CHOICE_Y_MIN:
            return r.cx, r.cy, r.text, "choice"

    # 3. Spam-click fallback — only when actual NPC speech is present.
    # Require multi-word text in the speech zone that doesn't look like
    # any chat or system message.
    # Exclusion rules:
    #   - conf < 0.70 (chat OCR is often lower-quality)
    #   - contains "Lv." → party/recruit chat
    #   - contains "Recruit" → recruitment message
    #   - contains "World" → world channel label
    #   - matches r'^\S+:' → "PlayerName: message" chat format
    #   - contains "Tower", "Dungeon", "FRESH", "JOIN" → typical MMO announcements
    CHAT_EXCLUSION = re.compile(
        r'^\S+:'           # Username: message (party/world/team chat)
        r'|\bLv\.'         # level number → recruit / party member text
        r'|\bRecruit\b'
        r'|\bWorld\b'
        r'|Endless\s+Tower'
        r'|\bFRESH\b'
        r'|\bJOIN\b'
        r'|\bDungeon\b',
        re.IGNORECASE,
    )
    speech_region = None
    for r in regions:
        if (
            DIALOG_TEXT_Y_MIN < r.cy < DIALOG_TEXT_Y_MAX
            and r.conf >= 0.70              # raised from 0.60 — chat OCR tends to be lower
            and len(r.text.split()) >= 4    # real NPC speech is a sentence
            and not CHAT_EXCLUSION.search(r.text)
        ):
            speech_region = r
            break
    if speech_region:
        # Click the detected speech text position (dialogue box area)
        return speech_region.cx, speech_region.cy, speech_region.text[:40], "spam"

    return None


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


def _is_pathfinding(regions) -> bool:
    """Return True if 'Pathfinding' (or similar) text is visible on screen."""
    r = find_text(regions, PATHFINDING_PATTERN, min_conf=MIN_CONF_PATHFINDING)
    return r is not None


def _find_action_button(regions):
    """
    Scan for any interactive action button in the game-world area.

    Returns (cx, cy, label) of the first matching button, or None.
    Buttons must be in the game-world zone (right of quest panel, above
    dialog area) to avoid false positives from quest text or dialog choices.
    """
    for pattern in ACTION_BUTTON_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_ACTION)
        if r and r.cx > ACTION_BUTTON_X_MIN and r.cy < ACTION_BUTTON_Y_MAX:
            return r.cx, r.cy, r.text
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

    # ── Step 0: Pathfinding idle (highest priority) ───────────────────────
    if _is_pathfinding(regions):
        status_cb("🚶 Pathfinding active — waiting for arrival…")
        quest_info = _build_quest_info(regions)
        return quest_info, False   # no click — just wait

    # ── Step 1: Dialog advancement ────────────────────────────────────────
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
        time.sleep(0.8)   # wait for dialog animation / text scroll
        # Dialog handled — fall through to quest navigation below so the
        # bot immediately picks up the next quest once the dialog clears.

    if not dlg:
        # ── Step 2: Interaction button check ──────────────────────────────
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

        # ── Step 3: Smart action button scan ──────────────────────────────
        action_btn = _find_action_button(regions)
        if action_btn:
            ax, ay, alabel = action_btn
            status_cb(
                f"🎯 Action button \"{alabel}\" at ({ax}, {ay}) — clicking"
            )
            click(ax, ay, bounds)
            time.sleep(0.4)
            quest_info = _build_quest_info(regions)
            return quest_info, True

    # ── Step 4: Quest row navigation ────────────────────────────────────────
    # Runs when: no dialog open, OR dialog just closed (dlg was set above).
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
