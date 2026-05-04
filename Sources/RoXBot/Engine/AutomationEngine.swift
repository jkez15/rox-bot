import Foundation
import CoreGraphics
import ApplicationServices

/// Main automation controller.
///
/// Architecture:
///   FramePipeline (actor)  pushes CGImage frames at ~1.6 fps
///   → handleFrame          runs OCR + QuestScanner on each frame
///   → ActionQueue (actor)  deduplicates / rate-limits
///   → ClickEngine          delivers cursor-free click to game process
///   → DashboardPanel       updated on @MainActor for every frame
@MainActor
final class AutomationEngine {

    private let dashboard:   DashboardPanel
    private let pipeline   = FramePipeline()
    private let queue      = ActionQueue()
    private var running    = true
    private var frameNumber = 0
    /// Tracks whether the previous frame had an active dialog (for calibrator feedback).
    private var prevHadDialog = false

    init(dashboard: DashboardPanel) {
        self.dashboard = dashboard
    }

    // MARK: - Lifecycle

    func start() async {
        // Load offline game data (NPC positions, scene IDs from bundle_dumps)
        GameKnowledge.shared.load()
        CommissionData.shared.load()
        LogMonitor.shared.startMonitoring()
        await ClickCalibrator.shared.loadFromDisk()

        // Check Accessibility permission — required for CGEventPostToPid to work
        let trusted = AXIsProcessTrusted()
        if !trusted {
            dashboard.log("⚠️ Accessibility permission NOT granted — clicks may not register!")
            dashboard.log("→ System Settings → Privacy → Accessibility → add RöX Bot")
            print("[Engine] ⚠️ Accessibility NOT trusted")
        } else {
            dashboard.log("✅ Accessibility permission granted")
            print("[Engine] ✅ Accessibility trusted")
        }

        dashboard.log("Bot ready — press ▶ Start when RöX is open")
        dashboard.setStatus("Idle — press ▶ Start")

        await dashboard.waitForStart()
        guard !dashboard.stopRequested else { return }

        print("[Engine] ▶ Start pressed — entering pipeline")
        dashboard.log("▶ Bot started")
        await managePipeline()
    }

    func stop() {
        running = false
        Task {
            await pipeline.stop()
            await ClickCalibrator.shared.saveToDisk()
        }
    }

    // MARK: - Pipeline lifecycle (restart on game close/reopen)

    private func managePipeline() async {
        while running && !dashboard.stopRequested {
            // Wait for game
            var waited = false
            while !WindowCapture.isRoXRunning() && !dashboard.stopRequested {
                if !waited { print("[Engine] RöX not running — waiting…"); waited = true }
                dashboard.setStatus("Waiting for RöX…")
                dashboard.setAction("Game not running")
                try? await Task.sleep(for: .seconds(3))
            }
            if WindowCapture.isRoXRunning() { print("[Engine] RöX detected — starting stream") }
            guard !dashboard.stopRequested else { break }

            // Start stream
            do {
                try await pipeline.start { [weak self] image, bounds in
                    await self?.handleFrame(image: image, bounds: bounds)
                }
                dashboard.log("✅ Stream connected to RöX window")
                dashboard.setStatus("Running")
            } catch {
                print("[Engine] ❌ Stream error: \(error)")
                dashboard.log("⚠️ Stream error: \(error) — check Screen Recording permission")
                dashboard.setStatus("Capture failed — check Screen Recording permission")
                try? await Task.sleep(for: .seconds(5))
                continue
            }

            // Keep alive until game closes or stop requested
            while running && !dashboard.stopRequested && WindowCapture.isRoXRunning() {
                try? await Task.sleep(for: .seconds(5))
            }

            await pipeline.stop()
            await queue.reset()

            if !dashboard.stopRequested {
                dashboard.log("RöX closed — waiting for restart…")
            }
        }

        dashboard.setStatus("Stopped")
        dashboard.log("🛑 Bot stopped")
    }

