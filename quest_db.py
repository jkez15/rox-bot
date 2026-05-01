"""
quest_db.py — SQLite-backed local database for quest automation state.

Stores everything the bot observes and does so it can:
  • Track which quest steps have been seen / completed
  • Detect stalls (same step, no progress for N cycles)
  • Record which click actions produce state changes
  • Build a learned history of the full main quest chain

Database location: quest_progress.db  (same directory as this file)

Tables
------
  quest_steps
    Unique (title, step_text) pairs — one row per distinct quest step.
    Tracks how many times seen, first/last seen, completion status,
    step type, and distance readings.

  click_actions
    Every click the bot performs: what quest step was active, what was
    clicked, and whether it produced a state change (dialog opened,
    pathfinding started, etc.)

  quest_chain
    Ordered log of completed steps — builds a walkthrough over time.

Usage (from quests.py)
----------------------
    from quest_db import QuestDB
    db = QuestDB()                          # one instance, kept alive

    step_id = db.observe_step(title, step_text, step_type, distance, target)
    db.record_click(step_id, "choice", "Next", 540, 400, state_changed=True)
    db.mark_step_done(step_id)
    stalled = db.is_stalled(step_id, threshold=8)
"""

from __future__ import annotations

import os
import re
import sqlite3
import time
from dataclasses import dataclass
from typing import Optional

DB_PATH = os.path.join(os.path.dirname(__file__), "quest_progress.db")

# ── Step type classifier ─────────────────────────────────────────────────────
# Ordered — first match wins.
_STEP_TYPE_RULES: list[tuple[str, str]] = [
    (r"\b(?:Head|Go|Travel|Move|Walk|Navigate)\s+to\b", "NAVIGATE"),
    (r"\bReturn\s+to\b",                                 "NAVIGATE"),
    (r"\b(?:Talk|Speak|Chat)\s+(?:to|with)\b",           "TALK"),
    (r"\b(?:Find|Locate|Look\s+for)\b.*\b(?:NPC|person|man|woman|guard|knight|merchant|adventurer)\b",
                                                         "TALK"),
    (r"\b(?:Examine|Inspect|Investigate|Check|Look\s+at)\b", "EXAMINE"),
    (r"\b(?:Collect|Gather|Pick\s+up|Obtain|Get|Acquire|Retrieve)\b", "COLLECT"),
    (r"\b(?:Defeat|Kill|Hunt|Slay|Eliminate|Destroy|Fight|Battle)\b", "COMBAT"),
    (r"\b(?:Deliver|Give|Hand|Submit|Turn\s+in|Report|Bring)\b", "DELIVER"),
    (r"\b(?:Enter|Go\s+inside|Proceed\s+into)\b",        "ENTER"),
    (r"\b(?:Use|Activate|Press|Push|Place|Deploy)\b",    "USE"),
    (r"\b(?:Photograph|Photo|Snapshot|Capture)\b",       "PHOTO"),
]

_STEP_TYPE_RE = [(re.compile(p, re.IGNORECASE), t) for p, t in _STEP_TYPE_RULES]


def classify_step(text: str) -> str:
    """Return a step type string for the given step description text."""
    for pattern, stype in _STEP_TYPE_RE:
        if pattern.search(text):
            return stype
    return "UNKNOWN"


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class QuestStep:
    step_id: int
    quest_title: str
    step_text: str
    step_type: str
    times_seen: int
    first_seen: float
    last_seen: float
    last_distance: Optional[int]
    last_target: Optional[str]
    completed: bool
    completed_at: Optional[float]


# ── Database ──────────────────────────────────────────────────────────────────

