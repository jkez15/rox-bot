#!/usr/bin/env python3
"""
Extract ALL NPC-related icon sprites from all shared_assets__ui_icons bundles.
Save them to templates/ with their sprite names.
"""
import UnityPy, sys
from pathlib import Path

bdir = Path.home() / "Library/Containers/com.play.rosea/Data/Documents/Bundle"
out_dir = Path("/Users/jkez/Documents/rox/templates")
out_dir.mkdir(exist_ok=True)

# Relevant bundle names to extract
BUNDLE_KEYWORDS = [
    "ui_icons_npc", "ui_icons_task", "ui_icons_collect",
    "seainteractive", "mapnpc", "npcmark", "npcicon",
    "ui_icons_pve", "ui_icons_pvp", "ui_icons_guild", "ui_icons_buffs",
]

extracted_total = 0
processed_bundles = 0

for bf in sorted(bdir.glob("*.bundle")):
    try:
        env = UnityPy.load(str(bf))
        bundle_name = ""
        for obj in env.objects:
            if obj.type.name == "AssetBundle":
                d = obj.read()
                bundle_name = getattr(d, 'm_AssetBundleName', '') or getattr(d, 'm_Name', '')
                break

        if not any(k in bundle_name for k in BUNDLE_KEYWORDS):
            continue

        processed_bundles += 1
        print(f"\n=== {bundle_name} ===")
        bundle_extracted = 0

        # Reload and extract
        env2 = UnityPy.load(str(bf))
        for obj in env2.objects:
            if obj.type.name == "Sprite":
                try:
                    data = obj.read()
                    name = getattr(data, 'name', getattr(data, 'm_Name', f'sprite_{bundle_extracted}'))
                    img = data.image
                    out_path = out_dir / f"{name}.png"
                    if not out_path.exists():
                        img.save(str(out_path))
                        bundle_extracted += 1
                        extracted_total += 1
                        print(f"  [+] {name} ({img.size[0]}x{img.size[1]})")
                except Exception as e:
                    pass

        print(f"  → {bundle_extracted} sprites")

    except Exception:
        pass

print(f"\n{'='*50}")
print(f"Processed {processed_bundles} bundles, extracted {extracted_total} sprites")
print(f"Templates dir: {len(list(out_dir.glob('*.png')))} total PNGs")