    // MARK: - Per-frame processing (called by FramePipeline ~1.6 fps)

    private func handleFrame(image: CGImage, bounds: CGRect) async {
        guard !dashboard.paused, !dashboard.stopRequested else { return }

        dashboard.incrementCycle()
        frameNumber += 1

        // 1. OCR — runs on a detached background task, releases main actor
        let regions = await OCREngine.recognize(image, minConfidence: 0.30)
        print("[Engine] OCR found \(regions.count) regions: \(regions.prefix(5).map(\.text))")

        // 1a. Calibrator feedback: did the previous interact click produce a state change?
        let hasDialogNow = OCREngine.find(regions, pattern: Patterns.anyDialogOrInteraction,
                                           minConfidence: 0.35) != nil
        let stateChanged = !prevHadDialog && hasDialogNow
        await ClickCalibrator.shared.evaluateResult(stateChanged: stateChanged, currentFrame: frameNumber)
        prevHadDialog = hasDialogNow

        // 1b. Auto-potion — pixel-based HP/SP check (runs in autoPotion mode OR always)
        let potionAction = checkPotionNeeded(image: image, mode: dashboard.selectedMode)

        // 2. Build context from OCR + live game state
        let mode = dashboard.selectedMode
        let context = ScreenContext(
            regions:       regions,
            questState:    QuestScanner.parseSidebar(regions, mode: mode),
            isPathfinding: LogMonitor.shared.isPathfinding,
            currentScene:  LogMonitor.shared.currentSceneId,
            mode:          mode
        )

        // 3. Analyse
        let (quest, action) = QuestScanner.scan(context: context)

        // 4. Update dashboard
        if quest.hasActiveQuest {
            dashboard.setQuest(title: quest.title, step: quest.stepText, distance: quest.distance)
            let dist = quest.distance.map { "  |  \($0) m" } ?? ""
            let scene = context.currentScene.flatMap { SceneID.name[$0] }.map { " [\($0)]" } ?? ""
            dashboard.setStatus("\(quest.title)\(dist)\(scene)")
        } else {
            dashboard.setStatus("Running — monitoring…")
        }

        // 5. Potion takes highest priority — fire immediately if needed (no dedup coords)
        if let potion = potionAction {
            let shouldAct = await queue.shouldExecute(potion)
            if shouldAct {
                await queue.record(potion)
                print("[Engine] Action: \(potion)")
                await execute(potion, bounds: bounds)
                return  // skip quest action this frame; next frame will re-scan
            }
        }

        // 6. Deduplicate + rate limit quest action
        let shouldAct = await queue.shouldExecute(action)
        guard shouldAct else { return }
        await queue.record(action)

        // 7. Execute
        print("[Engine] Action: \(action)")
        await execute(action, bounds: bounds)
    }

    // MARK: - Action execution

