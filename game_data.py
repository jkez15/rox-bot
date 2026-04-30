"""
game_data.py — Static game-data tables extracted from RöX Unity AssetBundles.

Data source
-----------
Bundle directory : ~/Library/Containers/com.play.rosea/Data/Documents/Bundle/
Key bundles:
  - 3646f446a33a9b6da50004fc89dc8ed8.bundle  — NPC / SceneNPC / DynamicNPC tables
  - 29e911ea58189fd5aa06f4ed04bea33f.bundle  — Entrust (commission quest) tables
  - 552ed40e494471c121f4ccb67005eac8.bundle  — Recurring quest, WonderWorld, Rune tables

Architecture notes
------------------
The game uses Unity 2019.4.41f1 + HybridCLR (hot-reload C# IL) + XLua scripting.
All static data is stored as Lua TextAsset scripts inside AssetBundles.
Localization is compiled Lua bytecode (kvReversal/translate scripts) — not
human-readable.  NPC display names in the SceneNPC table are a mix of Chinese
developer names and localization keys (e.g. "NpcName61001").

Usage
-----
    from game_data import ENTRUST_NPC_WORLD_POS, ENTRUST_NPC_IDS, load_all

    # Load data at startup (slow, ~2-3 s; call once)
    load_all()

    # Get world position for a quest-board NPC
    pos = ENTRUST_NPC_WORLD_POS.get(10101013)  # (x, z) in Unity world coords
"""

from __future__ import annotations

import os
import re
import logging
from functools import lru_cache
from typing import NamedTuple

log = logging.getLogger(__name__)

BUNDLE_DIR = os.path.expanduser(
    "~/Library/Containers/com.play.rosea/Data/Documents/Bundle"
)

# ── Known bundle hashes ────────────────────────────────────────────────────
# Stable across game updates (content-addressed hashes).
BUNDLE_NPC       = "3646f446a33a9b6da50004fc89dc8ed8.bundle"
BUNDLE_ENTRUST   = "29e911ea58189fd5aa06f4ed04bea33f.bundle"
BUNDLE_STATIC    = "552ed40e494471c121f4ccb67005eac8.bundle"

# ── Entrust / commission quest board NPC IDs ──────────────────────────────
# Source: data_entrust_QuestBoard → entrustNpcId list.
# These NPCs accept/give commission quests in each map zone.
# Format: uniqueId (scene prefix encodes zone: 10xx=Prontera, 11xx=Izlude, etc.)
ENTRUST_NPC_IDS: frozenset[int] = frozenset({
    10101013,   # Prontera (scene 1010) — 委托板 (commission board)
    11101014,   # Izlude   (scene 1110) — 委托板
    11801007,   # scene 1180
    12101007,   # scene 1210
    13101009,   # scene 1310
    14101007,   # scene 1410
    16101008,   # scene 1610
    17101010,   # scene 1710
    18101010,   # scene 1810
    19101013,   # scene 1910
    50101013,   # scene 5010
    51101013,   # scene 5110
})


class WorldPos(NamedTuple):
    x: float
    z: float
    scene_id: int
    name: str   # developer name (Chinese or localization key)


# Populated by load_all()
ENTRUST_NPC_WORLD_POS: dict[int, WorldPos] = {}

# ── Recurring quest task descriptions (localization keys) ─────────────────
# Source: data_RecurringQuest_RecurringQuest (Script 161, 923 KB)
# Maps task_id → TaskDesc localization key (not resolved to English here).
RECURRING_QUEST_TASK_DESC: dict[int, str] = {}

_loaded = False


def load_all(force: bool = False) -> None:
    """Parse bundle files and populate all data dicts.  Safe to call multiple times."""
    global _loaded
    if _loaded and not force:
        return

    try:
        import UnityPy  # optional heavy import — only needed at load time
    except ImportError:
        log.warning("UnityPy not available — game_data will be empty")
        return

    _load_scene_npc(UnityPy)
    _load_recurring_quests(UnityPy)
    _loaded = True
    log.info(
        "game_data loaded: %d entrust NPC positions, %d recurring tasks",
        len(ENTRUST_NPC_WORLD_POS),
        len(RECURRING_QUEST_TASK_DESC),
    )


