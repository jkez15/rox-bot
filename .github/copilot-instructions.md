# RöX Automation Bot — Copilot Instructions

## Project purpose
This is a **macOS Python automation bot** for the mobile/desktop game **RöX** (process name `RX`, Quartz window owner `Ro\u0308X` — NFD-encoded umlaut). The bot detects the running game, captures its window, performs image-based template matching to locate UI elements, and sends mouse clicks to automate quests and other repetitive tasks.

## Project structure

| File | Role |
|---|---|
| `main.py` | Entry point. Spawns worker thread + launches Tkinter dashboard. |
| `config.py` | All tunable constants (process name, thresholds, intervals). |
| `detector.py` | Uses `psutil` to check whether RöX is running. |
| `capture.py` | Captures the RöX window via macOS Quartz (`CGWindowListCreateImage`). Returns a **logical-resolution** PIL Image (1× not 2×). |
| `recognizer.py` | OpenCV `TM_CCOEFF_NORMED` template matching. |
| `quests.py` | Quest automation: 4-step state machine — pathfinding wait → dialog advance → interaction/action button → quest row click. |
| `actions.py` | Mouse/keyboard actions via `pyautogui`. Translates window-relative coords to screen coords. |
| `ui_dashboard.py` | Tkinter floating overlay showing live status, action log, stats, Pause/Stop. |
| `calibrate.py` | **Run this first.** Visual self-test tool — captures the window, annotates every match, saves `debug_calibration.png`, reports pass/fail. |
| `save_template.py` | Helper to screenshot the RöX window for cropping new templates. |
| `game_data.py` | Static game-data tables parsed from Unity AssetBundles. Provides entrust NPC world positions and recurring quest task keys. Call `game_data.load_all()` once at startup. |
| `templates/` | PNG reference images used for template matching. |

## Critical rules — always follow these

### 1. Coordinates are always LOGICAL (1× not Retina 2×)
`capture.py` resizes the captured image back to logical size (`bounds["Width"] × bounds["Height"]`). Template match results `(cx, cy)` are therefore directly usable as `click(cx, cy, bounds)` arguments. **Never multiply or divide by 2.**

### 2. Click targets must come from template matches, not hardcoded pixels
The `click(cx, cy, bounds)` call in `quests.py` (and any future automation file) must use the `(cx, cy)` returned by `find_template(...)`. Hardcoded pixel offsets become wrong whenever the window moves or resizes. Relative-fraction fallbacks (`bounds["Width"] * 0.xx`) are acceptable only as a last resort.

### 3. Always run calibrate.py after changing templates or adding new automation
`calibrate.py` is the source of truth for whether click targets are correct. It opens an annotated PNG showing every click target overlaid on the live screenshot. If a circle is in the wrong place, fix the template crop — not the code coordinates.

### 4. Template matching threshold guidance
- **0.85+** — exact pixel match (same game session, no UI animation)
- **0.70–0.84** — recommended default; handles slight rendering differences
- **0.55–0.69** — use only for presence detection (not as a click target)
- **< 0.55** — unreliable; recrop the template instead of lowering the threshold

### 5. The window name has a Unicode NFD umlaut
`APP_WINDOW_NAME = "Ro\u0308X"` (o + combining umlaut U+0308, NOT the precomposed ö U+00F6). `capture.py` normalises both sides with `unicodedata.normalize("NFC", ...)` before comparing. Do not change this without also updating the comparison logic.

### 6. Virtual environment
All dependencies live in `.venv/`. Always use `.venv/bin/python` or activate with `source .venv/bin/activate`. The project also has a `venv/` folder — do not use it.

### 7. Thread safety
`ui_dashboard.py` runs Tkinter on the **main thread**. The automation loop runs on a **daemon thread**. All cross-thread communication goes through `Dashboard` methods which use `threading.Lock`. Never call Tkinter widget methods from the worker thread.

## Adding a new automation task (step-by-step)

1. **Capture a template**
   ```bash
   python save_template.py my_button_name
   ```
2. **Crop it** — Open `templates/my_button_name.png` in Preview → Tools → Adjust Size / Crop. Crop tightly around just the button. Save.

3. **Register it in `calibrate.py`** — Add an entry to `TARGETS`:
   ```python
   {
       "name":      "My Button",
       "template":  "my_button_name.png",
       "threshold": 0.75,
       "required":  True,
       "colour":    "yellow",
   }
   ```

4. **Run calibration** and verify the circle lands on the correct element:
   ```bash
   python calibrate.py
   ```

5. **Write the automation** in the appropriate module (or a new `my_feature.py`):
   ```python
   match = find_template(screenshot, "my_button_name.png", threshold=0.75)
   if match:
       cx, cy, conf = match
       click(cx, cy, bounds)
   ```

6. **Wire it into `main.py`** inside `automation_loop()`.

## Planned future automation
- [ ] Auto-collect daily quest rewards
- [ ] Auto-talk to NPCs when distance reaches 0 m
- [ ] Auto-enter dungeons / boss fights
- [ ] HP/SP potion auto-use when bars drop below threshold
- [ ] Party auto-accept

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
English, Thai, Vietnamese localization scripts are **compiled Lua 5.3 bytecode** — not plain text.  Do NOT attempt to parse them as text.  NPC display names in `data_npc_SceneNPC` are Chinese developer names (e.g. `委托板` = "Commission Board") or localization keys (e.g. `NpcName61001`).

### game_data.py
`game_data.py` wraps bundle access via `UnityPy`:
```python
from game_data import load_all, ENTRUST_NPC_WORLD_POS, RECURRING_QUEST_TASK_DESC
load_all()   # ~0.8 s, call once at startup
pos = ENTRUST_NPC_WORLD_POS[10101013]  # WorldPos(x=-8.57, z=-31.46, scene_id=1010, name='委托板')
```
- `ENTRUST_NPC_WORLD_POS` — 12 quest-board NPCs with Unity world (x, z) coords
- `RECURRING_QUEST_TASK_DESC` — 1701 recurring quest task localization keys
- Scene IDs encode zones: `1010`=Prontera, `1110`=Izlude, `1210`=Geffen area, `1310`, `1410`, etc.
- NPC uniqueId first-4-digits = scene_id: `10101013 → scene 1010`

### Assembly
`/Applications/RöX.app/Wrapper/RX.app/Data/Raw/Assembly-CSharp.dll.bytes` is a readable MZ/.NET DLL (HybridCLR).  3,886 types.  Key namespaces: `Dream.Data` (TaskModel, NPCModel), `Dream.Game.AutoPathing`, `Dream.Game.Com.RoleMoveComponent`, `Cc.Thedream.Mmo.Protocal.Task`, `XLua.CSObjectWrap.*`.

### Runtime injection — BLOCKED
Frida is blocked: app lacks `get-task-allow` entitlement, production-signed (`2Y3ZW5J4A7.com.play.rosea`).  `frida.PermissionDeniedError` will be thrown.  Do not attempt Frida injection.

### Accessibility API — USELESS
The game renders via Metal canvas.  `AXUIElement` only exposes `AXGroup`/`AXButton` with no text content.  Use OCR (`ocr.py`) for all text detection.

## macOS permissions required
- **Screen Recording** — System Settings → Privacy & Security → Screen Recording → Terminal (or Python)
- **Accessibility** — Same location → Accessibility → Terminal (for `pyautogui` mouse control)

These must be granted manually once. If capture returns a black image or clicks don't register, check these permissions first.
