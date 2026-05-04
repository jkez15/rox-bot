#!/usr/bin/env python3
"""
Fast binary search across bundles for icon texture names.
Uses raw bytes search — much faster than loading through UnityPy.
"""
import UnityPy, sys
from pathlib import Path

bundle_dir = Path("/Applications/R\u00f6X.app/Wrapper/RX.app/Data/Raw/IOS")
out_dir    = Path("/Users/jkez/Documents/rox/templates")
out_dir.mkdir(exist_ok=True)

# Target icon names from npc_icon_key_summary.csv
targets = {
    "icon_NPC_0", "icon_NPC_0_L",
    "icon_Recover", "icon_Recover_L",
    "icon_service", "icon_service_L",
    "icon_entrust", "icon_entrust_L",
    "icon_blacksmith", "icon_blacksmith_L",
    "icon_weapon", "icon_weapon_L",
    "icon_Enchanting", "icon_Enchanting_L",
    "icon_AirShip", "icon_AirShip_L",
    "icon_HeadMake", "icon_HeadMake_L",
    "icon_EM", "icon_EM_L",
    "icon_gem", "icon_gem_L",
    "icon_Exchange", "icon_Exchange_L",
    "icon_potion", "icon_potion_L",
    "icon_quest", "icon_quest_L",
    "icon_Adventure", "icon_Adventure_L",
    "icon_storage", "icon_storage_L",
    "icon_refine", "icon_refine_L",
    "icon_guild", "icon_guild_L",
    "icon_warp", "icon_warp_L",
    "icon_pvp", "icon_pvp_L",
    "icon_bank", "icon_bank_L",
    "icon_cook", "icon_cook_L",
    "icon_card", "icon_card_L",
    "icon_pet", "icon_pet_L",
    "icon_casino", "icon_casino_L",
}

found = set()
total = 0
bundles = sorted(bundle_dir.glob("*.bundle"))
print(f"Scanning {len(bundles)} bundles for {len(targets)} target icons...")
sys.stdout.flush()

for i, bf in enumerate(bundles):
    if len(found) >= len(targets):
        print(f"All targets found at bundle {i}!")
        break
    if i % 500 == 0:
        print(f"  {i}/{len(bundles)}  found={len(found)}/{len(targets)}", flush=True)
    try:
        env = UnityPy.load(str(bf))
        for obj in env.objects:
            if obj.type.name == "Texture2D":
                data = obj.read()
                name = data.name
                if name in targets and name not in found:
                    try:
                        img = data.image
                        out_path = out_dir / f"{name}.png"
                        img.save(str(out_path))
                        found.add(name)
                        total += 1
                        print(f"  [+] {name}", flush=True)
                    except Exception as e:
                        print(f"  [!] {name}: {e}", flush=True)
    except Exception:
        pass

print(f"\nDone. Extracted {total} icons.")
print(f"Missing: {targets - found}")
