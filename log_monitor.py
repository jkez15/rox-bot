"""
log_monitor.py — Real-time Unity Player.log monitor for the RöX game.

The game writes debug output to its Unity Player.log file. By tailing this
file, we can observe game events (quest updates, scene transitions, NPC
interactions, errors) without any code injection.

Architecture
------------
  LogMonitor runs on a dedicated daemon thread.  It tails the log file,
  parses each new line, and pushes recognised events into a thread-safe
  deque that the automation loop can poll.

Typical Unity log locations (macOS):
  ~/Library/Logs/Unity/Player.log
  ~/Library/Containers/com.play.rosea/Data/Library/Logs/Unity/Player.log
  ~/Library/Containers/com.play.rosea/Data/Documents/Player.log

Usage
-----
    from log_monitor import LogMonitor, GameEvent

    monitor = LogMonitor()
    monitor.start()

    # In the automation loop:
    while True:
        for event in monitor.drain_events():
            if event.kind == "quest_complete":
                ...
            elif event.kind == "scene_change":
                ...
        # or check latest state:
        if monitor.current_scene:
            ...
"""

from __future__ import annotations

import os
import re
import time
import threading
from collections import deque
from dataclasses import dataclass, field


# ── Possible log file locations (checked in order) ───────────────────────────
_LOG_PATHS = [
    os.path.expanduser(
        "~/Library/Containers/com.play.rosea/Data/Library/Logs/Unity/Player.log"
    ),
    os.path.expanduser("~/Library/Logs/Unity/Player.log"),
    os.path.expanduser(
        "~/Library/Containers/com.play.rosea/Data/Documents/Player.log"
    ),
]

MAX_EVENTS = 200


# ── Event types ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class GameEvent:
    """A structured event parsed from a Unity log line."""
    kind: str           # e.g. "scene_change", "quest_update", "npc_interact"
    data: dict          # event-specific payload
    raw_line: str       # original log line
    timestamp: float    # time.time() when parsed


# ── Log line patterns ─────────────────────────────────────────────────────────
# These patterns are educated guesses based on Unity/HybridCLR conventions
# and the C# Dream.* namespace found in Assembly-CSharp.dll.  They will be
# refined once the live machine confirms actual log output.

_PATTERNS: list[tuple[str, re.Pattern, list[str]]] = [
    # Scene transitions
    ("scene_change", re.compile(
        r'(?:LoadScene|ChangeScene|EnterScene|OnSceneLoaded)\s*[:\(]\s*(\d+)',
        re.IGNORECASE
    ), ["scene_id"]),

    # Quest / task updates
    ("quest_update", re.compile(
        r'(?:TaskUpdate|QuestUpdate|TaskComplete|QuestComplete|AcceptTask'
        r'|SubmitTask|TaskProgress)\s*[:\(]\s*(\d+)',
        re.IGNORECASE
    ), ["task_id"]),

    # Quest completion
    ("quest_complete", re.compile(
        r'(?:TaskComplete|QuestComplete|FinishTask)\s*[:\(]\s*(\d+)',
        re.IGNORECASE
    ), ["task_id"]),

    # NPC interaction
    ("npc_interact", re.compile(
        r'(?:NPCInteract|TalkToNPC|NPCClick|OpenNPCDialog)\s*[:\(]\s*(\d+)',
        re.IGNORECASE
    ), ["npc_id"]),

    # Pathfinding / navigation
    ("pathfinding_start", re.compile(
        r'(?:StartPathfinding|AutoPathing|MoveToTarget|NavigateTo)\s*[:\(]\s*([\d.,-]+)',
        re.IGNORECASE
    ), ["target"]),

    ("pathfinding_end", re.compile(
        r'(?:PathfindingComplete|ReachTarget|ArrivedAt|StopPathing)',
        re.IGNORECASE
    ), []),

    # Player position (if logged)
    ("player_pos", re.compile(
        r'(?:PlayerPos|RolePos|Position)\s*[:\(]\s*([\d.-]+)\s*,\s*([\d.-]+)\s*,\s*([\d.-]+)',
        re.IGNORECASE
    ), ["x", "y", "z"]),

    # Dialog events
    ("dialog_open", re.compile(
        r'(?:OpenDialogue|ShowDialogue|DialogueStart)\s*[:\(]\s*(\d+)',
        re.IGNORECASE
    ), ["dialogue_id"]),

    ("dialog_close", re.compile(
        r'(?:CloseDialogue|DialogueEnd|HideDialogue)',
        re.IGNORECASE
    ), []),

    # Errors / warnings (always useful for debugging)
    ("unity_error", re.compile(
        r'^(?:Error|Exception|NullReferenceException|LuaException)',
        re.IGNORECASE
    ), []),

    # HP/SP changes
    ("hp_change", re.compile(
        r'(?:HPChange|DamageReceived|HealReceived)\s*[:\(]\s*([\d.-]+)',
        re.IGNORECASE
    ), ["value"]),

    # Item pickup
    ("item_pickup", re.compile(
        r'(?:PickupItem|GetItem|AddItem)\s*[:\(]\s*(\d+)\s*[,x]\s*(\d+)',
        re.IGNORECASE
    ), ["item_id", "count"]),
]


