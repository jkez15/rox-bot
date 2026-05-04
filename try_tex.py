#!/usr/bin/env python3
"""Try extracting textures from data.unity3d"""
import UnityPy, sys
from pathlib import Path

base = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data")
env = UnityPy.load(str(base / "data.unity3d"))
count = 0
for obj in env.objects:
    if obj.type.name == "Texture2D":
        count += 1
        try:
            data = obj.read()
            # Try different attribute access
            n = getattr(data, 'name', None) or getattr(data, 'm_Name', None) or f"tex_{count}"
            print(f"  {n}")
            if count >= 30:
                break
        except Exception as e:
            print(f"  [err] {e}")
            if count >= 5: break
print(f"Total Texture2D: {count}")
