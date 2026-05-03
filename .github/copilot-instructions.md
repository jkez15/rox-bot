# RöX Automation Bot — Copilot Instructions

> **⚠️ IMPORTANT — Read this first.**
> The project was **fully rewritten from Python to Swift** (Swift 6, SPM, macOS 14+).
> All Python files (`main.py`, `quests.py`, etc.) are **gone**. Ignore any Python references below.
> The bot is now a native macOS Swift app: `RoXBot.app`.

---

## Two-machine workflow

This project is developed across **two machines**:

| Machine | Role |
|---|---|
| **Mac with RöX** | Live testing, OCR calibration, template capture, bug diagnosis. All screen captures, clicks, and OCR runs happen here. |
| **Other machine (no RöX)** | All code writing, architecture, logic improvements. Cannot run the bot. Windows/Linux fine. |

### Rules for the non-Mac machine
- **Never try to run** `bash run.sh`, `bash build.sh`, or any Swift/macOS tooling — it won't compile on Windows.
- **Do write** Swift code, improve algorithms, fix bugs, add new automation features.
- **Do read** `bundle_dumps/*.txt` — plain text game data, fully readable on any machine.
- **Do read** `decompiled/Assembly-CSharp.decompiled.cs` — full decompiled C# of the game engine (~500k lines). Use grep/search to navigate.
- All coordinate zone constants live in `Sources/RoXBot/Quest/Zones.swift`.
- The Mac user will paste your Swift code, run `bash run.sh`, and report what happens.

---

## Project purpose
A **macOS Swift automation bot** for the game **RöX** (`com.play.rosea`, process `RX`).
Captures the game window, runs Apple Vision OCR on each frame, identifies quest state and UI buttons, and sends invisible mouse clicks to automate main quests.

---

## Build & run (Mac only)

```bash
# One-time certificate setup (do this once per Mac — keeps TCC permissions stable)
bash setup_signing.sh

# Build + kill old instance + relaunch (use this every time)
bash run.sh

# Build only (no relaunch)
bash build.sh
```

App bundle: `RoXBot.app/` — binary at `RoXBot.app/Contents/MacOS/RoXBot`
Bundle ID: `com.roxbot.app`
Signing: `RoXBotSign` self-signed cert in login keychain. Stable across all rebuilds — TCC permissions persist.

### macOS permissions required (live Mac only)
Both must be granted in **System Settings → Privacy & Security**:
- **Screen Recording** → add `RoXBot.app` → toggle ON
- **Accessibility** → add `RoXBot.app` → toggle ON

After `setup_signing.sh`, you grant these **once and never again** (cert is stable).

---

## Project structure (Swift SPM)

```
Sources/RoXBot/
├── main.swift                   Entry point — NSApp + AppDelegate
├── AppDelegate.swift            Initialises DashboardPanel + AutomationEngine
│
├── Actions/
│   └── ClickEngine.swift        Injects clicks via CGEventPost(.cghidEventTap)
│
├── Capture/
│   ├── WindowCapture.swift      Finds RöX SCWindow (handles NFD umlaut)
│   └── FramePipeline.swift      SCScreenshotManager polling at 700 ms → CGImage frames
│
├── Engine/
│   ├── AutomationEngine.swift   Main loop: OCR → ScreenContext → QuestScanner → ActionQueue → ClickEngine
│   └── ActionQueue.swift        Deduplicates clicks (10 s window, 40 px radius, 800 ms min interval)
│
├── GameData/
│   ├── GameKnowledge.swift      Parses bundle_dumps/npc_scene.txt → 1914 NPCs with world coords
│   └── LogMonitor.swift         Tails Unity Player.log — detects scene changes + pathfinding
│
├── OCR/
│   ├── OCREngine.swift          VNRecognizeTextRequest (Apple Vision) — ~190 ms/frame
│   └── TextRegion.swift         OCR result: text, x, y, w, h, confidence, cx, cy
│
├── Quest/
│   ├── Patterns.swift           All OCR regex patterns (dialogChoice, interaction, action, …)
│   ├── QuestScanner.swift       5-step state machine — pure function, no I/O, no async
│   ├── ScanAction.swift         ScanAction enum + QuestState + ScreenContext types
│   └── Zones.swift              Screen zone constants
│
└── UI/
    └── DashboardPanel.swift     NSPanel floating overlay — always on top
```

