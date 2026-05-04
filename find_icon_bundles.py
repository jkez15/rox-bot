#!/usr/bin/env python3
"""Quickly scan AssetBundle names only (cheap) to find icon bundles, then extract."""
import UnityPy, sys
from pathlib import Path

bundle_dir = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/Raw/IOS")
out_dir    = Path("/Users/jkez/Documents/rox/templates")
out_dir.mkdir(exist_ok=True)

# Keywords to look for in AssetBundle names
KEYWORDS = ["mapnpcicon", "npcicon", "npc_icon", "icon_npc", "mapnpc", "ui_npc", "npcmark",
            "npc_mark", "npcbubble", "examine", "interact"]

bundles = sorted(bundle_dir.glob("*.bundle"))
print(f"Scanning {len(bundles)} AssetBundle names for icon bundles...", flush=True)

candidate_bundles = []
for i, bf in enumerate(bundles):
    if i % 2000 == 0:
        print(f"  {i}/{len(bundles)}  candidates={len(candidate_bundles)}", flush=True)
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            if obj.type.name == "AssetBundle":
                data = obj.read()
                ab_name = getattr(data, 'name', getattr(data, 'm_Name', '')).lower()
                if any(k in ab_name for k in KEYWORDS):
                    candidate_bundles.append((bf, ab_name))
                    print(f"  FOUND: {bf.name[:8]} → {ab_name}", flush=True)
                break  # Only need the AssetBundle object
    except Exception:
        pass

print(f"\nCandidates: {len(candidate_bundles)}")

# Now extract Texture2D from all candidate bundles
extracted = 0
for bf, ab_name in candidate_bundles:
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                name = getattr(data, 'name', getattr(data, 'm_Name', f'tex_{extracted}'))
                try:
                    img = data.image
                    out_path = out_dir / f"{name}.png"
                    img.save(str(out_path))
                    extracted += 1
                    print(f"  [+] {name}", flush=True)
                except Exception as e:
                    print(f"  [!] {name}: {e}", flush=True)
    except Exception as e:
        print(f"  [err] {bf.name[:8]}: {e}", flush=True)

print(f"\nExtracted {extracted} textures")
