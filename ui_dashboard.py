"""
ui_dashboard.py – Floating status dashboard for the RöX bot.

Layout  (compact, always-on-top)
------
  • Header bar (accent colour)
  • Status card  — dot + status text + current action
  • Quest card   — active quest type, title, target, distance
  • Task checklist — toggle individual automation features
  • Stats row    — Cycles / Quests clicked / Elapsed
  • Activity log — scrollable timestamped entries
  • Button row   — Start → (Pause/Resume) + Stop

Threading
---------
  Tkinter runs on the MAIN thread.
  The automation worker runs on a DAEMON thread.
  All cross-thread state goes through threading.Lock().
  Never touch Tkinter widgets from the worker thread.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from collections import deque
from threading import Lock, Event
import time


# ── Constants ────────────────────────────────────────────────────────────────
LOG_MAX_LINES = 100
REFRESH_MS    = 400          # UI refresh rate

COLOUR_RUNNING = "#2ecc71"
COLOUR_PAUSED  = "#f39c12"
COLOUR_WAITING = "#3498db"
COLOUR_STOPPED = "#e74c3c"
COLOUR_BG      = "#1a1a2e"
COLOUR_PANEL   = "#16213e"
COLOUR_TEXT    = "#eaeaea"
COLOUR_DIM     = "#7f8c8d"
COLOUR_ACCENT  = "#e94560"
COLOUR_START   = "#27ae60"

# Automation tasks: (internal_name, display_label, enabled_by_default)
AUTOMATION_TASKS: list[tuple[str, str, bool]] = [
    ("quests",        "Quests",         True),
    ("daily_rewards", "Daily Rewards",  False),
    ("auto_potion",   "Auto-Potion",    False),
    ("party_accept",  "Party Accept",   False),
    ("farming",       "Farming",        False),
]


class Dashboard:
    """
    Thread-safe dashboard.

    State machine
    -------------
      idle    → Start clicked  → running
      running → Pause clicked  → paused
      paused  → Resume clicked → running
      any     → Stop clicked   → stopped
    """

    def __init__(self) -> None:
        self._lock = Lock()

        # Bot state
        self._status       = "idle"
        self._status_text  = "Press ▶ Start to begin"
        self._action       = "—"
        self._log: deque[str] = deque(maxlen=LOG_MAX_LINES)

        # Counters
        self._cycles  = 0
        self._quests  = 0
        self._start_t: float | None = None

        # Control flags
        self._started         = False   # set by Start button
        self._paused          = False
        self._stop_requested  = False

        # Event that the worker can block on while waiting for Start
        self._start_event = Event()

        # Active quest info (set by worker, read by UI)
        self._quest: dict | None = None

        # Task enable/disable states (synced from UI checkboxes each refresh)
        self._task_states: dict[str, bool] = {
            name: default for name, _, default in AUTOMATION_TASKS
        }

        self._root: tk.Tk | None = None

    # ── Thread-safe API (called from worker thread) ──────────────────────────

    def wait_for_start(self) -> bool:
        """Block the worker thread until Start is clicked or Stop is requested."""
        self._start_event.wait()
        with self._lock:
            return not self._stop_requested

    def set_status(self, status: str, text: str) -> None:
        with self._lock:
            self._status      = status
            self._status_text = text

    def set_action(self, text: str) -> None:
        with self._lock:
            self._action = text

    def set_quest(self, quest: dict | None) -> None:
        with self._lock:
            self._quest = quest

    def log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._log.append(f"[{ts}]  {message}")

    def increment_cycle(self) -> None:
        with self._lock:
            self._cycles += 1

    def increment_quests(self) -> None:
        with self._lock:
            self._quests += 1

    def mark_started(self) -> None:
        with self._lock:
            self._start_t = time.time()

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def is_stop_requested(self) -> bool:
        with self._lock:
            return self._stop_requested

    def is_task_enabled(self, task_name: str) -> bool:
        """Check whether a named automation task is enabled (thread-safe)."""
        with self._lock:
            return self._task_states.get(task_name, False)

    # ── Tkinter UI (main thread only) ────────────────────────────────────────

    def build(self) -> None:
        """Build the window and enter Tkinter mainloop (blocks until closed)."""
        root = tk.Tk()
        self._root = root
        root.title("RöX Bot")
        root.configure(bg=COLOUR_BG)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.geometry("370x560+40+60")

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=COLOUR_ACCENT, pady=4)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="⚔  RöX Automation Bot",
            font=("SF Pro Display", 13, "bold"),
            fg="white", bg=COLOUR_ACCENT
        ).pack()

        # ── Status card ───────────────────────────────────────────────────
        card = tk.Frame(root, bg=COLOUR_PANEL, padx=10, pady=6)
        card.pack(fill="x", padx=8, pady=(6, 0))

        row1 = tk.Frame(card, bg=COLOUR_PANEL)
        row1.pack(fill="x")
        tk.Label(row1, text="STATUS", font=("SF Pro Text", 8, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL).pack(side="left")
        self._status_dot = tk.Label(row1, text="●", font=("SF Pro Text", 12),
                                    fg=COLOUR_WAITING, bg=COLOUR_PANEL)
        self._status_dot.pack(side="right")

        self._status_lbl = tk.Label(
            card, text="Press ▶ Start to begin",
            font=("SF Pro Text", 10), fg=COLOUR_TEXT, bg=COLOUR_PANEL,
            anchor="w", wraplength=320
        )
        self._status_lbl.pack(fill="x", pady=(1, 4))

        ttk.Separator(card, orient="horizontal").pack(fill="x", pady=2)

        tk.Label(card, text="CURRENT ACTION", font=("SF Pro Text", 8, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL, anchor="w").pack(fill="x")
        self._action_lbl = tk.Label(
            card, text="—",
            font=("SF Pro Text", 9, "italic"), fg="#a8d8ea", bg=COLOUR_PANEL,
            anchor="w", wraplength=320
        )
        self._action_lbl.pack(fill="x", pady=(1, 0))

        # ── Quest info card ───────────────────────────────────────────────
        qcard = tk.Frame(root, bg=COLOUR_PANEL, padx=10, pady=6)
        qcard.pack(fill="x", padx=8, pady=(4, 0))

        tk.Label(qcard, text="ACTIVE QUEST", font=("SF Pro Text", 8, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL, anchor="w").pack(fill="x")

        self._quest_type_lbl = tk.Label(
            qcard, text="—",
            font=("SF Pro Text", 9, "bold"), fg=COLOUR_RUNNING, bg=COLOUR_PANEL,
            anchor="w"
        )
        self._quest_type_lbl.pack(fill="x")

        self._quest_title_lbl = tk.Label(
            qcard, text="",
            font=("SF Pro Text", 9), fg=COLOUR_TEXT, bg=COLOUR_PANEL,
            anchor="w", wraplength=320
        )
        self._quest_title_lbl.pack(fill="x")

        self._quest_target_lbl = tk.Label(
            qcard, text="",
            font=("SF Pro Text", 8, "italic"), fg="#a8d8ea", bg=COLOUR_PANEL,
            anchor="w", wraplength=320
        )
        self._quest_target_lbl.pack(fill="x")

        self._quest_dist_lbl = tk.Label(
            qcard, text="",
            font=("SF Pro Text", 8), fg=COLOUR_DIM, bg=COLOUR_PANEL,
            anchor="w"
        )
        self._quest_dist_lbl.pack(fill="x")

        # ── Task checklist ────────────────────────────────────────────────
        tcard = tk.Frame(root, bg=COLOUR_PANEL, padx=10, pady=6)
        tcard.pack(fill="x", padx=8, pady=(4, 0))

        tk.Label(tcard, text="TASKS", font=("SF Pro Text", 8, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL, anchor="w").pack(fill="x")

        # Two-column grid of checkboxes
        grid = tk.Frame(tcard, bg=COLOUR_PANEL)
        grid.pack(fill="x", pady=(2, 0))

        self._task_vars: dict[str, tk.BooleanVar] = {}
        for idx, (name, label, default) in enumerate(AUTOMATION_TASKS):
            var = tk.BooleanVar(value=default)
            self._task_vars[name] = var
            row, col = divmod(idx, 2)
            cb = tk.Checkbutton(
                grid, text=label, variable=var,
                bg=COLOUR_PANEL, fg=COLOUR_TEXT, selectcolor=COLOUR_BG,
                activebackground=COLOUR_PANEL, activeforeground=COLOUR_TEXT,
                font=("SF Pro Text", 9), anchor="w",
            )
            cb.grid(row=row, column=col, sticky="w", padx=(0, 10))

        # ── Stats row ─────────────────────────────────────────────────────
        stats = tk.Frame(root, bg=COLOUR_PANEL, padx=10, pady=6)
        stats.pack(fill="x", padx=8, pady=(4, 0))

        def stat_block(parent, title):
            f = tk.Frame(parent, bg=COLOUR_PANEL)
            f.pack(side="left", expand=True)
            tk.Label(f, text=title, font=("SF Pro Text", 7, "bold"),
                     fg=COLOUR_DIM, bg=COLOUR_PANEL).pack()
            val = tk.Label(f, text="0", font=("SF Pro Text", 14, "bold"),
                           fg=COLOUR_TEXT, bg=COLOUR_PANEL)
            val.pack()
            return val

        self._cycles_val  = stat_block(stats, "CYCLES")
        self._quests_val  = stat_block(stats, "QUESTS CLICKED")
        self._elapsed_val = stat_block(stats, "ELAPSED")

        # ── Activity log ──────────────────────────────────────────────────
        log_frame = tk.Frame(root, bg=COLOUR_BG, padx=8, pady=4)
        log_frame.pack(fill="both", expand=True, pady=(4, 0))
        tk.Label(log_frame, text="ACTIVITY LOG", font=("SF Pro Text", 8, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_BG, anchor="w").pack(fill="x")

        txt_frame = tk.Frame(log_frame, bg=COLOUR_PANEL)
        txt_frame.pack(fill="both", expand=True, pady=(2, 0))
        self._log_box = tk.Text(
            txt_frame, height=6, bg=COLOUR_PANEL, fg=COLOUR_TEXT,
            font=("Menlo", 8), relief="flat", state="disabled",
            wrap="word", padx=4, pady=3
        )
        sb = tk.Scrollbar(txt_frame, command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self._log_box.pack(side="left", fill="both", expand=True)

        # ── Button row ────────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=COLOUR_BG, padx=8, pady=6)
        btn_frame.pack(fill="x")

        btn_cfg = dict(font=("SF Pro Text", 11, "bold"), relief="flat",
                       padx=10, pady=5, cursor="hand2", bd=0)

        # Start button (visible initially)
        self._start_btn = tk.Button(
            btn_frame, text="▶  Start", bg=COLOUR_START, fg="white",
            command=self._on_start, **btn_cfg
        )
        self._start_btn.pack(fill="x", pady=(0, 4))

        # Pause + Stop (hidden until started)
        self._lower_frame = tk.Frame(btn_frame, bg=COLOUR_BG)

        self._pause_btn = tk.Button(
            self._lower_frame, text="⏸  Pause", bg="#f39c12", fg="white",
            command=self._toggle_pause, **btn_cfg
        )
        self._pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        tk.Button(
            self._lower_frame, text="⏹  Stop", bg=COLOUR_ACCENT, fg="white",
            command=self._request_stop, **btn_cfg
        ).pack(side="left", expand=True, fill="x")

        # ── Kick off refresh loop ─────────────────────────────────────────
        root.after(REFRESH_MS, self._refresh)
        root.protocol("WM_DELETE_WINDOW", self._request_stop)
        root.mainloop()

    # ── Button callbacks (main thread) ───────────────────────────────────────

    def _on_start(self) -> None:
        with self._lock:
            if self._started or self._stop_requested:
                return
            self._started     = True
            self._status      = "running"
            self._status_text = "RöX automation started"
            self._start_t     = time.time()
            self._log.append(
                f"[{datetime.now().strftime('%H:%M:%S')}]  ▶ Bot started by user"
            )
        # Signal the waiting worker thread
        self._start_event.set()

        # Swap buttons: hide Start, reveal Pause+Stop
        self._start_btn.pack_forget()
        self._lower_frame.pack(fill="x")

    def _toggle_pause(self) -> None:
        with self._lock:
            self._paused = not self._paused
            if self._paused:
                self._status      = "paused"
                self._status_text = "Paused — press Resume to continue"
            else:
                self._status      = "running"
                self._status_text = "Resuming…"
        self._update_pause_btn()

    def _update_pause_btn(self) -> None:
        with self._lock:
            paused = self._paused
        if paused:
            self._pause_btn.config(text="▶  Resume", bg=COLOUR_RUNNING)
        else:
            self._pause_btn.config(text="⏸  Pause", bg="#f39c12")

    def _request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            self._status         = "stopped"
            self._status_text    = "Stopped"
        # Unblock the worker if it's still waiting on Start
        self._start_event.set()
        if self._root:
            self._root.after(600, self._root.destroy)

    # ── Refresh (main thread, called by root.after) ──────────────────────────

    def _refresh(self) -> None:
        # Sync checkbox states to the thread-safe dict
        if hasattr(self, '_task_vars'):
            with self._lock:
                for name, var in self._task_vars.items():
                    self._task_states[name] = var.get()

        with self._lock:
            status      = self._status
            status_text = self._status_text
            action      = self._action
            cycles      = self._cycles
            quests      = self._quests
            log_lines   = list(self._log)
            start_t     = self._start_t
            quest       = dict(self._quest) if self._quest else None

        # Status dot
        dot_map = {
            "running": COLOUR_RUNNING,
            "paused":  COLOUR_PAUSED,
            "waiting": COLOUR_WAITING,
            "stopped": COLOUR_STOPPED,
            "idle":    COLOUR_DIM,
        }
        self._status_dot.config(fg=dot_map.get(status, COLOUR_DIM))
        self._status_lbl.config(text=status_text)
        self._action_lbl.config(text=action)

        # Quest card
        if quest:
            self._quest_type_lbl.config(
                text=f"[{quest.get('type', '?')}]",
                fg=COLOUR_RUNNING if quest.get("type") == "Main" else "#3498db"
            )
            self._quest_title_lbl.config(text=quest.get("title", ""))
            tgt = quest.get("target")
            self._quest_target_lbl.config(
                text=f"🎯 Target: {tgt}" if tgt else ""
            )
            dist = quest.get("distance")
            self._quest_dist_lbl.config(
                text=dist if dist else ""
            )
        else:
            self._quest_type_lbl.config(text="—", fg=COLOUR_DIM)
            self._quest_title_lbl.config(text="")
            self._quest_target_lbl.config(text="")
            self._quest_dist_lbl.config(text="")

        # Stats
        self._cycles_val.config(text=str(cycles))
        self._quests_val.config(text=str(quests))
        if start_t:
            secs    = int(time.time() - start_t)
            h, rem  = divmod(secs, 3600)
            m, s    = divmod(rem, 60)
            elapsed = f"{h:02d}:{m:02d}:{s:02d}"
        else:
            elapsed = "—"
        self._elapsed_val.config(text=elapsed)

        # Log box
        new_text = "\n".join(log_lines)
        self._log_box.config(state="normal")
        if self._log_box.get("1.0", "end-1c") != new_text:
            self._log_box.delete("1.0", "end")
            self._log_box.insert("end", new_text)
            self._log_box.see("end")
        self._log_box.config(state="disabled")

        if self._root and not self._stop_requested:
            self._root.after(REFRESH_MS, self._refresh)