---

## Data flow (one iteration per frame)

```
FramePipeline (actor, 700 ms poll)
  └─ SCScreenshotManager.captureImage → CGImage (1092×847 logical px)
        ↓
AutomationEngine.handleFrame()
  ├─ OCREngine.recognize()           → [TextRegion]   (~190 ms, detached task)
  ├─ LogMonitor.shared               → isPathfinding, currentSceneId
  ├─ ScreenContext(regions, parsedSidebar, isPathfinding, currentScene)
  ├─ QuestScanner.scan(context)      → (QuestState, ScanAction)
  ├─ ActionQueue.shouldExecute()     → Bool (dedup / rate-limit)
  └─ ClickEngine.click(wx, wy)       → CGEventPost(.cghidEventTap)
```

---

## QuestScanner — 5-step state machine

`QuestScanner.scan(context:)` returns exactly **one** `ScanAction` per frame.

| Priority | Condition | Action |
|---|---|---|
| 0 | OCR sees "Tap to enter game" | `.titleScreen` — click |
| 1 | `isPathfinding` (LogMonitor) **OR** OCR "Pathfinding" text | `.pathfinding` — wait, do nothing |
| 2 | Dialog button visible (`Next`, `OK`, `Yes`, `Agree`, `Continue`, `Got it`, `Bye`, `Skip`) | `.dialog` — click it |
| 3 | NPC/object interaction button visible in game world (`Examine`, `Inspect`, `Talk`, `Interact`, `Touch`, `Operate`, `Probe`, `Approach`, `Greet`, `Disguise`, `Investigate`) | `.interact` — click icon above label |
| 4 | World action button visible (`Collect`, `Enter`, `Activate`, `Use`, `Give`, `Report`, `Deliver`, `Complete`, `Claim`, `Challenge`, `Summon`) | `.action` — click it |
| 5 | `[Main]`/`[Sub]`/`[Daily]`/`[Guild]` quest row in sidebar AND distance > 5 m | `.navigate` — tap quest row |

**Zone rules (strictly enforced):**
- Dialog buttons: `cx > 260 && cy > 300 && cy < 770`
- Interaction/action buttons: `cx > 260 && cy > 300 && cy < 620` (game world only)
- Never click `cy >= 620` unless a clearly labelled button OCR-matches there
- `questRow` step skips if `distance ≤ 5 m` — prevents re-pathing when already at NPC

---

## Screen layout (1092 × 847 logical pixels at runtime)

```
┌──────────────────────────────────────────────────────────────────────┐
│  y < 300    TOP HUD: HP/SP bars, minimap, Backpack btn               │
├────────┬─────────────────────────────────────────────────────────────┤
│        │                                                             │
│ QUEST  │         GAME WORLD  (300 ≤ y < 620)                        │
│ PANEL  │   NPC buttons, action buttons, dialog choice buttons        │
│ x<260  │                                                             │
│        ├─────────────────────────────────────────────────────────────┤
│        │   DIALOG / CHAT ZONE  (620 ≤ y < 770) — never click here   │
├────────┴─────────────────────────────────────────────────────────────┤
│  y ≥ 770    BOTTOM HUD: level bar, chat input                        │
└──────────────────────────────────────────────────────────────────────┘
```

Zone constants in `Sources/RoXBot/Quest/Zones.swift`:
```swift
static let questPanelXMax = 260
static let hudTopYMax     = 300
static let gameWorldYMax  = 620
static let dialogYMin     = 620
static let dialogYMax     = 770
```

---

## Click engine

**Method**: `CGEventPost(.cghidEventTap)` — injects at HID level, Unity receives it.

