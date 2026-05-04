#!/usr/bin/env python3
import UnityPy, sys
from pathlib import Path

# Try data.unity3d
f = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/data.unity3d")
print(f"data.unity3d exists: {f.exists()}", file=sys.stderr)
if f.exists():
    try:
        env = UnityPy.load(str(f))
        print(f"Objects: {len(list(env.objects))}", file=sys.stderr)
        for i, obj in enumerate(env.objects):
            if i > 20: break
            print(f"  {obj.type.name}", file=sys.stderr)
            if obj.type.name == "Texture2D":
                data = obj.read()
                print(f"TEX: {data.name}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

# Try first bundle raw bytes check
b = list(Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/Raw/IOS/").glob("*.bundle"))[0]
raw = b.read_bytes()
print(f"Bundle magic: {raw[:8]}", file=sys.stderr)
print(f"Bundle header text: {raw[:20]}", file=sys.stderr)
