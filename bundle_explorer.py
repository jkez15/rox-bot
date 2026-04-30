"""
bundle_explorer.py — Read and dump Unity AssetBundle data from the RöX game.

PURPOSE
-------
This script is a research/analysis tool for the OTHER machine (no RöX).
It documents the full structure of every key AssetBundle so that automation
logic can be built without needing live access to the game.

Run on the LIVE machine (Mac with RöX installed):
    python bundle_explorer.py

Output files written to  bundle_dumps/ :
    npc_scene.txt          — All SceneNPC entries (world positions + names)
    npc_all.txt            — All NPC entries (stats, types)
    entrust_board.txt      — Commission quest board data
    recurring_quests.txt   — All 1701 recurring quest tasks
    waypoints.txt          — Route waypoints (posx/posy/posz)
    all_script_names.txt   — Names of every Lua TextAsset in all key bundles

These dump files are committed to git so the other machine can study them
without needing access to the game's bundle directory.

REQUIREMENTS (live machine only)
---------------------------------
    pip install unitypy
    # UnityPy reads .bundle files directly — no game running required.
    # Bundle dir: ~/Library/Containers/com.play.rosea/Data/Documents/Bundle/
"""

from __future__ import annotations

import os
import re
import sys
import json

BUNDLE_DIR = os.path.expanduser(
    "~/Library/Containers/com.play.rosea/Data/Documents/Bundle"
)
OUT_DIR = os.path.join(os.path.dirname(__file__), "bundle_dumps")

# Key bundles (content-addressed hashes — stable across game updates)
BUNDLES = {
    "npc":      "3646f446a33a9b6da50004fc89dc8ed8.bundle",
    "entrust":  "29e911ea58189fd5aa06f4ed04bea33f.bundle",
    "static":   "552ed40e494471c121f4ccb67005eac8.bundle",
    "waypoint": "e8bf32a6421ee05bc02c146520e1874c.bundle",
}

# Scripts of interest in each bundle
SCRIPTS_OF_INTEREST = {
    "npc": [
        "data_npc_NPC",
        "data_npc_SceneNPC",
        "data_npc_DynamicNPC",
        "data_DynamicNPCInfo",
    ],
    "entrust": [
        "data_entrust_QuestBoard",
        "data_entrust_LoversQuestPool",
        "data_entrust_QuestSpecialPool",
    ],
    "static": [
        "data_RecurringQuest_RecurringQuest",
        "data_WorldTask_WorldTask",
    ],
    "waypoint": [
        "data_Route_Route",
        "data_BattlePass_BattlePass",
        "data_SevenDayQuest_SevenDayQuest",
    ],
}


def load_bundle(key: str):
    """Load a bundle and return a dict of {script_name: text_content}."""
    import UnityPy
    path = os.path.join(BUNDLE_DIR, BUNDLES[key])
    if not os.path.exists(path):
        print(f"  ⚠  Bundle not found: {path}")
        return {}
    env = UnityPy.load(path)
    result = {}
    for obj in env.objects:
        if obj.type.name == "TextAsset":
            data = obj.read()
            result[data.m_Name] = data.m_Script
    return result


def dump_script_names(scripts: dict[str, str], out_file: str) -> None:
    """Write a sorted list of all script names + first-line previews."""
    with open(out_file, "w", encoding="utf-8", errors="replace") as f:
        for name in sorted(scripts.keys()):
            preview = scripts[name].split("\n")[0][:120].strip()
            f.write(f"{name}\n    {preview}\n\n")
    print(f"  → {out_file}  ({len(scripts)} scripts)")


def dump_raw(scripts: dict[str, str], script_names: list[str], out_file: str) -> None:
    """Write the raw Lua text of named scripts to a file."""
    with open(out_file, "w", encoding="utf-8", errors="replace") as f:
        for name in script_names:
            if name not in scripts:
                f.write(f"\n# ── {name} — NOT FOUND IN BUNDLE ──\n\n")
                continue
            text = scripts[name]
            # Skip compiled bytecode (Lua 5.3 header \x1bLua or binary garbage)
            if "\x1bLua" in text[:16] or "\x00" in text[:32]:
                f.write(f"\n# ── {name} — COMPILED BYTECODE (not readable) ──\n\n")
                continue
            f.write(f"\n# {'─'*70}\n")
            f.write(f"# {name}  ({len(text):,} chars)\n")
            f.write(f"# {'─'*70}\n\n")
            f.write(text)
            f.write("\n")
    print(f"  → {out_file}")