```
1. rox.activate(options: .activateIgnoringOtherApps)  // Unity must have focus
2. sleep 150 ms
3. CGEvent leftMouseDown → post(tap: .cghidEventTap)
4. sleep 60 ms
5. CGEvent leftMouseUp   → post(tap: .cghidEventTap)
6. CGWarpMouseCursorPosition(saved)                    // snap cursor back invisibly
7. sleep 80 ms
8. previousApp.activate()                             // restore user's focus
```

**Why not `CGEventPostToPid`?** Unity/Catalyst ignores Mach-port injected events entirely.
**Coordinates**: Always **logical pixels** (1× not Retina 2×). FramePipeline captures at logical resolution so match coords → click coords are 1:1.

---

## OCR engine

```swift
let regions = await OCREngine.recognize(image, minConfidence: 0.30)
let r = OCREngine.find(regions, pattern: #"\bNext\b"#, minConfidence: 0.40)
// r: TextRegion? with .text, .cx, .cy, .width, .height, .confidence
```

- Apple Vision `VNRecognizeTextRequest` — macOS only, no model download, no GPU
- `usesLanguageCorrection = false` — preserves `[Main]`, `[Sub]`, exact button text
- Confidence: 0.9–1.0 for clean UI text; 0.5–0.8 for styled buttons
- Vision uses bottom-left origin — `OCREngine` flips to top-left before returning

---

## GameKnowledge — offline NPC database

```swift
GameKnowledge.shared.load()   // called once at AutomationEngine.start()

let npc = GameKnowledge.shared.npc(uniqueId: 10101013)
// SceneNPC(uniqueId: 10101013, sceneId: 1010, x: -8.57, z: -31.46, name: "委托板")

let pronteraNPCs = GameKnowledge.shared.npcsInScene(1010)
```

NPC uniqueId first-4-digits = sceneId:
- `1010` = Prontera, `1110` = Izlude, `1210` = Geffen, `1310` = Morroc, `1410` = Alberta

Source: `bundle_dumps/npc_scene.txt` — 1,917 lines, committed to git, **readable on any machine**.

---

## LogMonitor — Unity Player.log integration

```swift
LogMonitor.shared.startMonitoring()
LogMonitor.shared.isPathfinding    // Bool
LogMonitor.shared.currentSceneId  // Int?
```

**Verified log strings** (from `decompiled/Assembly-CSharp.decompiled.cs`):

| Game event | Log line | Source line |
|---|---|---|
| Scene entered | `"C# Enter Scene: <name>  <sceneId>"` | 267131 |
| Scene left | `"C# Leave Scene: "` | 267137 |
| Pathfinding started | `"AutoPath:<toSceneId>,<startPos>,<target>"` | 314821 |
| Pathfinding completed | `"AutoPathing Completed"` | 315063 |

Log path: `~/Library/Containers/com.play.rosea/Data/Library/Logs/Unity/Player.log`
⚠️ Only exists on the Mac with the running game.

---

## bundle_dumps — offline game data (readable on any machine)

| File | Contents |
|---|---|
| `npc_scene.txt` | 1,914 NPCs — sceneId, uniqueId, world x/z, Chinese name |
| `npc_raw.txt` | Full NPC Lua table dump (3.9 MB) |
| `recurring_quests_raw.txt` | 1,701 commission board quest tasks (907 KB) |
| `entrust_raw.txt` | Commission board NPC assignments per scene |
| `waypoints_raw.txt` | Route waypoint data |

---

## decompiled/Assembly-CSharp.decompiled.cs — game C# source

Full decompiled game engine (~500k lines). Key search terms:

```bash
# What the game actually logs to Player.log:
grep -n "XLogger.Log" Assembly-CSharp.decompiled.cs

# Quest/task state machine:
grep -n "QuestState\|TaskModel\|NPCTaskState\|NpcTaskState" Assembly-CSharp.decompiled.cs

# Autopathfinding:
grep -n "AutoPath\|IsAutoPathing\|StartAutoPath\|StopAutoPath" Assembly-CSharp.decompiled.cs

# UI window classes:
grep -n "public class UI_" Assembly-CSharp.decompiled.cs
```

