"""
ui_dashboard.py – Floating status dashboard for the RöX bot.

A compact always-on-top Tkinter window that shows:
  • Bot status (running / paused / waiting)
  • Current action being performed
  • Live quest log (last N lines)
  • Start / Pause / Stop buttons
  • Elapsed runtime and cycle counter
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from datetime import datetime, timedelta
from collections import deque
from threading import Lock
import time


# ── Constants ───────────────────────────────────────────────────────────────
LOG_MAX_LINES = 80
REFRESH_MS = 500          # dashboard refresh rate in milliseconds

# Status colours
COLOUR_RUNNING  = "#2ecc71"   # green
COLOUR_PAUSED   = "#f39c12"   # amber
COLOUR_WAITING  = "#3498db"   # blue
COLOUR_STOPPED  = "#e74c3c"   # red
COLOUR_BG       = "#1a1a2e"   # dark navy
COLOUR_PANEL    = "#16213e"
COLOUR_TEXT     = "#eaeaea"
COLOUR_DIM      = "#7f8c8d"
COLOUR_ACCENT   = "#e94560"


class Dashboard:
    """
    Thread-safe status dashboard.  The automation thread calls the
    public `update_*` methods; Tkinter runs on the main thread.
    """

    def __init__(self) -> None:
        self._lock = Lock()
        self._status = "waiting"           # waiting | running | paused | stopped
        self._status_text = "Waiting for RöX to start…"
        self._current_action = "—"
        self._log: deque[str] = deque(maxlen=LOG_MAX_LINES)
        self._cycles = 0
        self._quests_clicked = 0
        self._start_time: float | None = None
        self._paused = False
        self._stop_requested = False

        self._root: tk.Tk | None = None

    # ── Public thread-safe API ───────────────────────────────────────────────

    def set_status(self, status: str, text: str) -> None:
        """status: 'waiting' | 'running' | 'paused' | 'stopped'"""
        with self._lock:
            self._status = status
            self._status_text = text

    def set_action(self, text: str) -> None:
        with self._lock:
            self._current_action = text

    def log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        with self._lock:
            self._log.append(f"[{ts}]  {message}")

    def increment_cycle(self) -> None:
        with self._lock:
            self._cycles += 1

    def increment_quests(self) -> None:
        with self._lock:
            self._quests_clicked += 1

    def mark_started(self) -> None:
        with self._lock:
            self._start_time = time.time()
            self._paused = False

    def is_paused(self) -> bool:
        with self._lock:
            return self._paused

    def is_stop_requested(self) -> bool:
        with self._lock:
            return self._stop_requested

    # ── Tkinter UI (run on main thread) ─────────────────────────────────────

    def build(self) -> None:
        """Build and start the Tkinter window (blocks until closed)."""
        root = tk.Tk()
        self._root = root
        root.title("RöX Bot")
        root.configure(bg=COLOUR_BG)
        root.attributes("-topmost", True)
        root.resizable(False, False)
        root.geometry("420x540+40+60")

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(root, bg=COLOUR_ACCENT, pady=6)
        hdr.pack(fill="x")
        tk.Label(
            hdr, text="⚔  RöX Automation Bot",
            font=("SF Pro Display", 15, "bold"),
            fg="white", bg=COLOUR_ACCENT
        ).pack()

        # ── Status card ───────────────────────────────────────────────────
        card = tk.Frame(root, bg=COLOUR_PANEL, padx=14, pady=10)
        card.pack(fill="x", padx=10, pady=(10, 0))

        row1 = tk.Frame(card, bg=COLOUR_PANEL)
        row1.pack(fill="x")
        tk.Label(row1, text="STATUS", font=("SF Pro Text", 9, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL).pack(side="left")
        self._status_dot = tk.Label(row1, text="●", font=("SF Pro Text", 14),
                                    fg=COLOUR_WAITING, bg=COLOUR_PANEL)
        self._status_dot.pack(side="right")

        self._status_label = tk.Label(
            card, text="Waiting for RöX…",
            font=("SF Pro Text", 11), fg=COLOUR_TEXT, bg=COLOUR_PANEL,
            anchor="w", wraplength=370
        )
        self._status_label.pack(fill="x", pady=(2, 6))

        ttk.Separator(card, orient="horizontal").pack(fill="x", pady=4)

        tk.Label(card, text="CURRENT ACTION", font=("SF Pro Text", 9, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_PANEL, anchor="w").pack(fill="x")
        self._action_label = tk.Label(
            card, text="—",
            font=("SF Pro Text", 10, "italic"), fg="#a8d8ea", bg=COLOUR_PANEL,
            anchor="w", wraplength=370
        )
        self._action_label.pack(fill="x", pady=(2, 0))

        # ── Stats row ─────────────────────────────────────────────────────
        stats = tk.Frame(root, bg=COLOUR_PANEL, padx=14, pady=8)
        stats.pack(fill="x", padx=10, pady=(6, 0))

        def stat_block(parent, title):
            f = tk.Frame(parent, bg=COLOUR_PANEL)
            f.pack(side="left", expand=True)
            tk.Label(f, text=title, font=("SF Pro Text", 8, "bold"),
                     fg=COLOUR_DIM, bg=COLOUR_PANEL).pack()
            val = tk.Label(f, text="0", font=("SF Pro Text", 18, "bold"),
                           fg=COLOUR_TEXT, bg=COLOUR_PANEL)
            val.pack()
            return val

        self._cycles_val  = stat_block(stats, "CYCLES")
        self._quests_val  = stat_block(stats, "QUESTS CLICKED")
        self._elapsed_val = stat_block(stats, "ELAPSED")

        # ── Log ───────────────────────────────────────────────────────────
        log_frame = tk.Frame(root, bg=COLOUR_BG, padx=10, pady=6)
        log_frame.pack(fill="both", expand=True, pady=(8, 0))
        tk.Label(log_frame, text="ACTIVITY LOG", font=("SF Pro Text", 9, "bold"),
                 fg=COLOUR_DIM, bg=COLOUR_BG, anchor="w").pack(fill="x")

        txt_frame = tk.Frame(log_frame, bg=COLOUR_PANEL)
        txt_frame.pack(fill="both", expand=True, pady=(4, 0))
        self._log_box = tk.Text(
            txt_frame, height=10, bg=COLOUR_PANEL, fg=COLOUR_TEXT,
            font=("Menlo", 9), relief="flat", state="disabled",
            wrap="word", padx=6, pady=4
        )
        scrollbar = tk.Scrollbar(txt_frame, command=self._log_box.yview)
        self._log_box.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        self._log_box.pack(side="left", fill="both", expand=True)

        # ── Buttons ───────────────────────────────────────────────────────
        btn_frame = tk.Frame(root, bg=COLOUR_BG, padx=10, pady=8)
        btn_frame.pack(fill="x")

        btn_cfg = dict(font=("SF Pro Text", 11, "bold"), relief="flat",
                       padx=12, pady=6, cursor="hand2", bd=0)

        self._pause_btn = tk.Button(
            btn_frame, text="⏸  Pause", bg="#f39c12", fg="white",
            command=self._toggle_pause, **btn_cfg
        )
        self._pause_btn.pack(side="left", expand=True, fill="x", padx=(0, 4))

        tk.Button(
            btn_frame, text="⏹  Stop", bg=COLOUR_ACCENT, fg="white",
            command=self._request_stop, **btn_cfg
        ).pack(side="left", expand=True, fill="x")

        # ── Start refresh loop ────────────────────────────────────────────
        root.after(REFRESH_MS, self._refresh)
        root.protocol("WM_DELETE_WINDOW", self._request_stop)
        root.mainloop()

    # ── Internal ────────────────────────────────────────────────────────────

    def _toggle_pause(self) -> None:
        with self._lock:
            self._paused = not self._paused
            if self._paused:
                self._status = "paused"
                self._status_text = "Paused by user"
            else:
                self._status = "running"
                self._status_text = "Resuming automation…"
        self._update_pause_button()

    def _update_pause_button(self) -> None:
        with self._lock:
            paused = self._paused
        if paused:
            self._pause_btn.config(text="▶  Resume", bg=COLOUR_RUNNING)
        else:
            self._pause_btn.config(text="⏸  Pause", bg="#f39c12")

    def _request_stop(self) -> None:
        with self._lock:
            self._stop_requested = True
            self._status = "stopped"
            self._status_text = "Stopped"
        if self._root:
            self._root.after(600, self._root.destroy)

    def _refresh(self) -> None:
        """Called on the Tkinter thread every REFRESH_MS ms to pull latest state."""
        with self._lock:
            status       = self._status
            status_text  = self._status_text
            action       = self._current_action
            cycles       = self._cycles
            quests       = self._quests_clicked
            log_lines    = list(self._log)
            start        = self._start_time

        # Status dot colour
        colour_map = {
            "running": COLOUR_RUNNING,
            "paused":  COLOUR_PAUSED,
            "waiting": COLOUR_WAITING,
            "stopped": COLOUR_STOPPED,
        }
        dot_colour = colour_map.get(status, COLOUR_DIM)
        self._status_dot.config(fg=dot_colour)
        self._status_label.config(text=status_text)
        self._action_label.config(text=action)

        # Stats
        self._cycles_val.config(text=str(cycles))
        self._quests_val.config(text=str(quests))
        elapsed = "—"
        if start:
            delta = timedelta(seconds=int(time.time() - start))
            h, rem = divmod(int(delta.total_seconds()), 3600)
            m, s = divmod(rem, 60)
            elapsed = f"{h:02d}:{m:02d}:{s:02d}"
        self._elapsed_val.config(text=elapsed)

        # Log box — only update if content changed
        new_text = "\n".join(log_lines)
        self._log_box.config(state="normal")
        current = self._log_box.get("1.0", "end-1c")
        if current != new_text:
            self._log_box.delete("1.0", "end")
            self._log_box.insert("end", new_text)
            self._log_box.see("end")
        self._log_box.config(state="disabled")

        if self._root:
            self._root.after(REFRESH_MS, self._refresh)