    private func execute(_ action: ScanAction, bounds: CGRect) async {
        switch action {

        case .none:
            dashboard.setAction("Monitoring…")

        case .pathfinding:
            dashboard.setAction("🚶 Pathfinding — waiting")

        case .titleScreen(let cx, let cy):
            dashboard.setAction("[Boot] Entering game…")
            dashboard.log("[Boot] 'Tap to enter game' detected")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
            dashboard.incrementActions()
            try? await Task.sleep(for: .seconds(2))

        case .dialog(let cx, let cy, let label):
            dashboard.setAction("💬 Dialog: \(label)")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
            dashboard.incrementActions()

        case .dismiss(let cx, let cy, let label):
            dashboard.setAction("✖ Dismiss: \(label)")
            dashboard.log("✖ Dismiss '\(label)' @ (\(cx),\(cy))")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
            dashboard.incrementActions()

        case .interact(let cx, let cy, let label, let labelY):
            // From the reference screenshot the NPC sign card layout is:
            //   [  icon (magnifying glass)  ]   ← card centre, ~35px above text
            //   [       "Investigate"       ]   ← text at bottom of card (labelY)
            //   … NPC model body below …
            //
            // cy = icon centre (labelY - 35).  We fan 5 clicks to cover:
            //   1. Icon centre         (cy)          ← primary: the sign card itself
            //   2. Card top            (cy - 25)     ← upper portion of sign card
            //   3. Card bottom / text  (labelY)      ← the text word itself
            //   4. Just below text     (labelY + 30) ← below card, maybe NPC head
            //   5. NPC body estimate   (labelY + 80) ← further below for model collider
            let cardTop   = max(cy - 25, Zones.hudTopYMax + 5)
            let belowText = min(labelY + 30, Zones.gameWorldYMax - 5)
            let npcBody   = min(labelY + 80, Zones.gameWorldYMax - 5)

            dashboard.setAction("🖱 Interact: \(label)")
            dashboard.log("🖱 Interact '\(label)' iconY=\(cy) labelY=\(labelY) clicks: \(cardTop),\(cy),\(labelY),\(belowText),\(npcBody)")

            // Record attempt for calibrator learning
            await ClickCalibrator.shared.recordAttempt(
                label: label, cx: cx, labelY: labelY,
                offsetUsed: cy - labelY, frameNumber: frameNumber
            )

            // 5-click fan: icon card → text → NPC body
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)        // icon centre
            try? await Task.sleep(for: .milliseconds(200))
            await ClickEngine.click(wx: cx, wy: cardTop, windowBounds: bounds)   // card top
            try? await Task.sleep(for: .milliseconds(200))
            await ClickEngine.click(wx: cx, wy: labelY, windowBounds: bounds)    // text label
            try? await Task.sleep(for: .milliseconds(200))
            await ClickEngine.click(wx: cx, wy: belowText, windowBounds: bounds) // below card
            try? await Task.sleep(for: .milliseconds(200))
            await ClickEngine.click(wx: cx, wy: npcBody, windowBounds: bounds)   // NPC model
            dashboard.incrementActions()

        case .action(let cx, let cy, let label):
            dashboard.setAction("⚡ Action: \(label)")
            dashboard.log("⚡ '\(label)' @ (\(cx),\(cy))")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
            dashboard.incrementActions()

        case .navigate(let cx, let cy, let label):
            dashboard.setAction("🗺 Navigate via '\(label)'")
            dashboard.log("🗺 Navigate '\(label)' @ (\(cx),\(cy))")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
            dashboard.incrementActions()
            // Wait for pathfinding to start before next scan cycle
            try? await Task.sleep(for: .seconds(2))

        case .usePotion(let kind):
            let key   = kind == .hp ? Zones.hpPotionKey : Zones.spPotionKey
            let label = kind == .hp ? "HP" : "SP"
            dashboard.setAction("🧪 Potion: \(label)")
            dashboard.log("🧪 \(label) potion (key \(key))")
            pressKey(key)
            dashboard.incrementActions()
        }
    }

    // MARK: - HP/SP bar pixel analysis

    /// Reads the HP and SP bars from the captured frame and returns a `.usePotion` action
    /// if either bar is below its threshold. Returns nil if both bars are fine.
    ///
    /// **ONLY fires in `.autoPotion` mode.** Potion use is completely suppressed in all
    /// other modes (mainQuest, dailyQuests, etc.) because the bar coordinates in Zones.swift
    /// are estimates that must be calibrated per-machine before use. If the coordinates are
    /// wrong, barFillRatio returns 0.0 (no colored pixels found) which always looks like
    /// "critically low" and would spam the hotkey every frame.
    private func checkPotionNeeded(image: CGImage, mode: AutomationMode) -> ScanAction? {
        // Hard gate: do nothing unless the user has explicitly selected Auto-Potion mode.
        guard mode == .autoPotion else { return nil }

        let hpFill = barFillRatio(image: image,
                                   x1: Zones.hpBarX1, y1: Zones.hpBarY1,
                                   x2: Zones.hpBarX2, y2: Zones.hpBarY2,
                                   channel: .red)
        // Sanity: fill == 0.0 means no red pixels at all — bar coords are wrong or HUD is
        // hidden (loading screen, cutscene). Skip rather than false-fire.
        if let fill = hpFill, fill > 0.02, fill < Zones.hpPotionThreshold {
            print("[Engine] HP bar at \(Int(fill * 100))% — using HP potion")
            return .usePotion(kind: .hp)
        }

        // SP potion
        let spFill = barFillRatio(image: image,
                                   x1: Zones.spBarX1, y1: Zones.spBarY1,
                                   x2: Zones.spBarX2, y2: Zones.spBarY2,
                                   channel: .blue)
        if let fill = spFill, fill > 0.02, fill < Zones.spPotionThreshold {
            print("[Engine] SP bar at \(Int(fill * 100))% — using SP potion")
            return .usePotion(kind: .sp)
        }

        return nil
    }

    private enum Channel { case red, blue }

    /// Samples pixels in the given rect and returns the fraction that are "lit" in the target channel.
    /// Returns nil if the image region is inaccessible.
    private func barFillRatio(image: CGImage, x1: Int, y1: Int, x2: Int, y2: Int,
                               channel: Channel) -> Float? {
        let w = x2 - x1
        let h = y2 - y1
        guard w > 0, h > 0 else { return nil }

        // Crop to the bar region
        guard let cropped = image.cropping(to: CGRect(x: x1, y: y1, width: w, height: h))
        else { return nil }

        // Render into a raw RGBA bitmap
        let bw = cropped.width
        let bh = cropped.height
        let bytesPerPixel = 4
        let bytesPerRow   = bw * bytesPerPixel
        var pixelData = [UInt8](repeating: 0, count: bh * bytesPerRow)

        guard let ctx = CGContext(
            data: &pixelData,
            width: bw, height: bh,
            bitsPerComponent: 8,
            bytesPerRow: bytesPerRow,
            space: CGColorSpaceCreateDeviceRGB(),
            bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue
        ) else { return nil }

        ctx.draw(cropped, in: CGRect(x: 0, y: 0, width: bw, height: bh))

        var litCount = 0
        var visibleCount = 0
        let total = bw * bh
        for i in 0..<total {
            let base = i * bytesPerPixel
            let r = Int(pixelData[base])
            let g = Int(pixelData[base + 1])
            let b = Int(pixelData[base + 2])
            // Count pixels with any visible colour (not dark background).
            let brightness = r + g + b
            if brightness > 80 { visibleCount += 1 }

            switch channel {
            case .red:
                // HP bar: red dominant (r > 100, r > g+40, r > b+40)
                if r > 100 && r > g + 40 && r > b + 40 { litCount += 1 }
            case .blue:
                // SP bar: blue dominant (b > 80, b > r+30, b > g+10)
                if b > 80 && b > r + 30 && b > g + 10 { litCount += 1 }
            }
        }

        // Sanity check: the sampled region must contain a meaningful number of
        // visible (non-dark) pixels. If < 15% are visible the HUD bar isn't in
        // this region (loading screen, wrong coordinates, etc.) → inconclusive.
        let visibleRatio = Float(visibleCount) / Float(max(total, 1))
        if visibleRatio < 0.15 {
            return nil   // region is mostly dark — no bar detected
        }

        return Float(litCount) / Float(max(total, 1))
    }

    // MARK: - Key press helper

    private func pressKey(_ keyCode: CGKeyCode) {
        let src = CGEventSource(stateID: .hidSystemState)
        let down = CGEvent(keyboardEventSource: src, virtualKey: keyCode, keyDown: true)
        let up   = CGEvent(keyboardEventSource: src, virtualKey: keyCode, keyDown: false)
        down?.post(tap: .cghidEventTap)
        Thread.sleep(forTimeInterval: 0.05)
        up?.post(tap: .cghidEventTap)
    }
}