Key findings already extracted:
- `UI_AutoPathing` class — the pathfinding HUD
- `StartAutoPathAI(Vector3 targetPos, float distance, ...)` — triggers autopath
- `NPCTaskStateChangedEvent` — fired on NPC interaction state change
- `XLogger.Log("C# Enter Scene: " + hostName + "  " + sceneId)` — line 267131

---

## Known bugs fixed — do not re-introduce

| Bug | Root cause | Fix applied |
|---|---|---|
| Bot clicks constantly with no dialog | Chat zone always has text → "text present" fallback fired every scan | Removed fallback entirely from `dialogButton()` |
| False dialog clicks on HUD menus | `Close`, `Done`, `Start`, `Return` had no zone check | Removed from `dialogChoice`; kept only unambiguous words + zone check `cy > 300 && cy < 770` |
| False NPC interaction clicks | `Open`, `Read`, `Look`, `Search`, `Press` matched tooltips/map labels | Removed generic English words from `interaction` patterns |
| Quest row re-tapped when at NPC | `navigate` step had no distance guard | Skips if `distance ≤ 5 m` |
| Pathfinding interrupted mid-walk | Only checked OCR text which can scroll off screen | Now checks BOTH `LogMonitor.isPathfinding` AND OCR text |
| TCC permissions reset on every rebuild | Ad-hoc `--sign -` changes code identity each build | `setup_signing.sh` creates stable `RoXBotSign` cert once |
| Clicks not registering in Unity | `CGEventPostToPid` ignored by Unity/Catalyst | Switched to `CGEventPost(.cghidEventTap)` |
| Screen capture gave empty frames | SCStream never delivered buffers (Unity window not changing) | Switched to `SCScreenshotManager.captureImage` polling |

---

## Planned / not yet implemented

- [ ] **HP/SP auto-potion** — read HP bar fill (pixel ratio in region `0–260, 0–60`); press hotkey when < threshold
- [ ] **Daily reward auto-collect** — detect golden chest popup; click Collect
- [ ] **Commission board automation** — use `recurring_quests_raw.txt` + `entrust_raw.txt` to accept and complete recurring quests
- [ ] **Sub/Daily/Guild quest handling** — currently only `[Main]` quests are navigated
- [ ] **Scene-aware NPC routing** — use `GameKnowledge.npc(uniqueId:)` for per-scene routing instead of relying solely on the game's autopath
- [ ] **Party auto-accept** — detect party invite popup; click Accept
- [ ] **Auto-enter dungeons** — detect entry prompt; click Enter/Challenge
- [ ] **Distance = 0 fast-interact** — when sidebar shows `0 m`, immediately trigger Examine without waiting for next frame

---

## Adding a new automation feature (for the non-Mac machine)

1. **Get the exact button label** from the Mac user — what text does OCR see on the button?
2. **Add the pattern** to `Sources/RoXBot/Quest/Patterns.swift` in the right array:
   - NPC/object button → `interaction` array
   - Dialog response → `dialogChoice` array  
   - World action → `action` array
3. **If special logic is needed** (e.g. only act in scene 1010, or only when distance < X), add a new step in `QuestScanner.swift` between the existing steps.
4. Ask the Mac user to run `bash run.sh` and report `[Engine] Action:` terminal lines.

---

## Game engine internals

- **Engine**: Unity 2019.4.41f1 + HybridCLR + XLua
- **Platform**: iOS app via macOS Catalyst (`RöX.app/Wrapper/RX.app`)
- **Bundle ID**: `com.play.rosea`
- **NFD umlaut**: Window title is `"Ro\u0308X"` (o + U+0308 combining char, NOT ö U+00F6)
- **Runtime injection**: Frida BLOCKED — no `get-task-allow` entitlement. Do not attempt.
- **Accessibility API**: Useless — Unity renders via Metal, AXUIElement has no text content.
- **English localization**: Compiled Lua 5.3 bytecode — not readable as plain text.
- **Player.log**: Does not exist until the game has been launched on that specific Mac.
- **MMKV store**: `Documents/mmkv/mmkv.default` — binary format, likely contains quest progress but not yet decoded.