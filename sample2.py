#!/usr/bin/env python3
import UnityPy, random, sys
from pathlib import Path

bundle_dir = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/Raw/IOS")
bundles = sorted(bundle_dir.glob("*.bundle"))
print(f"Total bundles: {len(bundles)}", file=sys.stderr)
sample = bundles[:50]  # just first 50

for bf in sample:
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            print(f"{bf.name[:8]} {obj.type.name}", file=sys.stderr)
            if obj.type.name == "Texture2D":
                data = obj.read()
                print(f"TEX: {data.name}")
    except Exception as e:
        pass
