"""
recognizer.py – Template matching against a captured PIL Image using OpenCV.
Place reference PNG templates in the templates/ folder.
"""

from __future__ import annotations

import os
import cv2
import numpy as np
from PIL import Image
from config import TEMPLATES_DIR, MATCH_THRESHOLD


def pil_to_cv(image: Image.Image) -> np.ndarray:
    """Convert a PIL RGB image to a BGR numpy array for OpenCV."""
    return cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)


def load_template(name: str) -> np.ndarray | None:
    """
    Load a template image from the templates/ folder by filename (with extension).
    Returns a BGR numpy array or None if the file doesn't exist.
    """
    path = os.path.join(TEMPLATES_DIR, name)
    if not os.path.exists(path):
        print(f"[Recognizer] ⚠️  Template not found: {path}")
        return None
    return cv2.imread(path)


def find_template(
    screenshot: Image.Image,
    template_name: str,
    threshold: float = MATCH_THRESHOLD,
) -> tuple[int, int, float] | None:
    """
    Search for a template image inside a screenshot using normalized cross-correlation.

    Returns (center_x, center_y, confidence) in window-relative pixels if found,
    or None if no match above the threshold.
    """
    template = load_template(template_name)
    if template is None:
        return None

    haystack = pil_to_cv(screenshot)
    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)

    if max_val >= threshold:
        th, tw = template.shape[:2]
        cx = max_loc[0] + tw // 2
        cy = max_loc[1] + th // 2
        print(
            f"[Recognizer] ✅ '{template_name}' found at ({cx},{cy})  conf={max_val:.2f}"
        )
        return cx, cy, max_val

    print(
        f"[Recognizer] ❌ '{template_name}' not found  (best conf={max_val:.2f} < {threshold})"
    )
    return None


def find_all_templates(
    screenshot: Image.Image,
    template_name: str,
    threshold: float = MATCH_THRESHOLD,
) -> list[tuple[int, int, float]]:
    """
    Find ALL occurrences of a template in the screenshot using NMS-style deduplication.
    Returns a list of (center_x, center_y, confidence) tuples.
    """
    template = load_template(template_name)
    if template is None:
        return []

    haystack = pil_to_cv(screenshot)
    result = cv2.matchTemplate(haystack, template, cv2.TM_CCOEFF_NORMED)
    th, tw = template.shape[:2]

    locations = np.where(result >= threshold)
    matches = []
    for pt in zip(*locations[::-1]):
        conf = float(result[pt[1], pt[0]])
        cx, cy = pt[0] + tw // 2, pt[1] + th // 2
        matches.append((cx, cy, conf))

    # Simple non-maximum suppression: merge nearby hits
    merged: list[tuple[int, int, float]] = []
    used = [False] * len(matches)
    for i, (cx, cy, conf) in enumerate(matches):
        if used[i]:
            continue
        group_x, group_y, group_conf = [cx], [cy], [conf]
        for j, (cx2, cy2, conf2) in enumerate(matches):
            if i != j and not used[j]:
                if abs(cx - cx2) < tw and abs(cy - cy2) < th:
                    group_x.append(cx2)
                    group_y.append(cy2)
                    group_conf.append(conf2)
                    used[j] = True
        merged.append(
            (int(np.mean(group_x)), int(np.mean(group_y)), float(np.max(group_conf)))
        )
        used[i] = True

    print(f"[Recognizer] Found {len(merged)} instance(s) of '{template_name}'")
    return merged


def annotate(
    screenshot: Image.Image, matches: dict[str, tuple[int, int, float] | None]
) -> Image.Image:
    """
    Draw circles on a copy of the screenshot for each matched template.
    `matches` is a dict of {template_name: (cx, cy, conf) or None}.
    Returns an annotated PIL Image.
    """
    img = pil_to_cv(screenshot).copy()
    for name, match in matches.items():
        if match:
            cx, cy, conf = match
            cv2.circle(img, (cx, cy), 20, (0, 255, 0), 2)
            cv2.putText(
                img,
                f"{name} {conf:.2f}",
                (cx - 20, cy - 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                1,
            )
    return Image.fromarray(cv2.cvtColor(img, cv2.COLOR_BGR2RGB))
