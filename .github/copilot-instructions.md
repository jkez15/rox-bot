# RöX Automation Bot — Copilot Instructions

## Two-machine workflow

This project is developed across **two machines**:

| Machine | Role |
|---|---|
| **Mac with RöX** | Live testing, OCR calibration, template capture, bug diagnosis. All screen captures, clicks, and OCR runs happen here. |
| **Other machine (no RöX)** | Architecture, AI/ML solutions, complex logic, code review, new modules. Cannot run the bot — but can read, analyse, and write all code. |

### Rules for the other machine
- **Never run `main.py`, `calibrate.py`, `capture.py`, or anything that requires the game window.** These will fail silently or hang.
- **Do write** new modules, improve algorithms, add logic, refactor, and propose solutions.
- When you need to verify screen geometry or OCR output, look at the `debug_*.png` files committed to the repo — they are real annotated captures from the live machine.
- All coordinate constants are in `quests.py` (`HUD_TOP_Y_MAX`, `GAME_WORLD_Y_MAX`, etc.). Use these when reasoning about screen layout.
- The live machine will test and diagnose; the other machine builds the solutions.

---

## Project purpose
This is a **macOS Python automation bot** for the mobile/desktop game **RöX** (process name `RX`, Quartz window owner `Ro\u0308X` — NFD-encoded umlaut). The bot detects the running game, captures its window, performs Apple Vision OCR + OpenCV template matching to locate UI elements, and sends mouse clicks to automate quests and other repetitive tasks.

## Project structure

| File | Role |
|---|---|
| `main.py` | Entry point. Spawns worker thread + launches Tkinter dashboard. |
| `config.py` | All tunable constants (process name, thresholds, intervals). |
| `detector.py` | Uses `psutil` to check whether RöX is running. |
| `capture.py` | Captures the RöX window via macOS Quartz (`CGWindowListCreateImage`). Returns a **logical-resolution** PIL Image (1× not 2×). |
| `ocr.py` | **Apple Vision OCR engine** (`VNRecognizeTextRequest`). ~190ms/scan, replaces EasyOCR. Returns `list[TextRegion]`. |
| `recognizer.py` | OpenCV `TM_CCOEFF_NORMED` template matching (icon/button detection). |
| `quests.py` | Quest automation: 5-step state machine — pathfinding idle → dialog advance → interaction → smart action buttons → quest row click. |
| `actions.py` | Mouse actions via **macOS Quartz CGEvents** (does NOT move the physical cursor). Keyboard via `pyautogui`. |
| `ui_dashboard.py` | Tkinter floating overlay: always-on-top, compact layout, task checklist (Quests, Daily Rewards, Auto-Potion, Party Accept, Farming). |
| `game_knowledge.py` | **Offline** game-data knowledge base parsed from `bundle_dumps/` text files. 1914 scene NPCs, 4215 static NPCs, 1890 recurring quests, 6 world tasks. No heavy deps. |
| `log_monitor.py` | Real-time Unity `Player.log` tail monitor. Detects scene changes, quest updates, pathfinding events, NPC interactions. Runs on a daemon thread. |
| `game_data.py` | Static game-data tables parsed from Unity AssetBundles via UnityPy (live machine). Provides entrust NPC world positions and recurring quest task keys. |
| `bundle_explorer.py` | **Run on live machine.** Extracts all Lua TextAsset data from AssetBundles → `bundle_dumps/`. |
| `calibrate.py` | **Run on live machine only.** Captures window, annotates every match, saves `debug_calibration.png`. |
| `save_template.py` | Captures the RöX window to `templates/<name>.png` for cropping new templates. Run on live machine. |
| `bundle_dumps/` | Pre-extracted game data text files (NPC positions, quests, waypoints). Committed to git for offline analysis. |
| `templates/` | PNG reference images used for template matching. |
| `ocr_easyocr_backup.py` | Old EasyOCR implementation, kept for reference. Do not use. |

---

