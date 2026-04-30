"""
quests.py – Quest automation for RöX using Apple Vision OCR.

Quest cycle (priority-ordered state machine per scan)
-----------------------------------------------------
  Step 0 — PATHFINDING IDLE (highest priority)
    Character is auto-walking.  Do nothing until 'Pathfinding' text clears.

  Step 1 — DIALOG ADVANCEMENT
    Explicit dialog buttons (Skip / Inquire / Next / Continue / OK…) are
    required to trigger this step.  NPC speech text alone is only used as a
    spam-click fallback when no button is visible.

  Step 2 — INTERACTION CHECK
    'Examine' / 'Inspect' button in the game world → click the icon above it.

  Step 3 — SMART ACTION BUTTONS
    Any interactive button in the game-world zone (outside quest panel,
    above dialog zone).

  Step 4 — QUEST NAVIGATION (lowest priority)
    Click the [Main] quest row to set it as the active navigation target.

Screen layout (1051 × 816 logical pixels)
------------------------------------------
  x < 260            → quest sidebar
  y < 300            → top HUD  (HP/SP bars, minimap, Backpack, Leave)
  300 ≤ y < 620       → game world (NPC buttons, action buttons, dialogs)
  620 ≤ y < 770       → dialog / chat zone
  y ≥ 770            → bottom HUD (level bar, chat input)
"""

from __future__ import annotations

import re
import time
from typing import Callable

from capture import capture_window
from ocr import read_window, find_text, find_all_text
from actions import click


# ── Screen geometry ──────────────────────────────────────────────────────────

# Anything left of this x is inside the quest-panel sidebar.
QUEST_PANEL_X_MAX = 260

# Top HUD boundary: HP/SP, minimap, Backpack, Leave dungeon button.
# Nothing above this y can ever be a dialog choice or action button.
HUD_TOP_Y_MAX = 300

# Bottom of the game-world area.  Below this is the dialog/chat zone.
GAME_WORLD_Y_MAX = 620

# Dialog / NPC speech zone.
DIALOG_TEXT_Y_MIN = GAME_WORLD_Y_MAX      # 620
DIALOG_TEXT_Y_MAX = 770


# ── Pathfinding detection ────────────────────────────────────────────────────
PATHFINDING_PATTERN = r"Pathfinding|Path\s*finding|Auto.?walk"
MIN_CONF_PATHFINDING = 0.30


# ── Quest priority ────────────────────────────────────────────────────────────
# Only [Main] quests are pursued.  First match wins.
QUEST_PRIORITY: list[tuple[str, str]] = [
    (r"\[Main\]", "Main"),
]
MIN_CONF_QUEST = 0.40


# ── Interaction button (Examine / Inspect / Talk) ────────────────────────────
INTERACTION_PATTERNS = [
    r"\bExamine\b",
    r"\bInspect\b",
    r"\bTalk\b",
]
# Icon button sits this many pixels ABOVE the 'Examine' text label.
# Measured: Examine @ (713,279), yellow icon centroid @ (705,252) → 27px up.
INTERACTION_BUTTON_OFFSET_Y = -27
MIN_CONF_BUTTON = 0.50


# ── Smart action buttons ─────────────────────────────────────────────────────
# Zone: cx > QUEST_PANEL_X_MAX  AND  HUD_TOP_Y_MAX < cy < GAME_WORLD_Y_MAX
ACTION_BUTTON_PATTERNS: list[str] = [
    r"\bShow\b", r"\bPresent\b", r"\bDisplay\b",
    r"\bPhotograph\b", r"\bPhoto\b", r"\bCapture\b",
    r"\bSnapshot\b", r"\bCamera\b", r"\bShoot\b",
    r"\bCollect\b", r"\bGather\b", r"\bPick\s*up\b",
    r"\bLoot\b", r"\bHarvest\b",
    r"\bActivate\b", r"\bUse\b", r"\bOpen\b",
    r"\bInteract\b", r"\bTouch\b", r"\bPress\b",
    r"\bPush\b", r"\bPull\b", r"\bPlace\b", r"\bDrop\b",
    r"\bInvestigate\b", r"\bCheck\b",
    r"\bAttack\b", r"\bFight\b", r"\bEnter\b",
    r"\bChallenge\b", r"\bBegin\b",
    r"\bDeliver\b", r"\bGive\b", r"\bHand\s*over\b",
    r"\bSubmit\b", r"\bTurn\s*in\b", r"\bReport\b",
    r"\bRepair\b", r"\bCraft\b", r"\bBuild\b",
    r"\bSummon\b", r"\bPlay\b", r"\bRead\b",
    r"\bSearch\b", r"\bDig\b", r"\bFish\b",
    r"\bCook\b", r"\bBrew\b",
    r"\bAccept\b", r"\bConfirm\b", r"\bComplete\b",
    r"\bClaim\b", r"\bReceive\b",
    r"\bExchange\b", r"\bTrade\b", r"\bBuy\b", r"\bSell\b",
]
MIN_CONF_ACTION = 0.50