class LogMonitor:
    """
    Tails the Unity Player.log and emits GameEvent objects.

    Thread-safe: start() spawns a daemon thread; drain_events() is safe
    to call from any thread.
    """

    def __init__(self) -> None:
        self._events: deque[GameEvent] = deque(maxlen=MAX_EVENTS)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._log_path: str | None = None

        # Accumulated state derived from events
        self._current_scene: int | None = None
        self._last_quest_id: int | None = None
        self._is_pathfinding: bool = False

    # ── Public API ────────────────────────────────────────────────────────

    @property
    def log_path(self) -> str | None:
        return self._log_path

    @property
    def current_scene(self) -> int | None:
        with self._lock:
            return self._current_scene

    @property
    def is_pathfinding(self) -> bool:
        with self._lock:
            return self._is_pathfinding

    @property
    def last_quest_id(self) -> int | None:
        with self._lock:
            return self._last_quest_id

    def start(self) -> bool:
        """Start the log-tail thread.  Returns True if the log file was found."""
        self._log_path = self._find_log()
        if self._log_path is None:
            print("[LogMonitor] No Unity Player.log found — monitoring disabled")
            return False

        print(f"[LogMonitor] Tailing {self._log_path}")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._tail_loop,
            daemon=True,
            name="log-monitor",
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)

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

    # ── Internal ──────────────────────────────────────────────────────────

    @staticmethod
    def _find_log() -> str | None:
        for path in _LOG_PATHS:
            if os.path.exists(path):
                return path
        return None

    def _tail_loop(self) -> None:
        """Continuously read new lines appended to the log file."""
        path = self._log_path
        if path is None:
            return

        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                # Seek to end — we only care about NEW lines
                f.seek(0, 2)

                while not self._stop.is_set():
                    line = f.readline()
                    if line:
                        line = line.rstrip("\n\r")
                        if line:
                            self._process_line(line)
                    else:
                        # No new data — sleep briefly
                        time.sleep(0.1)
        except FileNotFoundError:
            print(f"[LogMonitor] Log file disappeared: {path}")

    def _process_line(self, line: str) -> None:
        """Match line against all known patterns and emit events."""
        for kind, pattern, field_names in _PATTERNS:
            m = pattern.search(line)
            if m:
                data: dict = {}
                for i, name in enumerate(field_names):
                    if i < len(m.groups()):
                        data[name] = m.group(i + 1)

                event = GameEvent(
                    kind=kind,
                    data=data,
                    raw_line=line,
                    timestamp=time.time(),
                )

                with self._lock:
                    self._events.append(event)
                    self._update_state(event)
                break   # one event per line

    def _update_state(self, event: GameEvent) -> None:
        """Update accumulated state from a new event (called under lock)."""
        if event.kind == "scene_change":
            try:
                self._current_scene = int(event.data.get("scene_id", 0))
            except (ValueError, TypeError):
                pass
        elif event.kind == "quest_update":
            try:
                self._last_quest_id = int(event.data.get("task_id", 0))
            except (ValueError, TypeError):
                pass
        elif event.kind == "pathfinding_start":
            self._is_pathfinding = True
        elif event.kind == "pathfinding_end":
            self._is_pathfinding = False


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    monitor = LogMonitor()
    if not monitor.start():
        print("No log file found. Run this on the Mac with RöX installed.")
        print(f"Searched: {_LOG_PATHS}")
        import sys
        sys.exit(1)

    print(f"Monitoring: {monitor.log_path}")
    print("Press Ctrl+C to stop.\n")
    try:
        while True:
            events = monitor.drain_events()
            for e in events:
                print(f"  [{e.kind}] {e.data}  ← {e.raw_line[:120]}")
            time.sleep(0.5)
    except KeyboardInterrupt:
        monitor.stop()
        print("\nStopped.")
