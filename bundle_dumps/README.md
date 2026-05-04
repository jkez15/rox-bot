# bundle_dumps/

This directory contains raw Lua TextAsset data extracted from the RöX Unity AssetBundles.

## How to regenerate (live machine only)

```bash
pip install unitypy
python bundle_explorer.py
```

Requires RöX installed at `~/Library/Containers/com.play.rosea/Data/Documents/Bundle/`.

## Files produced

| File | Contents |
|---|---|
| `npc_scene.txt` | All SceneNPC entries: scene_id, unique_id, posx, posz, name |
| `npc_raw.txt` | Raw Lua source for data_npc_NPC, data_npc_SceneNPC, data_npc_DynamicNPC |
| `entrust_raw.txt` | Raw Lua source for commission quest board tables |
| `recurring_quests_raw.txt` | Raw Lua source for 1701 recurring quest tasks |
| `waypoints_raw.txt` | Raw Lua source for route waypoints (posx/posy/posz) |
| `all_script_names_*.txt` | Index of every Lua TextAsset in each bundle |

## Derived offline catalogs

These are committed helper files generated from the raw dumps so the non-Mac
machine can do research without re-parsing the large Lua tables.

| File | Contents |
|---|---|
| `npc_interactive_catalog.csv` | Per-NPC lookup: `npc_guid`, `scene_id`, scene position, `icon1`, `icon2`, `sign_content_key`, `sign_icon_id`, `is_interactive` |
| `npc_icon_key_summary.csv` | Unique NPC icon keys with counts and sample NPC IDs / name keys |
| `entrust_npc_icon_catalog.csv` | Commission board NPC IDs joined with `npcIcon` IDs, scene coordinates, and NPC icon keys |
| `recurring_quest_icon_catalog.csv` | Recurring quest entries that expose `icon`, `monsterId`, or `collectNpc` fields |
| `game_asset_hints.txt` | Installed app asset container paths and decompiled code path hints for future Unity extraction |

## Key data for automation

### NPC scene positions (`npc_scene.txt`)
Each line: `scene_id  unique_id  posx  posz  name`

Scene IDs map to game zones:
- `1010` = Prontera (main city)
- `1110` = Izlude
- `1210` = Geffen area
- `1310`, `1410`, `1610`, `1710`, `1810`, `1910` = other zones
- `5010`, `5110` = later zones

NPC `uniqueId` first 4 digits = scene_id (e.g. `10101013` → scene `1010`).

### Commission board NPCs
These 12 uniqueIds accept/give commission quests (one per zone):
```
10101013  11101014  11801007  12101007  13101009  14101007
16101008  17101010  18101010  19101013  50101013  51101013
```

### Recurring quest tasks (`recurring_quests_raw.txt`)
1701 tasks. Each has:
- `Id` — numeric task ID
- `TaskDesc` — localization key (e.g. `"RecurringQuestTask_001"`)
- `TaskType` — type of task
- `TaskTarget` — target count or value

### Route waypoints (`waypoints_raw.txt`)
Per-zone route tables with `posx`, `posy`, `posz` for auto-pathing.
These are the same coordinate space as SceneNPC positions.

### NPC icon keys (`npc_interactive_catalog.csv`, `npc_icon_key_summary.csv`)
These files expose stable icon names such as `icon_entrust`, `icon_blacksmith`,
`icon_weapon`, `icon_sale`, and `icon_NPC_0`.

They are useful for:
- mapping OCR labels to likely icon families
- deciding which UI elements deserve template matching instead of OCR only
- preparing future Unity asset extraction from hashed bundles

### Game asset extraction hints (`game_asset_hints.txt`)
This file records the app-side container paths observed on the live Mac:
- `RX.app/Data/data.unity3d`
- `RX.app/Data/resources.resource`
- `RX.app/Data/Raw/IOS/*.bundle`

It also records relevant decompiled path strings like:
- `UI/Prefabs/Npc/NpcSign.prefab`
- `Icons/MapNpcIcon/icon_NPC_0`

These are the bridge between the offline dump files and any future real sprite
extraction from the installed game.

## Localization note
The English/Thai/Vietnamese localization scripts (`debug_en_translate`,
`debug_en_kvReversal`) in bundle `e957292c18f4bfd36c5770ed1496e812` are
**compiled Lua 5.3 bytecode** — not readable as text. NPC names in
`data_npc_SceneNPC` are Chinese developer names or localization keys.