# ── Dialog buttons ────────────────────────────────────────────────────────────
SKIP_PATTERN = r"\bSkip\b"

# Advance / close buttons.  Must be below HUD and right of quest sidebar.
DIALOG_CHOICE_PATTERNS = [
    r"Inquir",      # 'Inquire' — completes NPC conversation
    r"\bNext\b",
    r"Continu",     # 'Continue'
    r"\bClose\b",
    r"\bOk\b", r"\bOK\b",
    r"\bYes\b",
    r"\bAgree\b",
    r"Got\s*it",
    r"Understood",
    r"I\s*see",
    r"\bDone\b",
    r"\bFinish\b",
    r"\bBye\b",
    r"\bThanks\b",
]
# Choice buttons: below the HUD, right of the quest sidebar.
DIALOG_CHOICE_X_MIN = QUEST_PANEL_X_MAX   # 260
DIALOG_CHOICE_Y_MIN = HUD_TOP_Y_MAX       # 300 — never click Leave/Backpack

MIN_CONF_DIALOG = 0.50

# Chat / world-message exclusion for the NPC speech spam-click fallback.
_CHAT_EXCLUSION = re.compile(
    r'^\S+:'             # PlayerName: message
    r'|\bLv\.'
    r'|\bRecruit\b'
    r'|\bWorld\b'
    r'|\bGuild\b'
    r'|Endless\s+Tower'
    r'|\bFRESH\b'
    r'|\bJOIN\b'
    r'|\bDungeon\b'
    r'|\bAFK\b'
    r'|\bauto\s+join\b',
    re.IGNORECASE,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_distance(regions) -> str | None:
    """Return e.g. '31 m' from 'Distance to target: 31 m', or None."""
    r = find_text(regions, r"Distance to target", min_conf=0.40)
    if r:
        m = re.search(r"Distance to target\s*:?\s*(.+)", r.text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _extract_target(regions) -> str | None:
    """Return e.g. 'Prontera South Gate' from 'Target location: …', or None."""
    r = find_text(regions, r"Target location", min_conf=0.40)
    if r:
        m = re.search(r"Target location\s*:?\s*(.+)", r.text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def _build_quest_title(regions) -> tuple[str, str, object] | None:
    """
    Find the [Main] quest row and reconstruct the full title.

    Vision sometimes splits '[Main] Bernard's' and 'Recollection' into two
    separate regions because of line wrapping.  We merge consecutive
    quest-panel regions that are vertically adjacent (<= 30px apart).

    Returns (quest_type, full_title_text, region) or None.
    """
    for pattern, qtype in QUEST_PRIORITY:
        r = find_text(regions, pattern, min_conf=MIN_CONF_QUEST)
        if r is None:
            continue
        # Gather adjacent regions in the quest panel that are below the
        # matched row within 30px (continuation of the same wrapped title).
        parts = [r.text]
        for other in sorted(regions, key=lambda o: o.cy):
            if other is r:
                continue
            if (
                other.cx < QUEST_PANEL_X_MAX + 50
                and r.cy < other.cy <= r.cy + 30
                and other.conf >= MIN_CONF_QUEST
                and not re.search(r"\[Main\]|\[Tutorial\]|Distance|Target", other.text)
            ):
                parts.append(other.text)
        return qtype, " ".join(parts), r
    return None


def _is_pathfinding(regions) -> bool:
    return find_text(regions, PATHFINDING_PATTERN, min_conf=MIN_CONF_PATHFINDING) is not None


def _find_dialog_button(regions):
    """
    Returns (cx, cy, label, action) if a dialog interaction is needed, else None.

    Priority:
      1. Skip button (anywhere outside quest sidebar, below HUD)
      2. Explicit choice button (below HUD, outside sidebar)
      3. NPC speech spam-click (only clear multi-word sentence in dialog zone)
    """
    # 1. Skip
    skip = find_text(regions, SKIP_PATTERN, min_conf=MIN_CONF_DIALOG)
    if skip and skip.cx > QUEST_PANEL_X_MAX and skip.cy > HUD_TOP_Y_MAX:
        return skip.cx, skip.cy, skip.text, "skip"

    # 2. Choice buttons
    for pattern in DIALOG_CHOICE_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_DIALOG)
        if r and r.cx > DIALOG_CHOICE_X_MIN and r.cy > DIALOG_CHOICE_Y_MIN:
            return r.cx, r.cy, r.text, "choice"

    # 3. NPC speech spam-click fallback
    for r in sorted(regions, key=lambda r: r.cy):
        if (
            DIALOG_TEXT_Y_MIN < r.cy < DIALOG_TEXT_Y_MAX
            and r.conf >= 0.70
            and len(r.text.split()) >= 4
            and not _CHAT_EXCLUSION.search(r.text)
        ):
            return r.cx, r.cy, r.text[:40], "spam"

    return None


def _find_interaction_button(regions):
    """Return (cx, cy, label) for Examine/Inspect/Talk, or None."""
    for pattern in INTERACTION_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_BUTTON)
        if r and r.cx > QUEST_PANEL_X_MAX and HUD_TOP_Y_MAX < r.cy < GAME_WORLD_Y_MAX:
            return r.cx, r.cy + INTERACTION_BUTTON_OFFSET_Y, r.text
    return None


def _find_action_button(regions):
    """Return (cx, cy, label) for any game-world action button, or None."""
    for pattern in ACTION_BUTTON_PATTERNS:
        r = find_text(regions, pattern, min_conf=MIN_CONF_ACTION)
        if (
            r
            and r.cx > QUEST_PANEL_X_MAX
            and HUD_TOP_Y_MAX < r.cy < GAME_WORLD_Y_MAX
        ):
            return r.cx, r.cy, r.text
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def do_quest_scan(
    status_cb: Callable[[str], None] = print,
) -> tuple[dict | None, bool]:
    """
    Single Vision pass: capture → read text → act.

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

    regions = read_window(screenshot, min_conf=0.30)
    if not regions:
        status_cb("No text detected in window")
        return None, False

    # ── Step 0: Pathfinding idle ──────────────────────────────────────────
    if _is_pathfinding(regions):
        status_cb("🚶 Pathfinding active — waiting for arrival…")
        return _make_quest_info(regions), False

    # ── Step 1: Dialog advancement ────────────────────────────────────────
    dlg = _find_dialog_button(regions)
    if dlg:
        dx, dy, dlabel, action = dlg
        if action == "skip":
            status_cb(f"💬 Skipping cutscene at ({dx}, {dy})")
        elif action == "choice":
            status_cb(f"💬 Dialog — clicking \"{dlabel}\" at ({dx}, {dy})")
        else:
            status_cb(f"💬 NPC speech — advancing dialog at ({dx}, {dy})")
        click(dx, dy, bounds)
        time.sleep(0.8)
        # Fall through to Step 4 so the quest row is re-clicked once the
        # dialog clears.

    if not dlg:
        # ── Step 2: Interaction button ────────────────────────────────────
        btn = _find_interaction_button(regions)
        if btn:
            bx, by, blabel = btn
            status_cb(f"🖱  Interact \"{blabel}\" at ({bx}, {by})")
            click(bx, by, bounds)
            time.sleep(0.4)
            return _make_quest_info(regions), True

        # ── Step 3: Action button ─────────────────────────────────────────
        action_btn = _find_action_button(regions)
        if action_btn:
            ax, ay, alabel = action_btn
            status_cb(f"🎯 Action \"{alabel}\" at ({ax}, {ay})")
            click(ax, ay, bounds)
            time.sleep(0.4)
            return _make_quest_info(regions), True

    # ── Step 4: Quest row navigation ──────────────────────────────────────
    quest = _build_quest_title(regions)
    info  = _make_quest_info(regions, quest)

    if quest:
        qtype, title, region = quest
        status_cb(f"👆 [{qtype}] {title!r} — clicking to navigate")
        click(region.cx, region.cy, bounds)
        time.sleep(0.3)
        return info, True

    visible = [r.text for r in regions[:6]]
    status_cb(f"No quest or action found. Visible: {visible}")
    return info, False


# ── Internal ──────────────────────────────────────────────────────────────────

def _make_quest_info(regions, quest_tuple=None) -> dict | None:
    """Build the quest-info dict shown in the dashboard."""
    distance = _extract_distance(regions)
    target   = _extract_target(regions)

    if quest_tuple is None:
        quest_tuple = _build_quest_title(regions)
    if quest_tuple is None:
        return None

    qtype, title, _ = quest_tuple
    return {
        "type":     qtype,
        "title":    title,
        "distance": distance,
        "target":   target,
    }
