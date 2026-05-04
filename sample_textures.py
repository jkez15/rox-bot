#!/usr/bin/env python3
"""Sample 200 random bundles and print all Texture2D names found — to understand naming."""
import UnityPy, random
from pathlib import Path

bundle_dir = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/Raw/IOS")
bundles = sorted(bundle_dir.glob("*.bundle"))
sample = random.sample(bundles, min(200, len(bundles)))

names = set()
for bf in sample:
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                names.add(data.name)
    except Exception:
        pass

for n in sorted(names):
    print(n)
print(f"\n{len(names)} unique Texture2D names in 200-bundle sample")
