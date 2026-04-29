"""
detector.py – Detects whether the RoX (RX) application is currently running
and retrieves its process info using psutil.
"""

import psutil
from config import APP_PROCESS_NAME


def get_rox_process() -> psutil.Process | None:
    """
    Return the psutil.Process object for RoX if it is running, else None.
    Matches against APP_PROCESS_NAME (case-insensitive).
    """
    for proc in psutil.process_iter(["pid", "name", "status"]):
        try:
            if APP_PROCESS_NAME.lower() in proc.info["name"].lower():
                return proc
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return None


def is_rox_running() -> bool:
    """Return True if the RoX process is currently active."""
    return get_rox_process() is not None


def wait_for_rox(poll_interval: float = 3.0) -> psutil.Process:
    """
    Block until RoX starts, polling every `poll_interval` seconds.
    Returns the Process object once found.
    """
    import time

    print(f"[Detector] Waiting for '{APP_PROCESS_NAME}' to start...")
    while True:
        proc = get_rox_process()
        if proc:
            print(f"[Detector] ✅ Found '{APP_PROCESS_NAME}' — PID {proc.pid}")
            return proc
        time.sleep(poll_interval)
