"""
main.py – RöX Automation Bot entry point.

Architecture:
  • Main thread   → Tkinter dashboard UI
  • Worker thread → detection + capture + quest automation loop

Usage:
    source .venv/bin/activate
    python main.py
"""

import sys
import time
import threading

from config import POLL_INTERVAL, LOOP_INTERVAL, QUEST_CLICK_INTERVAL
from detector import is_rox_running
from actions import focus_rox
from quests import run_quest_cycle, get_quest_info
from ui_dashboard import Dashboard


# ── Worker thread ────────────────────────────────────────────────────────────

def automation_loop(dash: Dashboard) -> None:
    """
    Runs on a background thread.
    Waits for RöX → runs quest automation → loops until stopped.
    """
    dash.log("Bot started — looking for RöX…")

    while not dash.is_stop_requested():

        # ── Phase 1: wait for RöX ────────────────────────────────────────
        if not is_rox_running():
            dash.set_status("waiting", "Waiting for RöX to start…")
            dash.set_action("Polling for RöX process…")
            dash.log("RöX not running — waiting…")
            while not is_rox_running():
                if dash.is_stop_requested():
                    return
                time.sleep(POLL_INTERVAL)

        # ── Phase 2: RöX is open ─────────────────────────────────────────
        dash.mark_started()
        dash.set_status("running", "RöX detected — automation active")
        dash.log("✅ RöX detected! Starting automation.")
        focus_rox()
        time.sleep(0.5)

        last_quest_click = 0.0

        while is_rox_running() and not dash.is_stop_requested():

            # Respect pause
            if dash.is_paused():
                dash.set_status("paused", "Paused — press Resume to continue")
                dash.set_action("Paused")
                time.sleep(0.5)
                continue

            dash.increment_cycle()

            # ── Quest info for dashboard ─────────────────────────────────
            quest = get_quest_info()
            if quest:
                dash.set_status(
                    "running",
                    f"[{quest['type']}] {quest['title']}"
                    + (f"  |  {quest['distance']}" if quest.get("distance") else "")
                )

            # ── Quest automation ─────────────────────────────────────────
            now = time.time()
            if now - last_quest_click >= QUEST_CLICK_INTERVAL:

                def status_cb(msg: str) -> None:
                    dash.set_action(msg)
                    dash.log(msg)

                try:
                    clicked = run_quest_cycle(status_cb=status_cb)
                except Exception as exc:
                    dash.log(f"⚠️  Error: {exc}")
                    clicked = False

                if clicked:
                    dash.increment_quests()
                    last_quest_click = time.time()
                    dash.set_status("running", "Quest clicked — waiting for character to move…")
                else:
                    dash.set_status("running", "RöX active — monitoring quest panel…")
            else:
                remaining = int(QUEST_CLICK_INTERVAL - (now - last_quest_click))
                dash.set_action(f"⏳ Next quest click in {remaining}s…")

            time.sleep(LOOP_INTERVAL)

        if not dash.is_stop_requested():
            dash.set_status("waiting", "RöX closed — waiting for restart…")
            dash.log("RöX was closed. Waiting for it to reopen…")

    dash.set_status("stopped", "Bot stopped")
    dash.log("Bot stopped by user.")


# ── Entry point ──────────────────────────────────────────────────────────────

def main() -> None:
    dash = Dashboard()

    worker = threading.Thread(target=automation_loop, args=(dash,), daemon=True)
    worker.start()

    # Dashboard.build() blocks on the main thread (Tkinter mainloop)
    dash.build()

    sys.exit(0)


if __name__ == "__main__":
    main()