class QuestDB:
    """Thread-safe SQLite wrapper for quest progress tracking."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────

    def _init_schema(self) -> None:
        c = self._conn
        c.executescript("""
        CREATE TABLE IF NOT EXISTS quest_steps (
            step_id       INTEGER PRIMARY KEY AUTOINCREMENT,
            quest_title   TEXT    NOT NULL,
            step_text     TEXT    NOT NULL,
            step_type     TEXT    NOT NULL DEFAULT 'UNKNOWN',
            times_seen    INTEGER NOT NULL DEFAULT 1,
            first_seen    REAL    NOT NULL,
            last_seen     REAL    NOT NULL,
            last_distance INTEGER,
            last_target   TEXT,
            completed     INTEGER NOT NULL DEFAULT 0,
            completed_at  REAL,
            UNIQUE(quest_title, step_text)
        );

        CREATE TABLE IF NOT EXISTS click_actions (
            action_id     INTEGER PRIMARY KEY AUTOINCREMENT,
            step_id       INTEGER REFERENCES quest_steps(step_id),
            action_type   TEXT,    -- 'skip','tap','choice','interact','action','navigate'
            action_label  TEXT,
            cx            INTEGER,
            cy            INTEGER,
            state_changed INTEGER NOT NULL DEFAULT 0,
            timestamp     REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS quest_chain (
            chain_id      INTEGER PRIMARY KEY AUTOINCREMENT,
            quest_title   TEXT    NOT NULL,
            step_text     TEXT    NOT NULL,
            step_type     TEXT    NOT NULL,
            completed_at  REAL    NOT NULL,
            duration_s    REAL,   -- seconds from first_seen to completed
            click_count   INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_steps_title ON quest_steps(quest_title);
        CREATE INDEX IF NOT EXISTS idx_actions_step ON click_actions(step_id);
        CREATE INDEX IF NOT EXISTS idx_chain_title ON quest_chain(quest_title);
        """)
        c.commit()

    # ── Core API ──────────────────────────────────────────────────────────

    def observe_step(
        self,
        quest_title: str,
        step_text: str,
        step_type: str,
        distance: Optional[int] = None,
        target: Optional[str] = None,
    ) -> int:
        """
        Record that we saw this step this scan cycle.
        Inserts on first sight, increments times_seen thereafter.
        Returns the step_id.
        """
        now = time.time()
        c = self._conn
        row = c.execute(
            "SELECT step_id, completed FROM quest_steps "
            "WHERE quest_title=? AND step_text=?",
            (quest_title, step_text),
        ).fetchone()

        if row is None:
            cur = c.execute(
                "INSERT INTO quest_steps "
                "(quest_title, step_text, step_type, times_seen, first_seen, "
                " last_seen, last_distance, last_target) "
                "VALUES (?,?,?,1,?,?,?,?)",
                (quest_title, step_text, step_type, now, now, distance, target),
            )
            c.commit()
            return cur.lastrowid  # type: ignore[return-value]
        else:
            c.execute(
                "UPDATE quest_steps SET times_seen=times_seen+1, last_seen=?, "
                "last_distance=?, last_target=? "
                "WHERE step_id=?",
                (now, distance, target, row["step_id"]),
            )
            c.commit()
            return int(row["step_id"])

    def record_click(
        self,
        step_id: int,
        action_type: str,
        action_label: str,
        cx: int,
        cy: int,
        state_changed: bool = False,
    ) -> None:
        """Log a click action taken while this step was active."""
        self._conn.execute(
            "INSERT INTO click_actions "
            "(step_id, action_type, action_label, cx, cy, state_changed, timestamp) "
            "VALUES (?,?,?,?,?,?,?)",
            (step_id, action_type, action_label, cx, cy, int(state_changed),
             time.time()),
        )
        self._conn.commit()

    def mark_step_done(self, step_id: int) -> None:
        """Mark a step as completed and append it to the quest chain log."""
        now = time.time()
        row = self._conn.execute(
            "SELECT * FROM quest_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if row is None or row["completed"]:
            return

        duration = now - row["first_seen"]
        click_count = self._conn.execute(
            "SELECT COUNT(*) FROM click_actions WHERE step_id=?", (step_id,)
        ).fetchone()[0]

        self._conn.execute(
            "UPDATE quest_steps SET completed=1, completed_at=? WHERE step_id=?",
            (now, step_id),
        )
        self._conn.execute(
            "INSERT INTO quest_chain "
            "(quest_title, step_text, step_type, completed_at, duration_s, click_count) "
            "VALUES (?,?,?,?,?,?)",
            (row["quest_title"], row["step_text"], row["step_type"],
             now, duration, click_count),
        )
        self._conn.commit()

    def is_stalled(self, step_id: int, threshold: int = 10) -> bool:
        """
        Return True if this step has been seen >= threshold times without
        completing.  Signals the engine to try a different approach.
        """
        row = self._conn.execute(
            "SELECT times_seen, completed FROM quest_steps WHERE step_id=?",
            (step_id,),
        ).fetchone()
        if row is None:
            return False
        return bool(row["times_seen"] >= threshold and not row["completed"])

    def get_step(self, step_id: int) -> Optional[QuestStep]:
        row = self._conn.execute(
            "SELECT * FROM quest_steps WHERE step_id=?", (step_id,)
        ).fetchone()
        if row is None:
            return None
        return QuestStep(
            step_id=row["step_id"],
            quest_title=row["quest_title"],
            step_text=row["step_text"],
            step_type=row["step_type"],
            times_seen=row["times_seen"],
            first_seen=row["first_seen"],
            last_seen=row["last_seen"],
            last_distance=row["last_distance"],
            last_target=row["last_target"],
            completed=bool(row["completed"]),
            completed_at=row["completed_at"],
        )

    def active_step_for(self, quest_title: str) -> Optional[QuestStep]:
        """Return the most-recently-seen incomplete step for a quest title."""
        row = self._conn.execute(
            "SELECT * FROM quest_steps "
            "WHERE quest_title=? AND completed=0 "
            "ORDER BY last_seen DESC LIMIT 1",
            (quest_title,),
        ).fetchone()
        if row is None:
            return None
        return self.get_step(row["step_id"])

    def click_count_for(self, step_id: int) -> int:
        """How many clicks have been sent while this step was active."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM click_actions WHERE step_id=?", (step_id,)
        ).fetchone()
        return int(row[0])

    def quest_chain_summary(self, quest_title: str) -> list[dict]:
        """Return all completed steps for a quest, ordered by completion time."""
        rows = self._conn.execute(
            "SELECT step_text, step_type, completed_at, duration_s, click_count "
            "FROM quest_chain WHERE quest_title=? ORDER BY completed_at ASC",
            (quest_title,),
        ).fetchall()
        return [dict(r) for r in rows]

    def all_quest_titles(self) -> list[str]:
        """Return every distinct quest title the bot has ever tracked."""
        rows = self._conn.execute(
            "SELECT DISTINCT quest_title FROM quest_steps ORDER BY quest_title"
        ).fetchall()
        return [r[0] for r in rows]

    def stats(self) -> dict:
        """Quick summary for the dashboard."""
        steps_total = self._conn.execute(
            "SELECT COUNT(*) FROM quest_steps"
        ).fetchone()[0]
        steps_done = self._conn.execute(
            "SELECT COUNT(*) FROM quest_steps WHERE completed=1"
        ).fetchone()[0]
        clicks_total = self._conn.execute(
            "SELECT COUNT(*) FROM click_actions"
        ).fetchone()[0]
        quests = self._conn.execute(
            "SELECT COUNT(DISTINCT quest_title) FROM quest_steps"
        ).fetchone()[0]
        return {
            "quests_tracked": quests,
            "steps_total": steps_total,
            "steps_completed": steps_done,
            "clicks_total": clicks_total,
        }

    def close(self) -> None:
        self._conn.close()


# ── Module-level singleton (shared across quests.py and dashboard) ────────────
db = QuestDB()


# ── CLI ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Quest DB stats:", db.stats())
    print("\nTracked quests:")
    for title in db.all_quest_titles():
        chain = db.quest_chain_summary(title)
        active = db.active_step_for(title)
        print(f"\n  [{title}]  ({len(chain)} completed steps)")
        for s in chain:
            mins = s["duration_s"] / 60 if s["duration_s"] else 0
            print(f"    ✅ [{s['step_type']:10s}] {s['step_text'][:60]}  "
                  f"({mins:.1f}m, {s['click_count']} clicks)")
        if active:
            print(f"    ⏳ [{active.step_type:10s}] {active.step_text[:60]}  "
                  f"(seen {active.times_seen}×)")
