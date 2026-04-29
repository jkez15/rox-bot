"""
main.py – RöX Automation Bot entry point.

Architecture
------------
  Main thread   → Tkinter dashboard (ui_dashboard.py)
  Worker thread → automation loop (detect → OCR → click)

The worker thread is started immediately but blocks on
Dashboard.wait_for_start() until the user presses ▶ Start.
This keeps the UI responsive at all times.

Usage
-----
  source .venv/bin/activate
  python main.py
"""

import sys
import time
import threading

from config import POLL_INTERVAL, LOOP_INTERVAL, QUEST_CLICK_INTERVAL
from detector import is_rox_running
from quests import do_quest_scan
from ui_dashboard import Dashboard


# ── Worker thread ─────────────────────────────────────────────────────────────

def automation_loop(dash: Dashboard) -> None:
    """
    Runs on a background daemon thread.

    1. Waits (blocking) until the user clicks ▶ Start in the dashboard.
    2. Waits for RöX to be running.
    3. Runs one OCR pass per cycle:
       - reads quest text
       - clicks the NPC in the world, or falls back to the quest row
       - updates the dashboard with quest info and action log
    4. Respects Pause / Stop at every iteration.
    """
    dash.log("Bot ready — press ▶ Start when you're in RöX")
    dash.set_status("idle", "Press ▶ Start to begin")

    # ── Gate: wait for Start button ───────────────────────────────────────────
    if not dash.wait_for_start():
        return   # Stop was pressed before Start

    dash.log("▶ Bot started")

    # ── Main loop ─────────────────────────────────────────────────────────────
    while not dash.is_stop_requested():

        # Phase 1 — wait for RöX process
        if not is_rox_running():
            dash.set_status("waiting", "Waiting for RöX to launch…")
            dash.set_action("Polling for RöX process…")
            dash.log("RöX not running — waiting…")

            while not is_rox_running():
                if dash.is_stop_requested():
                    return
                time.sleep(POLL_INTERVAL)

        # Phase 2 — RöX is running
        dash.mark_started()
        dash.set_status("running", "RöX detected — automation active")
        dash.log("✅ RöX detected")

        last_click_t = 0.0

        while is_rox_running() and not dash.is_stop_requested():

            # Respect pause
            if dash.is_paused():
                dash.set_status("paused", "Paused — press Resume to continue")
                dash.set_action("Paused")
                time.sleep(0.5)
                continue

            dash.increment_cycle()

            now = time.time()
            if now - last_click_t >= QUEST_CLICK_INTERVAL:

                def _status(msg: str) -> None:
                    dash.set_action(msg)
                    dash.log(msg)

                quest_info = None
                clicked    = False

                # ── Quest automation (gated by checklist) ─────────────────
                if dash.is_task_enabled("quests"):
                    try:
                        quest_info, clicked = do_quest_scan(status_cb=_status)
                    except Exception as exc:
                        dash.log(f"⚠️  Error in quest scan: {exc}")
                else:
                    dash.set_action("Quests disabled — skipping")

                # ── Future tasks — add implementations here ───────────────
                # if dash.is_task_enabled("daily_rewards"):
                #     do_daily_rewards(status_cb=_status)
                #
                # if dash.is_task_enabled("auto_potion"):
                #     do_auto_potion(status_cb=_status)
                #
                # if dash.is_task_enabled("party_accept"):
                #     do_party_accept(status_cb=_status)
                #
                # if dash.is_task_enabled("farming"):
                #     do_farming(status_cb=_status)

                # Push quest info to dashboard
                dash.set_quest(quest_info)

                if quest_info:
                    qtype = quest_info.get("type", "?")
                    title = quest_info.get("title", "")
                    dist  = quest_info.get("distance", "")
                    dash.set_status(
                        "running",
                        f"[{qtype}] {title}" + (f"  |  {dist}" if dist else "")
                    )

                if clicked:
                    dash.increment_quests()
                    last_click_t = time.time()
                else:
                    dash.set_status("running", "Monitoring quest panel…")

            else:
                remaining = int(QUEST_CLICK_INTERVAL - (now - last_click_t))
                dash.set_action(f"⏳ Next scan in {remaining}s…")

            time.sleep(LOOP_INTERVAL)

        if not dash.is_stop_requested():
            dash.set_status("waiting", "RöX closed — waiting for restart…")
            dash.log("RöX was closed. Waiting for it to reopen…")

    dash.set_status("stopped", "Bot stopped")
    dash.log("🛑 Bot stopped.")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    dash = Dashboard()

    # Worker thread starts immediately but blocks until Start is clicked
    worker = threading.Thread(
        target=automation_loop,
        args=(dash,),
        daemon=True,
        name="rox-worker"
    )
    worker.start()

    # Dashboard.build() runs Tkinter mainloop on the main thread (blocks)
    dash.build()

    sys.exit(0)


if __name__ == "__main__":
    main()
