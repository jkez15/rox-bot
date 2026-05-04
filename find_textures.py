#!/usr/bin/env python3
"""Find all Texture2D assets in data.unity3d and resources.resource"""
import UnityPy, sys
from pathlib import Path

base = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data")

for fname in ["data.unity3d", "resources.resource"]:
    f = base / fname
    if not f.exists():
        continue
    print(f"\n=== {fname} ===")
    try:
        env = UnityPy.load(str(f))
        textures = []
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                textures.append(data.name)
        print(f"  Found {len(textures)} Texture2D objects")
        icon_names = [n for n in textures if "icon" in n.lower() or "npc" in n.lower() or "map" in n.lower()]
        print(f"  Icon-related: {icon_names[:50]}")
        print(f"  All names sample: {textures[:20]}")
    except Exception as e:
        print(f"  Error: {e}")
