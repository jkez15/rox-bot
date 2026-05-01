"""
quests.py – Self-directing quest automation for RöX.

How it works
------------
Each call to do_quest_scan() runs one full OCR cycle and acts.

The engine reads the quest sidebar on every scan to extract:
  • Quest title    — "[Main] All Must be Found!"
  • Step text      — "Head to behind the cathedral."  (multi-line, merged)
  • Distance       — "118 m"
  • Target         — "Prontera"

It classifies the step type (NAVIGATE / TALK / EXAMINE / COLLECT /
COMBAT / DELIVER / ENTER / USE / PHOTO) and chooses the right action.
All observations and click actions are persisted to quest_progress.db
so the bot can detect stalls and build a full quest walkthrough over time.

Priority order each scan
------------------------
  0  PATHFINDING ACTIVE  →  wait, no click
  1  DIALOG / SKIP       →  click the button (or tap-to-advance)
  2  INTERACTION         →  Examine / Talk / Inspect button visible
  3  ACTION BUTTON       →  Use / Collect / Enter / etc. in game world
  4  QUEST NAVIGATION    →  (re)click [Main] row to set nav target
  5  STALL RECOVERY      →  if stuck N cycles, try alternative approach

Screen layout  (1051 × 816 logical px)
---------------------------------------
  x <  260            quest sidebar
  y <  300            top HUD  (HP/SP bars, minimap, Backpack)
  300 ≤ y < 620       game world  (NPCs, action buttons, dialogs)
  620 ≤ y < 770       dialog / chat zone
  y ≥  770            bottom HUD
"""

from __future__ import annotations

import re
import time
from typing import Callable, Optional

from capture import capture_window
from ocr import read_window, find_text, find_all_text
from log_monitor import tracker as _state_tracker
from actions import click
from quest_db import db as _db, classify_step

# ── Screen geometry ───────────────────────────────────────────────────────────
QUEST_PANEL_X_MAX = 260
HUD_TOP_Y_MAX     = 300
GAME_WORLD_Y_MAX  = 620
DIALOG_TEXT_Y_MIN = GAME_WORLD_Y_MAX   # 620
DIALOG_TEXT_Y_MAX = 770

# ── Confidence thresholds ─────────────────────────────────────────────────────
MIN_CONF_PATHFINDING = 0.30
MIN_CONF_QUEST       = 0.40
MIN_CONF_DIALOG      = 0.42
MIN_CONF_BUTTON      = 0.50
MIN_CONF_ACTION      = 0.50

# ── Pathfinding ───────────────────────────────────────────────────────────────
PATHFINDING_PATTERN = r"Pathfinding|Path\s*finding|Auto.?walk"

# ── Quest sidebar ─────────────────────────────────────────────────────────────
QUEST_PRIORITY: list[tuple[str, str]] = [
    (r"\[Main\]", "Main"),
]

# ── Interaction buttons ───────────────────────────────────────────────────────
INTERACTION_PATTERNS = [
    r"\bExamine\b",
    r"\bInspect\b",
    r"\bTalk\b",
    r"\bInvestigate\b",
]
INTERACTION_BUTTON_OFFSET_Y = -27   # icon sits above the text label

# ── Dialog buttons ────────────────────────────────────────────────────────────
SKIP_PATTERN = r"\bSkip\b"

DIALOG_CHOICE_PATTERNS = [
    r"Inquir",
    r"\bNext\b",
    r"Continu",
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
    r"I.ll\s*do\s*it",
    r"\bAccept\b",
    r"\bConfirm\b",
    r"\bStart\b",
    r"\bReceive\b",
    r"\bClaim\b",
    r"\bReward\b",
    r"Let.s\s*go",
    r"\bReturn\b",
]
DIALOG_CHOICE_X_MIN = QUEST_PANEL_X_MAX
DIALOG_ADVANCE_TAP_X = 650
DIALOG_ADVANCE_TAP_Y = 695