def extract_scene_npcs(scripts: dict[str, str]) -> list[dict]:
    """Parse data_npc_SceneNPC into a list of dicts with key fields.

    The SceneNPC structure is:
      [SCENE_ID] = {
          sceneGenerator = {
              { uniqueid = 123, name = "...", posx = ..., posz = ..., ... },
              { ... },
          }
      }

    We find each scene block by its top-level [SCENE_ID] = { key, then
    extract NPCs by finding each uniqueid entry and pulling surrounding
    fields from the enclosing chunk of Lua.
    """
    text = scripts.get("data_npc_SceneNPC", "")
    if not text:
        return []
    records = []

    # Find top-level scene blocks: [1010] = {
    scene_starts = list(re.finditer(r'\n\t\[(\d{4,5})\]\s*=\s*\{', text))
    for i, scene_m in enumerate(scene_starts):
        scene_id = int(scene_m.group(1))
        start = scene_m.end()
        end = scene_starts[i + 1].start() if i + 1 < len(scene_starts) else len(text)
        block = text[start:end]

        # Find all NPCs inside this scene block via their uniqueid field
        for uid_m in re.finditer(r'\["uniqueid"\]\s*=\s*(\d+)', block):
            uid = int(uid_m.group(1))
            pos = uid_m.start()
            # Grab a generous chunk around this NPC entry (700 chars back, 200 forward)
            chunk = block[max(0, pos - 700):pos + 200]

            name_m = re.search(r'\["name"\]\s*=\s*"([^"]*)"', chunk)
            posx_m = re.search(r'\["posx"\]\s*=\s*([\-\d.eE+]+)', chunk)
            posz_m = re.search(r'\["posz"\]\s*=\s*([\-\d.eE+]+)', chunk)

            records.append({
                "scene_id":  scene_id,
                "unique_id": uid,
                "name":      name_m.group(1) if name_m else "?",
                "posx":      float(posx_m.group(1)) if posx_m else 0.0,
                "posz":      float(posz_m.group(1)) if posz_m else 0.0,
            })
    return records


def main() -> None:
    try:
        import UnityPy
    except ImportError:
        print("❌  UnityPy not installed.  Run:  pip install unitypy")
        sys.exit(1)

    if not os.path.isdir(BUNDLE_DIR):
        print(f"❌  Bundle directory not found:\n    {BUNDLE_DIR}")
        print("    This script must be run on the Mac with RöX installed.")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"Output directory: {OUT_DIR}\n")

    # ── NPC bundle ────────────────────────────────────────────────────────
    print("Loading NPC bundle…")
    npc_scripts = load_bundle("npc")
    dump_script_names(npc_scripts, f"{OUT_DIR}/all_script_names_npc.txt")
    dump_raw(npc_scripts, SCRIPTS_OF_INTEREST["npc"], f"{OUT_DIR}/npc_raw.txt")

    # Structured SceneNPC dump
    scene_npcs = extract_scene_npcs(npc_scripts)
    with open(f"{OUT_DIR}/npc_scene.txt", "w", encoding="utf-8") as f:
        f.write(f"# data_npc_SceneNPC — {len(scene_npcs)} NPCs\n")
        f.write("# scene_id  unique_id   posx        posz        name\n\n")
        for r in sorted(scene_npcs, key=lambda x: (x["scene_id"], x["unique_id"])):
            f.write(
                f"{r['scene_id']:6d}  {r['unique_id']:12d}  "
                f"{r['posx']:10.2f}  {r['posz']:10.2f}  {r['name']}\n"
            )
    print(f"  → {OUT_DIR}/npc_scene.txt  ({len(scene_npcs)} NPCs)")

    # ── Entrust bundle ────────────────────────────────────────────────────
    print("\nLoading entrust bundle…")
    entrust_scripts = load_bundle("entrust")
    dump_script_names(entrust_scripts, f"{OUT_DIR}/all_script_names_entrust.txt")
    dump_raw(entrust_scripts, SCRIPTS_OF_INTEREST["entrust"], f"{OUT_DIR}/entrust_raw.txt")

    # ── Static / recurring quest bundle ───────────────────────────────────
    print("\nLoading static bundle…")
    static_scripts = load_bundle("static")
    dump_script_names(static_scripts, f"{OUT_DIR}/all_script_names_static.txt")
    dump_raw(static_scripts, SCRIPTS_OF_INTEREST["static"], f"{OUT_DIR}/recurring_quests_raw.txt")

    # ── Waypoint bundle ───────────────────────────────────────────────────
    print("\nLoading waypoint bundle…")
    waypoint_scripts = load_bundle("waypoint")
    dump_script_names(waypoint_scripts, f"{OUT_DIR}/all_script_names_waypoint.txt")
    dump_raw(waypoint_scripts, SCRIPTS_OF_INTEREST["waypoint"], f"{OUT_DIR}/waypoints_raw.txt")

    print(f"\n✅  Done. All dumps written to  {OUT_DIR}/")
    print("    Commit bundle_dumps/ to git so the other machine can study the data.")


if __name__ == "__main__":
    main()
