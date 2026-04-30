"""
log_monitor.py — OCR-driven game state tracker for the RöX automation bot.

Background
----------
RöX (production iOS Catalyst build) does NOT write a Unity Player.log.
The game's only log files are proprietary ByteDance `.alog` files stored at:
  ~/Library/Containers/com.play.rosea/Data/Library/alog/default/ready/
These are fully encrypted/compressed binary blobs — not readable.

Strategy
--------
Instead of tailing a log file, we derive game state from the OCR regions
that the automation loop already captures each scan cycle.  After every call
to `read_window()`, pass the result to `tracker.update(regions)`.
The tracker extracts:

  • Pathfinding state                 ("Distance to target: N m" text)
  • Distance to target                (exact metres, 0 = arrived)
  • Dialog open/close                 (Skip/Next/Close buttons visible)
  • NPC interaction available         (Examine/Inspect/Talk label visible)
  • Dungeon mode                      (Leave button in top HUD)
  • Active quest title                ([Main] row in quest sidebar)

All state is updated atomically under a lock so the Tkinter thread can
safely read it via the properties.

Usage
-----
    from log_monitor import tracker, GameEvent

    # In the automation loop (worker thread), after OCR:
    regions = read_window(screenshot)
    events = tracker.update(regions)
    for e in events:
        print(e.kind, e.data)

    # From any thread — read accumulated state:
    if tracker.is_pathfinding:
        pass
    if tracker.distance_to_target == 0:
        pass
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ocr import TextRegion


MAX_EVENTS = 200

# OCR text patterns
_DIST_PATTERN    = re.compile(r'[Dd]istance\s+to\s+target[:\s]+(\d+)\s*m')
_DUNGEON_LEAVE   = re.compile(r'\bLeave\b', re.IGNORECASE)
_DIALOG_BUTTONS  = re.compile(r'\b(?:Skip|Next|Close|Inquire|Continue|OK)\b',
                               re.IGNORECASE)
_EXAMINE_LABEL   = re.compile(r'\b(?:Examine|Inspect|Talk|Interact)\b',
                               re.IGNORECASE)
_QUEST_MAIN      = re.compile(r'\[Main\]')


@dataclass(frozen=True)
class GameEvent:
    """A structured state-change event derived from OCR regions."""
    kind: str           # e.g. "pathfinding_started", "arrived", "dialog_open"
    data: dict
    timestamp: float = field(default_factory=time.time)

    def __str__(self) -> str:
        return f"[{self.kind}] {self.data}"


class GameStateTracker:
    """
    Derives and tracks game state from OCR scan results.

    All public properties are thread-safe.
    Call update(regions) from the worker thread after every read_window().
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._events: deque[GameEvent] = deque(maxlen=MAX_EVENTS)

        self._is_pathfinding: bool = False
        self._distance_to_target: int | None = None
        self._active_quest_title: str | None = None
        self._dialog_open: bool = False
        self._in_dungeon: bool = False
        self._npc_nearby: bool = False

    # ── Public properties ─────────────────────────────────────────────────

    @property
    def is_pathfinding(self) -> bool:
        with self._lock:
            return self._is_pathfinding

    @property
    def distance_to_target(self) -> int | None:
        """Metres to current navigation target, or None if not pathfinding."""
        with self._lock:
            return self._distance_to_target

    @property
    def active_quest_title(self) -> str | None:
        with self._lock:
            return self._active_quest_title

    @property
    def dialog_open(self) -> bool:
        with self._lock:
            return self._dialog_open

    @property
    def in_dungeon(self) -> bool:
        with self._lock:
            return self._in_dungeon

    @property
    def npc_nearby(self) -> bool:
        """True when an Examine/Inspect/Talk button is visible."""
        with self._lock:
            return self._npc_nearby

    # ── Core update method ────────────────────────────────────────────────

    def update(self, regions: list) -> list[GameEvent]:
        """
        Parse a fresh list of OCR TextRegions and update internal state.
        Returns a list of new GameEvents (state changes only).
        Call this from the worker thread after every read_window().
        """
        all_text = " ".join(r.text for r in regions)
        new_events: list[GameEvent] = []

        # 1. Distance / pathfinding
        dist_match = _DIST_PATTERN.search(all_text)
        if dist_match:
            dist = int(dist_match.group(1))
            with self._lock:
                prev_pf   = self._is_pathfinding
                prev_dist = self._distance_to_target
                self._is_pathfinding    = dist > 0
                self._distance_to_target = dist
                if not prev_pf and dist > 0:
                    e = GameEvent("pathfinding_started", {"distance": dist})
                    self._events.append(e); new_events.append(e)
                if prev_dist and prev_dist > 0 and dist == 0:
                    e = GameEvent("arrived", {"previous_distance": prev_dist})
                    self._events.append(e); new_events.append(e)
        else:
            with self._lock:
                if self._is_pathfinding:
                    e = GameEvent("pathfinding_ended", {})
                    self._events.append(e); new_events.append(e)
                self._is_pathfinding    = False
                self._distance_to_target = None

        # 2. Dialog open/close
        has_dialog = bool(_DIALOG_BUTTONS.search(all_text))
        with self._lock:
            was_open = self._dialog_open
            self._dialog_open = has_dialog
            if not was_open and has_dialog:
                e = GameEvent("dialog_open", {})
                self._events.append(e); new_events.append(e)
            elif was_open and not has_dialog:
                e = GameEvent("dialog_closed", {})
                self._events.append(e); new_events.append(e)

        # 3. NPC nearby (Examine/Talk button visible)
        has_npc = bool(_EXAMINE_LABEL.search(all_text))
        with self._lock:
            was_npc = self._npc_nearby
            self._npc_nearby = has_npc
            if not was_npc and has_npc:
                e = GameEvent("npc_in_range", {})
                self._events.append(e); new_events.append(e)
            elif was_npc and not has_npc:
                e = GameEvent("npc_out_of_range", {})
                self._events.append(e); new_events.append(e)

        # 4. Dungeon detection (Leave button in top HUD area, y < 300)
        in_dungeon = any(
            _DUNGEON_LEAVE.search(r.text) and r.cy < 300
            for r in regions
        )
        with self._lock:
            was_dungeon = self._in_dungeon
            self._in_dungeon = in_dungeon
            if not was_dungeon and in_dungeon:
                e = GameEvent("dungeon_entered", {})
                self._events.append(e); new_events.append(e)
            elif was_dungeon and not in_dungeon:
                e = GameEvent("dungeon_exited", {})
                self._events.append(e); new_events.append(e)

        # 5. Active quest title — first [Main] row in sidebar (x < 260)
        quest_regions = [
            r for r in regions
            if _QUEST_MAIN.search(r.text) and r.cx < 260
        ]
        if quest_regions:
            title = quest_regions[0].text.strip()
            with self._lock:
                if self._active_quest_title != title:
                    old = self._active_quest_title
                    self._active_quest_title = title
                    e = GameEvent("quest_changed", {"old": old, "new": title})
                    self._events.append(e); new_events.append(e)

        return new_events

    # ── Event queue API ───────────────────────────────────────────────────

    def drain_events(self) -> list[GameEvent]:
        """Return and clear all queued events (thread-safe)."""
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    def peek_events(self, n: int = 10) -> list[GameEvent]:
        """Return the last N events without clearing (thread-safe)."""
        with self._lock:
            return list(self._events)[-n:]

    def state_summary(self) -> dict:
        """Return a snapshot of all tracked state (thread-safe)."""
        with self._lock:
            return {
                "is_pathfinding":      self._is_pathfinding,
                "distance_to_target":  self._distance_to_target,
                "active_quest_title":  self._active_quest_title,
                "dialog_open":         self._dialog_open,
                "in_dungeon":          self._in_dungeon,
                "npc_nearby":          self._npc_nearby,
            }


# ── Module-level singleton ────────────────────────────────────────────────────
tracker = GameStateTracker()


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    print("GameStateTracker — OCR-based state tracker (no log file)")
    print()
    print("RöX does NOT write a Unity Player.log.")
    print("The .alog files at:")
    print("  ~/Library/Containers/com.play.rosea/Data/Library/alog/default/ready/")
    print("are ByteDance SDK binary blobs — not readable game events.")
    print()
    print("Usage:")
    print("  from log_monitor import tracker")
    print("  events = tracker.update(regions)   # call after every read_window()")
    print("  print(tracker.state_summary())")
    sys.exit(0)