# ── Internal loaders ──────────────────────────────────────────────────────

def _bundle_path(name: str) -> str:
    return os.path.join(BUNDLE_DIR, name)


def _load_scene_npc(UnityPy) -> None:
    """Populate ENTRUST_NPC_WORLD_POS from data_npc_SceneNPC."""
    path = _bundle_path(BUNDLE_NPC)
    if not os.path.exists(path):
        log.warning("NPC bundle not found: %s", path)
        return

    env = UnityPy.load(path)
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        if data.m_Name != "data_npc_SceneNPC":
            continue

        text = data.m_Script
        for npc_id in ENTRUST_NPC_IDS:
            # Search for the uniqueid within the sceneGenerator arrays
            pattern = f'"uniqueid"] = {npc_id},'
            if pattern not in text:
                # Also try the tab-indented format
                pattern = f'"uniqueid"] = {npc_id}'
                if pattern not in text:
                    continue
            idx = text.index(pattern)
            chunk = text[max(0, idx - 700):idx + 200]

            name_m = re.search(r'"name"\] = "([^"]+)"', chunk)
            posx_m = re.search(r'"posx"\]\s*=\s*([\-\d.eE+]+)', chunk)
            posz_m = re.search(r'"posz"\]\s*=\s*([\-\d.eE+]+)', chunk)
            # Find the enclosing scene block by looking for [SCENE_ID] = {
            scene_matches = list(re.finditer(r'\[(\d{4,5})\]\s*=\s*\{', text[:idx]))

            scene_id = int(scene_matches[-1].group(1)) if scene_matches else 0
            npc_name = name_m.group(1) if name_m else "?"
            posx = float(posx_m.group(1)) if posx_m else 0.0
            posz = float(posz_m.group(1)) if posz_m else 0.0

            ENTRUST_NPC_WORLD_POS[npc_id] = WorldPos(
                x=posx, z=posz, scene_id=scene_id, name=npc_name
            )
        break  # found the right TextAsset


def _load_recurring_quests(UnityPy) -> None:
    """Populate RECURRING_QUEST_TASK_DESC from data_RecurringQuest_RecurringQuest."""
    path = _bundle_path(BUNDLE_STATIC)
    if not os.path.exists(path):
        log.warning("Static bundle not found: %s", path)
        return

    env = UnityPy.load(path)
    for obj in env.objects:
        if obj.type.name != "TextAsset":
            continue
        data = obj.read()
        if data.m_Name != "data_RecurringQuest_RecurringQuest":
            continue

        text = data.m_Script
        # Extract all [id] = { ... "TaskDesc" = "...", ... } entries
        for m in re.finditer(
            r'\["Id"\]\s*=\s*(\d+).*?\["TaskDesc"\]\s*=\s*"([^"]+)"',
            text,
            re.DOTALL,
        ):
            task_id = int(m.group(1))
            task_desc_key = m.group(2)
            RECURRING_QUEST_TASK_DESC[task_id] = task_desc_key
        break


# ── Convenience helpers ───────────────────────────────────────────────────

def get_entrust_npc_pos(npc_id: int) -> WorldPos | None:
    """Return world position of an entrust quest NPC, or None if unknown."""
    return ENTRUST_NPC_WORLD_POS.get(npc_id)


def scene_id_from_npc(npc_unique_id: int) -> int:
    """
    Derive the scene ID from a uniqueId using the game's naming convention.
    NPC uniqueIds encode the scene: first 4 digits = scene_id.
    e.g. 10101013 → scene 1010, 11101014 → scene 1110.
    """
    return int(str(npc_unique_id)[:4])


if __name__ == "__main__":
    import time
    logging.basicConfig(level=logging.INFO)
    t0 = time.time()
    load_all()
    print(f"Loaded in {time.time()-t0:.1f}s")
    print(f"\nEntrust NPC positions ({len(ENTRUST_NPC_WORLD_POS)}):")
    for npc_id, pos in sorted(ENTRUST_NPC_WORLD_POS.items()):
        print(f"  {npc_id}: scene={pos.scene_id}  ({pos.x:8.2f}, {pos.z:8.2f})  [{pos.name}]")
    print(f"\nRecurring quest tasks: {len(RECURRING_QUEST_TASK_DESC)}")