## Screen layout (1051 × 816 logical pixels)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  y < 300    TOP HUD: HP/SP bars, minimap, Backpack, Leave dungeon btn   │
├────────┬────────────────────────────────────────────────────────────────┤
│        │                                                                │
│ QUEST  │           GAME WORLD  (300 ≤ y < 620)                         │
│ PANEL  │    NPC buttons, action buttons, dialog choice buttons          │
│ x<260  │                                                                │
│        ├────────────────────────────────────────────────────────────────┤
│        │  DIALOG / CHAT ZONE  (620 ≤ y < 770) — never clicked          │
├────────┴────────────────────────────────────────────────────────────────┤
│  y ≥ 770    BOTTOM HUD: level bar, chat input                           │
└─────────────────────────────────────────────────────────────────────────┘
```

Key constants in `quests.py`:
```python
QUEST_PANEL_X_MAX = 260   # sidebar right edge
HUD_TOP_Y_MAX     = 300   # top HUD bottom edge
GAME_WORLD_Y_MAX  = 620   # game world bottom edge
DIALOG_TEXT_Y_MIN = 620   # chat/dialog zone starts
DIALOG_TEXT_Y_MAX = 770   # chat/dialog zone ends
```

---

## OCR engine — Apple Vision (`ocr.py`)

```python
from ocr import read_window, find_text, find_all_text

regions = read_window(screenshot, min_conf=0.30)
# returns list[TextRegion(text, x, y, w, h, conf, cx, cy)]

