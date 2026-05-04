#!/usr/bin/env python3
"""Find bundles containing Examine / NpcSign / MapNpcMark sprites"""
import UnityPy
from pathlib import Path

bdir = Path.home() / "Library/Containers/com.play.rosea/Data/Documents/Bundle"
bundles = sorted(bdir.glob("*.bundle"))
print(f"Searching {len(bundles)} bundles for examine/sign icons...")

keywords = ["examine", "npcsign", "npcmark", "npcbubble", "mapnpc",
            "interac", "sign_icon", "dialog_icon", "floatingbtn",
            "floating", "worldbtn", "worldbutton"]

for bf in bundles:
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            if obj.type.name == "AssetBundle":
                d = obj.read()
                name = (getattr(d, 'm_AssetBundleName', '') or '').lower()
                if any(k in name for k in keywords):
                    print(f"BUNDLE: {name}")
                break
    except Exception:
        pass
print("Done")
