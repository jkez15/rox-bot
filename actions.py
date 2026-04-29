"""
actions.py – Mouse and keyboard actions targeted at the RoX window.

Mouse events use macOS Quartz CGEvents so the physical cursor is NOT moved.
Keyboard events still use pyautogui (which does not affect the cursor).
All click coordinates are in SCREEN space (translated from window-relative).
"""

import time
import Quartz
import pyautogui
from config import APP_WINDOW_NAME

# Disable pyautogui's built-in fail-safe pause (keyboard only)
pyautogui.PAUSE = 0.05


def window_to_screen(wx: int, wy: int, bounds: dict) -> tuple[int, int]:
    """
    Convert a coordinate relative to the window's top-left corner
    into absolute screen coordinates.
    """
    return bounds["X"] + wx, bounds["Y"] + wy


def _post_click(sx: float, sy: float) -> None:
    """Send a mouse-down then mouse-up at absolute screen coords via CGEvents."""
    point = Quartz.CGPointMake(sx, sy)

    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    time.sleep(0.05)

    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


def click(wx: int, wy: int, bounds: dict, duration: float = 0.1) -> None:
    """Click at window-relative (wx, wy) without moving the real cursor."""
    sx, sy = window_to_screen(wx, wy, bounds)
    _post_click(sx, sy)
    print(f"[Actions] Clicked  window({wx},{wy})  →  screen({sx},{sy})")


def double_click(wx: int, wy: int, bounds: dict, duration: float = 0.1) -> None:
    """Double-click at window-relative position without moving the real cursor."""
    sx, sy = window_to_screen(wx, wy, bounds)
    point = Quartz.CGPointMake(sx, sy)

    # First click
    down1 = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down1)
    up1 = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up1)

    time.sleep(0.05)

    # Second click (click count = 2)
    down2 = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventSetIntegerValueField(down2, Quartz.kCGMouseEventClickState, 2)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down2)

    up2 = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, point, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventSetIntegerValueField(up2, Quartz.kCGMouseEventClickState, 2)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up2)

    print(f"[Actions] DoubleClicked  window({wx},{wy})  →  screen({sx},{sy})")


def drag(
    wx1: int, wy1: int, wx2: int, wy2: int, bounds: dict, duration: float = 0.5
) -> None:
    """Click-drag from (wx1,wy1) to (wx2,wy2) without moving the real cursor."""
    sx1, sy1 = window_to_screen(wx1, wy1, bounds)
    sx2, sy2 = window_to_screen(wx2, wy2, bounds)

    p1 = Quartz.CGPointMake(sx1, sy1)
    p2 = Quartz.CGPointMake(sx2, sy2)

    # Mouse down at start
    down = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseDown, p1, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)

    # Interpolate drag movement
    steps = max(int(duration / 0.02), 5)
    for i in range(1, steps + 1):
        t = i / steps
        cx = sx1 + (sx2 - sx1) * t
        cy = sy1 + (sy2 - sy1) * t
        pt = Quartz.CGPointMake(cx, cy)
        drag_evt = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDragged, pt, Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, drag_evt)
        time.sleep(duration / steps)

    # Mouse up at end
    up = Quartz.CGEventCreateMouseEvent(
        None, Quartz.kCGEventLeftMouseUp, p2, Quartz.kCGMouseButtonLeft
    )
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)

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
