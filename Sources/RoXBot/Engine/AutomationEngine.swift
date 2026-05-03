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

    init(dashboard: DashboardPanel) {
        self.dashboard = dashboard
    }

    // MARK: - Lifecycle

    func start() async {
        LogMonitor.shared.startMonitoring()

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
        Task { await pipeline.stop() }
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

        // 1. OCR — runs on a detached background task, releases main actor
        let regions = await OCREngine.recognize(image, minConfidence: 0.30)
        print("[Engine] OCR found \(regions.count) regions: \(regions.prefix(5).map(\.text))")

        // 2. Analyse
        let (info, action) = QuestScanner.scan(regions: regions)

        // 3. Update dashboard
        if let info {
            dashboard.setQuest(title: info.title, step: info.stepText, distance: info.distance)
            let dist = info.distance.map { "  |  \($0) m" } ?? ""
            dashboard.setStatus("\(info.title)\(dist)")
        } else {
            dashboard.setStatus("Running — monitoring…")
        }

        // 4. Deduplicate + rate limit
        let shouldAct = await queue.shouldExecute(action)
        guard shouldAct else { return }
        await queue.record(action)

        // 5. Execute
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

        case .interact(let cx, let cy, let label):
            dashboard.setAction("🖱 Interact: \(label)")
            dashboard.log("🖱 Interact '\(label)' @ (\(cx),\(cy))")
            await ClickEngine.click(wx: cx, wy: cy, windowBounds: bounds)
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
        }
    }
}