r = find_text(regions, r"\[Main\]", min_conf=0.40)
# returns first TextRegion matching the regex, or None
```

- Uses `VNRecognizeTextRequest` via `pyobjc` — **no model download, no GPU**
- `usesLanguageCorrection = False` — preserves exact game text like `[Main]`
- Vision coord system is bottom-left origin; `ocr.py` flips to top-left before returning
- Confidence is typically 0.9–1.0 for clean game UI text; 0.5–0.8 for styled buttons

---

## Quest automation state machine (`quests.py`)

Each call to `do_quest_scan()` runs one full cycle:

```
Step 0  Pathfinding active?  →  wait, no click
Step 1  Explicit dialog button (Skip/Inquire/Next/Close/OK…)?  →  click it
Step 2  Examine/Inspect/Talk button in game world?  →  click icon above label
Step 3  Any action button (Show/Collect/Use/Activate/Enter…) in game world?  →  click
Step 4  [Main] quest row in sidebar?  →  click to set navigation target
```

The chat/dialog zone (`y > 620`) is **never clicked**. All detection is button-first — no text-zone spam-clicking.

---

## Critical rules — always follow these

### 1. Coordinates are always LOGICAL (1× not Retina 2×)
`capture.py` resizes the captured image back to logical size. Template match results `(cx, cy)` are directly usable as `click(cx, cy, bounds)` arguments. **Never multiply or divide by 2.**

### 2. Click targets must come from OCR/template matches, not hardcoded pixels
Use `find_text(regions, pattern)` or `find_template(screenshot, "name.png")`. Hardcoded pixel offsets break when the window moves or resizes.

### 3. Always run calibrate.py (on live machine) after changing templates
`calibrate.py` saves `debug_calibration.png` — an annotated screenshot showing every click target. Check this file in the repo to verify positions.

### 4. Template matching threshold guidance
- **0.85+** — exact pixel match (same game session, no UI animation)
- **0.70–0.84** — recommended default
- **0.55–0.69** — presence detection only (not a click target)
- **< 0.55** — unreliable; recrop the template

### 5. The window name has a Unicode NFD umlaut
`APP_WINDOW_NAME = "Ro\u0308X"` (o + combining umlaut U+0308, NOT ö U+00F6). Do not change without updating `capture.py` comparison logic.

### 6. Virtual environment
All dependencies live in `.venv/`. Always use `.venv/bin/python`. Do not use the `venv/` folder.

### 7. Thread safety
Tkinter runs on the **main thread**. Automation runs on a **daemon thread**. All cross-thread communication goes through `Dashboard` methods with `threading.Lock`. Never call Tkinter widget methods from the worker thread.

---

## Adding a new automation task (step-by-step)

1. **Capture a template** (live machine):
   ```bash
   python save_template.py my_button_name
   ```
2. **Crop it** — Open `templates/my_button_name.png` in Preview → Rectangular Selection → ⌘K Crop → ⌘S Save. Crop tightly around just the button.

3. **Register it in `calibrate.py`**:
   ```python
   {
       "name":      "My Button",
       "template":  "my_button_name.png",
       "threshold": 0.75,
       "required":  True,
       "colour":    "yellow",
   }
   ```

4. **Run calibration** (live machine):
   ```bash
   python calibrate.py
   # inspect debug_calibration.png to verify the circle is on the right element
   ```

5. **Write the automation**:
   ```python
   # OCR approach (text labels)
   r = find_text(regions, r"\bMyLabel\b", min_conf=0.50)
   if r and r.cx > QUEST_PANEL_X_MAX and r.cy < GAME_WORLD_Y_MAX:
       click(r.cx, r.cy, bounds)

   # Template approach (icons with no text)
   match = find_template(screenshot, "my_button_name.png", threshold=0.75)
   if match:
       cx, cy, conf = match
       click(cx, cy, bounds)
   ```

6. **Wire into `do_quest_scan()`** in `quests.py` at the appropriate step priority.

---

## Planned future automation (build these on the other machine)

- [ ] **HP/SP potion auto-use** — detect HP/SP bar fill level via template matching on the bar region; click potion hotkey when below threshold. Bar region: approx `(0–260, 0–60)`.
- [ ] **Auto-collect daily quest rewards** — detect reward popup (template: golden chest icon); click Collect button.
- [ ] **Auto-talk to NPCs when distance = 0 m** — parse "Distance to target: 0 m" from OCR; trigger Examine interaction immediately.
- [ ] **Auto-enter dungeons / boss fights** — detect dungeon entry prompt template; click Enter/Challenge.
- [ ] **Party auto-accept** — detect party invite popup; click Accept.
- [ ] **Recurring quest board automation** — use `game_data.RECURRING_QUEST_TASK_DESC` (1701 tasks) to identify and complete recurring quests from the commission board.
- [ ] **Scene-aware navigation** — use `game_data.ENTRUST_NPC_WORLD_POS` (12 NPCs with Unity world coords) to build scene-specific routing logic.
- [ ] **Vision-based HP bar reader** — crop HP bar pixel row, measure red/green ratio for exact HP% without template matching.

---

## Game engine internals (research notes)

### Engine stack
- **Unity 2019.4.41f1** with **HybridCLR** (hot-reload C# IL) + **XLua** scripting
- iOS app running via macOS Catalyst wrapper: `RöX.app/Wrapper/RX.app`
- App container: `~/Library/Containers/com.play.rosea/Data/`

### Unity AssetBundles
All static game data is stored as **Lua TextAsset** scripts inside 10,946 Unity AssetBundles:
```
~/Library/Containers/com.play.rosea/Data/Documents/Bundle/
```

**Key bundle hashes** (stable, content-addressed):

| Bundle hash | Contents |
|---|---|
| `3646f446a33a9b6da50004fc89dc8ed8` | NPC tables: `data_npc_NPC`, `data_npc_SceneNPC` (1.3 MB, all NPC world positions), `data_npc_DynamicNPC`, `data_DynamicNPCInfo` |
| `29e911ea58189fd5aa06f4ed04bea33f` | Entrust/commission quests: `data_entrust_QuestBoard`, `data_entrust_LoversQuestPool`, `data_entrust_QuestSpecialPool` |
| `552ed40e494471c121f4ccb67005eac8` | 417 Lua scripts — `data_RecurringQuest_RecurringQuest` (923 KB, 1701 tasks), WorldTask, RamadanQuest, WonderWorld |
| `e8bf32a6421ee05bc02c146520e1874c` | Route waypoints (`posx/posy/posz`), BattlePass, SevenDayQuest |
| `e957292c18f4bfd36c5770ed1496e812` | UI prefabs + compiled Lua bytecode: `debug_en_translate`, `debug_en_kvReversal` (English localization — **bytecode, not readable**) |

### Localization
English localization scripts are **compiled Lua 5.3 bytecode** — not plain text. NPC display names in `data_npc_SceneNPC` are Chinese developer names (e.g. `委托板` = "Commission Board") or localization keys (e.g. `NpcName61001`).

### game_data.py
```python
from game_data import load_all, ENTRUST_NPC_WORLD_POS, RECURRING_QUEST_TASK_DESC
load_all()   # ~0.8 s, call once at startup
pos = ENTRUST_NPC_WORLD_POS[10101013]  # WorldPos(x=-8.57, z=-31.46, scene_id=1010, name='委托板')
```
- `ENTRUST_NPC_WORLD_POS` — 12 quest-board NPCs with Unity world (x, z) coords
- `RECURRING_QUEST_TASK_DESC` — 1701 recurring quest task localization keys
- Scene IDs: `1010`=Prontera, `1110`=Izlude, `1210`=Geffen, `1310`, `1410`, etc.
- NPC uniqueId first-4-digits = scene_id: `10101013 → scene 1010`

### Assembly
`/Applications/RöX.app/Wrapper/RX.app/Data/Raw/Assembly-CSharp.dll.bytes` is a readable MZ/.NET DLL (HybridCLR). 3,886 types. Key namespaces: `Dream.Data` (TaskModel, NPCModel), `Dream.Game.AutoPathing`, `Dream.Game.Com.RoleMoveComponent`, `Cc.Thedream.Mmo.Protocal.Task`.

### Runtime injection — BLOCKED
Frida is blocked: app lacks `get-task-allow` entitlement, production-signed (`2Y3ZW5J4A7.com.play.rosea`). `frida.PermissionDeniedError` will be thrown. Do not attempt Frida injection or cheat-engine approaches.

### Accessibility API — USELESS
The game renders via Metal canvas. `AXUIElement` only exposes `AXGroup`/`AXButton` with no text content. Use `ocr.py` for all text detection.

---

## Game integration strategy

Since runtime injection (Frida) is blocked and the Accessibility API is useless for this Unity game, we use **three complementary approaches** to get game data:

### 1. Offline knowledge base — `game_knowledge.py`
```python
from game_knowledge import load, ALL_SCENE_NPCS, RECURRING_QUESTS, npcs_in_scene
load()   # ~0.2 s, reads bundle_dumps/*.txt only — no heavy deps

