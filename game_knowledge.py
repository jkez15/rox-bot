"""
game_knowledge.py — Offline game-data knowledge base parsed from bundle dumps.

This module reads the text files in bundle_dumps/ (committed to git from the
live machine) and builds lookup tables the bot can use to make smarter
decisions without needing UnityPy or the live game.

Data available
--------------
  ALL_SCENE_NPCS         dict[int, SceneNPC]   — every NPC with world coords
  ENTRUST_NPC_IDS        frozenset[int]         — commission-board NPC uniqueIds
  ENTRUST_NPC_POSITIONS  dict[int, SceneNPC]    — commission-board NPCs only
  RECURRING_QUESTS       dict[int, RecurringQuest]  — 1701 tasks
  WORLD_TASKS            dict[int, WorldTask]       — world-event tasks
  NPC_STATIC             dict[int, NPCStatic]       — base NPC defs (name, dialogue)

  scene_name(scene_id)   → human label ("Prontera", "Izlude", …)
  npcs_in_scene(scene_id) → list of SceneNPC in that zone
  find_npc(unique_id)     → SceneNPC or None

Usage
-----
    from game_knowledge import load, ALL_SCENE_NPCS, RECURRING_QUESTS
    load()   # ~0.3 s, reads bundle_dumps/*.txt, no heavy deps
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import NamedTuple

_BASE = os.path.join(os.path.dirname(__file__), "bundle_dumps")

# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SceneNPC:
    unique_id: int
    static_id: int
    scene_id: int
    name: str
    x: float
    y: float
    z: float
    visible: bool = True


@dataclass(frozen=True)
class NPCStatic:
    static_id: int
    name: str                          # localization key e.g. "NpcName40000"
    npc_type: int = 0
    dialogue_ids: tuple[int, ...] = ()


@dataclass(frozen=True)
class RecurringQuest:
    quest_id: int
    task_desc: str          # localization key
    target_type: int = 0
    target_params: tuple[int, ...] = ()
    times: int = 1
    join_type: int = 0
    join_param: str = "0"
    day: int | None = None
    day_type: int | None = None
    reward: int = 0


@dataclass(frozen=True)
class WorldTask:
    task_id: int
    task_name: str
    task_desc: str
    show_name: str
    submit_npc: int = 0
    area_id: int = 0


# ── Module-level dicts (populated by load()) ─────────────────────────────────

ALL_SCENE_NPCS: dict[int, SceneNPC] = {}
NPC_STATIC: dict[int, NPCStatic] = {}
RECURRING_QUESTS: dict[int, RecurringQuest] = {}
WORLD_TASKS: dict[int, WorldTask] = {}

ENTRUST_NPC_IDS: frozenset[int] = frozenset({
    10101013, 11101014, 11801007, 12101007, 13101009, 14101007,
    16101008, 17101010, 18101010, 19101013, 50101013, 51101013,
})

ENTRUST_NPC_POSITIONS: dict[int, SceneNPC] = {}

SCENE_NAMES: dict[int, str] = {
    1000: "World Map",
    1010: "Prontera",
    1110: "Izlude",
    1180: "Byalan",
    1210: "Geffen",
    1310: "Payon",
    1410: "Morroc",
    1610: "Alberta",
    1710: "Aldebaran",
    1810: "Lutie",
    1910: "Comodo",
    5010: "Niflheim",
    5110: "Lighthalzen",
}

_loaded = False


# ── Public API ────────────────────────────────────────────────────────────────

def load(force: bool = False) -> None:
    """Parse bundle_dumps/ text files. Fast (~0.3 s), no heavy dependencies."""
    global _loaded
    if _loaded and not force:
        return
    _parse_scene_npcs()
    _parse_npc_static()
    _parse_recurring_quests()
    _parse_world_tasks()
    # Build entrust subset
    ENTRUST_NPC_POSITIONS.clear()
    for uid in ENTRUST_NPC_IDS:
        if uid in ALL_SCENE_NPCS:
            ENTRUST_NPC_POSITIONS[uid] = ALL_SCENE_NPCS[uid]
    _loaded = True
    print(
        f"[GameKnowledge] Loaded: {len(ALL_SCENE_NPCS)} scene NPCs, "
        f"{len(NPC_STATIC)} static NPCs, "
        f"{len(RECURRING_QUESTS)} recurring quests, "
        f"{len(WORLD_TASKS)} world tasks, "
        f"{len(ENTRUST_NPC_POSITIONS)} entrust NPCs"
    )


def scene_name(scene_id: int) -> str:
    return SCENE_NAMES.get(scene_id, f"Scene {scene_id}")


def npcs_in_scene(scene_id: int) -> list[SceneNPC]:
    return [n for n in ALL_SCENE_NPCS.values() if n.scene_id == scene_id]


def find_npc(unique_id: int) -> SceneNPC | None:
    return ALL_SCENE_NPCS.get(unique_id)


# ── Parsers ───────────────────────────────────────────────────────────────────

def _read_dump(filename: str) -> str:
    path = os.path.join(_BASE, filename)
    if not os.path.exists(path):
        print(f"[GameKnowledge] Warning: {path} not found")
        return ""
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def _find_section(text: str, marker: str) -> str:
    """Extract a dump section by its header marker, skipping the header lines."""
    start = text.find(marker)
    if start == -1:
        return ""
    # Skip past the 3 header lines (marker, separator, blank)
    body_start = text.find("\n\n", start)
    if body_start == -1:
        return ""
    body_start += 2  # skip past \n\n
    # Find the next section header: a line starting with "# " after a blank line
    next_sec = re.search(r'\n\n# ─', text[body_start:])
    if next_sec:
        return text[body_start:body_start + next_sec.start()]
    return text[body_start:]


def _parse_scene_npcs() -> None:
    """
    Parse data_npc_SceneNPC from npc_raw.txt.

    Structure: each scene is  [SCENE_ID] = { sceneGenerator = { {npc}, {npc}, ... } }
    NPCs are nested inside the sceneGenerator array.
    """
    ALL_SCENE_NPCS.clear()
    text = _read_dump("npc_raw.txt")
    if not text:
        return

    section = _find_section(text, "# data_npc_SceneNPC")
    if not section:
        return

    # Parse scene blocks: [SCENE_ID] = {
    current_scene_id = 0
    for scene_m in re.finditer(r'\[(\d{4,5})\]\s*=\s*\{', section):
        current_scene_id = int(scene_m.group(1))
        scene_start = scene_m.end()

        # Find all NPC entries within this scene's sceneGenerator
        # Walk forward from here — NPCs are in the sceneGenerator array
        # Look for uniqueid entries
        # Determine end of this scene block (next scene block or end)
        next_scene = re.search(r'\n\t\[\d{4,5}\]\s*=\s*\{', section[scene_start:])
        scene_end = scene_start + next_scene.start() if next_scene else len(section)
        scene_block = section[scene_start:scene_end]

        # Extract each NPC from the sceneGenerator list
        for npc_m in re.finditer(
            r'\["uniqueid"\]\s*=\s*(\d+)',
            scene_block,
        ):
            uid = int(npc_m.group(1))
            # Look backward from this match to find the enclosing NPC block
            pos = npc_m.start()
            chunk = scene_block[max(0, pos - 600):pos + 200]

            name_m = re.search(r'\["name"\]\s*=\s*"([^"]*)"', chunk)
            posx_m = re.search(r'\["posx"\]\s*=\s*([\-\d.eE+]+)', chunk)
            posy_m = re.search(r'\["posy"\]\s*=\s*([\-\d.eE+]+)', chunk)
            posz_m = re.search(r'\["posz"\]\s*=\s*([\-\d.eE+]+)', chunk)
            static_m = re.search(r'\["staticId"\]\s*=\s*(\d+)', chunk)
            vis_m = re.search(r'\["visible"\]\s*=\s*(\d+)', chunk)

            ALL_SCENE_NPCS[uid] = SceneNPC(
                unique_id=uid,
                static_id=int(static_m.group(1)) if static_m else 0,
                scene_id=current_scene_id,
                name=name_m.group(1) if name_m else "?",
                x=float(posx_m.group(1)) if posx_m else 0.0,
                y=float(posy_m.group(1)) if posy_m else 0.0,
                z=float(posz_m.group(1)) if posz_m else 0.0,
                visible=int(vis_m.group(1)) != 0 if vis_m else True,
            )


def _parse_npc_static() -> None:
    """Parse data_npc_NPC from npc_raw.txt — base NPC definitions."""
    NPC_STATIC.clear()
    text = _read_dump("npc_raw.txt")
    if not text:
        return

    section = _find_section(text, "# data_npc_NPC")
    if not section:
        return

    for block_m in re.finditer(
        r'\[(\d+)\]\s*=\s*\{(.*?)\n\t\}',
        section,
        re.DOTALL,
    ):
        sid = int(block_m.group(1))
        block = block_m.group(2)

        name_m = re.search(r'\["name"\]\s*=\s*"([^"]*)"', block)
        type_m = re.search(r'\["type"\]\s*=\s*(\d+)', block)
        dlg_ids: list[int] = []
        dlg_m = re.search(r'\["defaultDialogueIdList"\]\s*=\s*\{([^}]*)\}', block)
        if dlg_m:
            dlg_ids = [int(x) for x in re.findall(r'\d+', dlg_m.group(1))]

        NPC_STATIC[sid] = NPCStatic(
            static_id=sid,
            name=name_m.group(1) if name_m else f"NPC_{sid}",
            npc_type=int(type_m.group(1)) if type_m else 0,
            dialogue_ids=tuple(dlg_ids),
        )


def _parse_recurring_quests() -> None:
    """Parse data_RecurringQuest_RecurringQuest from recurring_quests_raw.txt."""
    RECURRING_QUESTS.clear()
    text = _read_dump("recurring_quests_raw.txt")
    if not text:
        return

    section = _find_section(text, "# data_RecurringQuest_RecurringQuest")
    if not section:
        return

    for block_m in re.finditer(
        r'\[\d+\]\s*=\s*\{(.*?)\n\t\}',
        section,
        re.DOTALL,
    ):
        block = block_m.group(1)

        id_m = re.search(r'\["Id"\]\s*=\s*(\d+)', block)
        if not id_m:
            continue
        qid = int(id_m.group(1))

        desc_m = re.search(r'\["TaskDesc"\]\s*=\s*"([^"]*)"', block)
        tt_m = re.search(r'\["TargetType"\]\s*=\s*(\d+)', block)
        times_m = re.search(r'\["Times"\]\s*=\s*(\d+)', block)
        jt_m = re.search(r'\["JoinType"\]\s*=\s*(\d+)', block)
        jp_m = re.search(r'\["JoinTypeParameter"\]\s*=\s*"([^"]*)"', block)
        day_m = re.search(r'\["Day"\]\s*=\s*(\d+)', block)
        dt_m = re.search(r'\["DayType"\]\s*=\s*(\d+)', block)
        rew_m = re.search(r'\["reward"\]\s*=\s*(\d+)', block)

        # Target parameters
        tp_list: list[int] = []
        tp_m = re.search(r'\["TargetParameter"\]\s*=\s*\{([^}]*)\}', block)
        if tp_m:
            tp_list = [int(x) for x in re.findall(r'\d+', tp_m.group(1))]

        RECURRING_QUESTS[qid] = RecurringQuest(
            quest_id=qid,
            task_desc=desc_m.group(1) if desc_m else "",
            target_type=int(tt_m.group(1)) if tt_m else 0,
            target_params=tuple(tp_list),
            times=int(times_m.group(1)) if times_m else 1,
            join_type=int(jt_m.group(1)) if jt_m else 0,
            join_param=jp_m.group(1) if jp_m else "0",
            day=int(day_m.group(1)) if day_m else None,
            day_type=int(dt_m.group(1)) if dt_m else None,
            reward=int(rew_m.group(1)) if rew_m else 0,
        )


def _parse_world_tasks() -> None:
    """Parse data_WorldTask_WorldTask from recurring_quests_raw.txt."""
    WORLD_TASKS.clear()
    text = _read_dump("recurring_quests_raw.txt")
    if not text:
        return

    section = _find_section(text, "# data_WorldTask_WorldTask")
    if not section:
        return

    for block_m in re.finditer(
        r'\[\d+\]\s*=\s*\{(.*?)\n\t\}',
        section,
        re.DOTALL,
    ):
        block = block_m.group(1)

        id_m = re.search(r'\["id"\]\s*=\s*(\d+)', block)
        if not id_m:
            continue
        tid = int(id_m.group(1))

        tn_m = re.search(r'\["taskName"\]\s*=\s*"([^"]*)"', block)
        td_m = re.search(r'\["taskDescription"\]\s*=\s*"([^"]*)"', block)
        sn_m = re.search(r'\["showName"\]\s*=\s*"([^"]*)"', block)
        snpc_m = re.search(r'\["submitNpc"\]\s*=\s*(\d+)', block)
        area_m = re.search(r'\["areaId"\]\s*=\s*(\d+)', block)

        WORLD_TASKS[tid] = WorldTask(
            task_id=tid,
            task_name=tn_m.group(1) if tn_m else "",
            task_desc=td_m.group(1) if td_m else "",
            show_name=sn_m.group(1) if sn_m else "",
            submit_npc=int(snpc_m.group(1)) if snpc_m else 0,
            area_id=int(area_m.group(1)) if area_m else 0,
        )


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import time as _t
    t0 = _t.time()
    load()
    print(f"\nLoaded in {_t.time() - t0:.2f}s")

    print(f"\n--- Entrust NPC Positions ({len(ENTRUST_NPC_POSITIONS)}) ---")
    for uid, npc in sorted(ENTRUST_NPC_POSITIONS.items()):
        print(f"  {uid}: {scene_name(npc.scene_id)} ({npc.x:.2f}, {npc.z:.2f}) [{npc.name}]")

    print(f"\n--- Sample Scene NPCs (Prontera, first 10) ---")
    for npc in npcs_in_scene(1010)[:10]:
        print(f"  {npc.unique_id}: ({npc.x:.2f}, {npc.z:.2f}) [{npc.name}] vis={npc.visible}")

    print(f"\n--- Recurring Quest Target Types ---")
    type_counts: dict[int, int] = {}
    for rq in RECURRING_QUESTS.values():
        type_counts[rq.target_type] = type_counts.get(rq.target_type, 0) + 1
    for tt, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  TargetType {tt}: {count} quests")

    print(f"\n--- World Tasks ---")
    for wt in WORLD_TASKS.values():
        print(f"  [{wt.task_id}] {wt.task_name} — {wt.task_desc}")