# ── Action buttons in game world ──────────────────────────────────────────────
ACTION_BUTTON_PATTERNS: list[str] = [
    r"\bShow\b", r"\bPresent\b", r"\bDisplay\b",
    r"\bPhotograph\b", r"\bPhoto\b", r"\bCapture\b",
    r"\bSnapshot\b", r"\bCamera\b",
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

# ── Stall detection ───────────────────────────────────────────────────────────
STALL_THRESHOLD = 12

# ── Per-run state ─────────────────────────────────────────────────────────────
_last_step_id: Optional[int] = None
_stall_recovery_count: int = 0


# ── Quest sidebar parsing ─────────────────────────────────────────────────────

def _parse_sidebar(regions) -> dict | None:
    """
    Extract quest data from the sidebar OCR regions.

    Returns a dict with keys:
      title, quest_type, step_text, distance, target, title_region
    """
    for pattern, qtype in QUEST_PRIORITY:
        title_r = find_text(regions, pattern, min_conf=MIN_CONF_QUEST)
        if title_r is None:
            continue

        sidebar_below = sorted(
            [
                r for r in regions
                if r.cx < QUEST_PANEL_X_MAX + 50
                and r.cy > title_r.cy
                and r.conf >= 0.35
            ],
            key=lambda r: r.cy,
        )

        step_lines: list[str] = []
        distance: Optional[int] = None
        target: Optional[str] = None

        for r in sidebar_below:
            t = r.text.strip()
            if not t:
                continue
            dm = re.search(r'[Dd]istance\s+to\s+target\s*:?\s*(\d+)\s*m', t)
            if dm:
                distance = int(dm.group(1))
                continue
            tm = re.search(r'[Tt]arget\s+location\s*:?\s*(.+)', t)
            if tm:
                target = tm.group(1).strip()
                continue
            if re.search(r'\[Main\]|\[Tutorial\]|\[Side\]|\[Daily\]', t):
                break
            step_lines.append(t)

        step_text = " ".join(step_lines).strip()

        # Build full title (may wrap onto next line)
        title_parts = [title_r.text]
        for r in sidebar_below[:2]:
            if (
                r.cy <= title_r.cy + 20
                and not re.search(r'\[Main\]|\[Tutorial\]|Distance|Target', r.text)
            ):
                title_parts.append(r.text)
        title = " ".join(title_parts).strip()

        return {
            "title": title,
            "quest_type": qtype,
            "step_text": step_text,
            "distance": distance,
            "target": target,
            "title_region": title_r,
        }

    return None


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_pathfinding(regions) -> bool:
    return find_text(regions, PATHFINDING_PATTERN, min_conf=MIN_CONF_PATHFINDING) is not None


def _find_dialog_button(regions):
    """Returns (cx, cy, label, action) or None."""
    skip = find_text(regions, SKIP_PATTERN, min_conf=MIN_CONF_DIALOG)
    if skip and skip.cx > QUEST_PANEL_X_MAX:
        return skip.cx, skip.cy, skip.text, "skip"

    for patt in DIALOG_CHOICE_PATTERNS:
        r = find_text(regions, patt, min_conf=MIN_CONF_DIALOG)
        if r and r.cx > DIALOG_CHOICE_X_MIN:
            if patt == r"\bLeave\b" and r.cy < HUD_TOP_Y_MAX:
                continue
            return r.cx, r.cy, r.text, "choice"

    dialog_text = [
        reg for reg in regions
        if DIALOG_TEXT_Y_MIN <= reg.cy <= DIALOG_TEXT_Y_MAX
        and reg.cx > QUEST_PANEL_X_MAX
        and len(reg.text.strip()) > 8
    ]
    if dialog_text:
        return DIALOG_ADVANCE_TAP_X, DIALOG_ADVANCE_TAP_Y, "[tap]", "tap"

    return None


def _find_interaction_button(regions, screenshot=None):
    """Return (cx, cy, label) for Examine/Talk/Inspect, or None."""
    for patt in INTERACTION_PATTERNS:
        r = find_text(regions, patt, min_conf=MIN_CONF_BUTTON)
        if r and r.cx > QUEST_PANEL_X_MAX and r.cy < GAME_WORLD_Y_MAX:
            return r.cx, r.cy + INTERACTION_BUTTON_OFFSET_Y, r.text

    if screenshot is not None:
        try:
            from recognizer import find_template
            match = find_template(screenshot, "examine_icon.png", threshold=0.75)
            if match:
                ix, iy, _ = match
                if ix > QUEST_PANEL_X_MAX and iy < GAME_WORLD_Y_MAX:
                    return ix, iy, "Examine"
        except Exception:
            pass

    return None


def _find_action_button(regions):
    """Return (cx, cy, label) for any game-world action button, or None."""
    for patt in ACTION_BUTTON_PATTERNS:
        r = find_text(regions, patt, min_conf=MIN_CONF_ACTION)
        if (
            r
            and r.cx > QUEST_PANEL_X_MAX
            and HUD_TOP_Y_MAX < r.cy < GAME_WORLD_Y_MAX
        ):
            return r.cx, r.cy, r.text
    return None


def _stall_recovery(sidebar, step_id, step_type, regions, screenshot, bounds, status_cb):
    """Try to break out of a stall. Returns True if a recovery click was sent."""
    global _stall_recovery_count
    _stall_recovery_count += 1
    attempt = _stall_recovery_count

    status_cb(f"⚠️  Stall #{attempt} on [{step_type}] — trying recovery")

    # Re-click the quest row to refresh navigation target
    if step_type in ("NAVIGATE", "TALK", "EXAMINE", "DELIVER",
                     "COLLECT", "COMBAT", "ENTER"):
        region = sidebar.get("title_region") if sidebar else None
        if region:
            status_cb("  ↩  Re-clicking quest row")
            click(region.cx, region.cy, bounds)
            _db.record_click(step_id, "navigate", "[stall-refresh]",
                             region.cx, region.cy, state_changed=False)
            time.sleep(0.5)
            return True

    # Low-conf scan for action buttons
    if step_type in ("USE", "PHOTO", "UNKNOWN"):
        for patt in ACTION_BUTTON_PATTERNS:
            r = find_text(regions, patt, min_conf=0.35)
            if r and r.cx > QUEST_PANEL_X_MAX and HUD_TOP_Y_MAX < r.cy < GAME_WORLD_Y_MAX:
                status_cb(f"  ↩  Low-conf button: \"{r.text}\"")
                click(r.cx, r.cy, bounds)
                _db.record_click(step_id, "action", r.text,
                                 r.cx, r.cy, state_changed=False)
                time.sleep(0.4)
                return True

    # Every 3rd stall attempt: tap game world centre
    if attempt % 3 == 0:
        tx, ty = 600, 450
        status_cb(f"  ↩  Tapping game world ({tx},{ty})")
        click(tx, ty, bounds)
        time.sleep(0.5)
        return True

    return False


# ── Public API ────────────────────────────────────────────────────────────────

def do_quest_scan(
    status_cb: Callable[[str], None] = print,
) -> tuple[dict | None, bool]:
    """
    Single OCR pass: capture → read → classify → act → persist.

    Returns (quest_info_dict | None, clicked: bool).
    """
    global _last_step_id, _stall_recovery_count

    screenshot, bounds = capture_window()
    if screenshot is None or bounds is None:
        status_cb("⚠  Cannot capture RöX window")
        return None, False

    regions = read_window(screenshot, min_conf=0.30)
    if not regions:
        status_cb("No text detected in window")
        return None, False

    _state_tracker.update(regions)

    # ── Step 0: Pathfinding active ────────────────────────────────────────
    if _is_pathfinding(regions):
        sidebar = _parse_sidebar(regions)
        dist = sidebar["distance"] if sidebar else None
        status_cb(f"🚶 Pathfinding{(' — ' + str(dist) + ' m') if dist else ''}")
        return _build_quest_info(sidebar), False

    # ── Parse sidebar & persist observation ──────────────────────────────
    sidebar = _parse_sidebar(regions)
    step_id: Optional[int] = None
    step_type: str = "UNKNOWN"

    if sidebar and sidebar["step_text"]:
        step_type = classify_step(sidebar["step_text"])
        step_id = _db.observe_step(
            quest_title=sidebar["title"],
            step_text=sidebar["step_text"],
            step_type=step_type,
            distance=sidebar["distance"],
            target=sidebar["target"],
        )

    # Detect step change → mark old step done, reset stall counter
    if step_id != _last_step_id:
        if _last_step_id is not None:
            _db.mark_step_done(_last_step_id)
            status_cb(f"✅ Previous step done — now [{step_type}]")
        _last_step_id = step_id
        _stall_recovery_count = 0

    # ── Step 1: Dialog / Skip ─────────────────────────────────────────────
    dlg = _find_dialog_button(regions)
    if dlg:
        dx, dy, dlabel, action = dlg
        if action == "skip":
            status_cb(f"⏭  Skip at ({dx},{dy})")
        elif action == "tap":
            status_cb("💬 NPC dialog — tapping to advance")
        else:
            status_cb(f"💬 '{dlabel}' at ({dx},{dy})")
        click(dx, dy, bounds)
        if step_id:
            _db.record_click(step_id, action, dlabel, dx, dy, state_changed=True)
        time.sleep(0.5 if action in ("skip", "tap") else 1.0)
        # Fall through to Step 4 to re-click quest row after dialog clears

    if not dlg:
        # ── Step 2: Interaction button ────────────────────────────────────
        btn = _find_interaction_button(regions, screenshot)
        if btn:
            bx, by, blabel = btn
            status_cb(f"🖱  {blabel} at ({bx},{by})")
            click(bx, by, bounds)
            if step_id:
                _db.record_click(step_id, "interact", blabel,
                                 bx, by, state_changed=True)
            time.sleep(0.4)
            return _build_quest_info(sidebar), True

        # ── Step 3: Action button ─────────────────────────────────────────
        act_btn = _find_action_button(regions)
        if act_btn:
            ax, ay, alabel = act_btn
            status_cb(f"🎯 '{alabel}' [{step_type}] at ({ax},{ay})")
            click(ax, ay, bounds)
            if step_id:
                _db.record_click(step_id, "action", alabel,
                                 ax, ay, state_changed=True)
            time.sleep(0.4)
            return _build_quest_info(sidebar), True

        # ── Stall check before Step 4 ─────────────────────────────────────
        if step_id and _db.is_stalled(step_id, STALL_THRESHOLD):
            recovered = _stall_recovery(
                sidebar, step_id, step_type,
                regions, screenshot, bounds, status_cb,
            )
            if recovered:
                return _build_quest_info(sidebar), True

    # ── Step 4: Quest row navigation ──────────────────────────────────────
    if sidebar:
        r = sidebar["title_region"]
        dist_str = f" ({sidebar['distance']} m)" if sidebar["distance"] else ""
        status_cb(f"👆 [{step_type}]{dist_str} {sidebar['step_text'][:50]!r}")
        click(r.cx, r.cy, bounds)
        if step_id:
            _db.record_click(step_id, "navigate", "[Main]",
                             r.cx, r.cy, state_changed=False)
        time.sleep(0.3)
        return _build_quest_info(sidebar), True

    visible = [r.text for r in regions[:6]]
    status_cb(f"No quest or action found. Visible: {visible}")
    return None, False


# ── Info dict for dashboard ───────────────────────────────────────────────────

def _build_quest_info(sidebar: dict | None) -> dict | None:
    if sidebar is None:
        return None
    step_type = classify_step(sidebar.get("step_text", ""))
    return {
        "type":      sidebar.get("quest_type", "?"),
        "title":     sidebar.get("title", ""),
        "step":      sidebar.get("step_text", ""),
        "step_type": step_type,
        "distance":  sidebar.get("distance"),
        "target":    sidebar.get("target"),
    }