# 1914 NPCs with 3D world coordinates
npc = ALL_SCENE_NPCS[10101013]  # SceneNPC(unique_id=10101013, scene_id=1010, x=-8.57, z=-31.46, name='委托板')

# 1890 recurring quest task definitions
q = RECURRING_QUESTS[30101]     # RecurringQuest(quest_id=30101, target_type=74, times=50, ...)

# All NPCs in Prontera
prontera_npcs = npcs_in_scene(1010)  # list of SceneNPC
```
- Parses `bundle_dumps/` text files (committed to git from the live machine)
- No UnityPy needed — works offline on any machine
- Provides: NPC positions, quest definitions, world tasks, NPC dialogue IDs

### 2. Real-time log monitor — `log_monitor.py`
```python
from log_monitor import LogMonitor
monitor = LogMonitor()
monitor.start()  # daemon thread tails Player.log

# In automation loop:
for event in monitor.drain_events():
    if event.kind == "scene_change":
        new_scene = int(event.data["scene_id"])
    elif event.kind == "quest_complete":
        ...

# Or check accumulated state:
if monitor.current_scene == 1010:  # Prontera
    ...
if monitor.is_pathfinding:  # avoid clicking
    ...
```
- Tails Unity's `Player.log` in real-time
- Detects: scene changes, quest updates, NPC interactions, pathfinding start/end, errors
- Patterns are estimates — **must be calibrated on live machine** by examining actual log output
- Run `python log_monitor.py` on the live machine to see raw log events

### 3. Live machine calibration tasks
When on the live machine, run these to discover actual log patterns:
```bash
# Watch the log in real-time while playing
python log_monitor.py

# Re-extract bundle data after game updates
python bundle_explorer.py

# Examine actual Player.log location and contents
tail -f ~/Library/Containers/com.play.rosea/Data/Library/Logs/Unity/Player.log
```

---

## macOS permissions required (live machine only)
- **Screen Recording** — System Settings → Privacy & Security → Screen Recording → Terminal
- **Accessibility** — Same location → Accessibility → Terminal (for `pyautogui` mouse control)

If capture returns a black image or clicks don't register, check these permissions first.

