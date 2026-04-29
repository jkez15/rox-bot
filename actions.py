"""
actions.py – Mouse and keyboard actions targeted at the RoX window.
All click coordinates are in SCREEN space (translated from window-relative).
"""

import time
import pyautogui
from config import APP_WINDOW_NAME

# Disable pyautogui's built-in fail-safe pause
pyautogui.PAUSE = 0.05


def window_to_screen(wx: int, wy: int, bounds: dict) -> tuple[int, int]:
    """
    Convert a coordinate relative to the window's top-left corner
    into absolute screen coordinates.
    """
    return bounds["X"] + wx, bounds["Y"] + wy


def click(wx: int, wy: int, bounds: dict, duration: float = 0.1) -> None:
    """Click at window-relative (wx, wy) position."""
    sx, sy = window_to_screen(wx, wy, bounds)
    pyautogui.moveTo(sx, sy, duration=duration)
    pyautogui.click()
    print(f"[Actions] Clicked  window({wx},{wy})  →  screen({sx},{sy})")


def double_click(wx: int, wy: int, bounds: dict, duration: float = 0.1) -> None:
    """Double-click at window-relative position."""
    sx, sy = window_to_screen(wx, wy, bounds)
    pyautogui.moveTo(sx, sy, duration=duration)
    pyautogui.doubleClick()
    print(f"[Actions] DoubleClicked  window({wx},{wy})  →  screen({sx},{sy})")


def drag(
    wx1: int, wy1: int, wx2: int, wy2: int, bounds: dict, duration: float = 0.5
) -> None:
    """Click-drag from (wx1,wy1) to (wx2,wy2) in window-relative coords."""
    sx1, sy1 = window_to_screen(wx1, wy1, bounds)
    sx2, sy2 = window_to_screen(wx2, wy2, bounds)
    pyautogui.moveTo(sx1, sy1, duration=0.1)
    pyautogui.dragTo(sx2, sy2, duration=duration, button="left")
    print(f"[Actions] Dragged  ({wx1},{wy1})→({wx2},{wy2})")


def type_text(text: str, interval: float = 0.05) -> None:
    """Type a string of text with a small delay between keystrokes."""
    pyautogui.typewrite(text, interval=interval)


def press_key(key: str) -> None:
    """Press a single key (e.g. 'enter', 'esc', 'space')."""
    pyautogui.press(key)


def focus_rox() -> None:
    """Bring the RoX window to the foreground using AppleScript."""
    import subprocess
    subprocess.run(
        ["osascript", "-e", f'tell application "{APP_WINDOW_NAME}" to activate'],
        capture_output=True,
    )
    time.sleep(0.3)
