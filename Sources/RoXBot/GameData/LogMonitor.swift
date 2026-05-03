import Foundation

/// Real-time Unity Player.log tail monitor.
/// Runs on a background Task; writes to properties that any thread can read.
/// (Properties are written from one background Task, read from the main actor —
/// benign eventual-consistency; a stale read at worst skips one cycle of click suppression.)
final class LogMonitor {

    static let shared = LogMonitor()

    private let logPath = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent(
            "Library/Containers/com.play.rosea/Data/Library/Logs/Unity/Player.log"
        )

    // Readable from any context — updated only by the background task
    private(set) var currentSceneId: Int?  = nil
    private(set) var isPathfinding:  Bool  = false

    private var monitorTask: Task<Void, Never>?

    private init() {}

    func startMonitoring() {
        guard monitorTask == nil else { return }
        monitorTask = Task.detached(priority: .background) { [weak self] in
            await self?.tailLog()
        }
    }

    func stop() {
        monitorTask?.cancel()
        monitorTask = nil
    }

    // MARK: - Private

    private func tailLog() async {
        guard FileManager.default.fileExists(atPath: logPath.path) else {
            print("[LogMonitor] Player.log not found — log monitoring disabled")
            return
        }
        guard let fh = FileHandle(forReadingAtPath: logPath.path) else {
            print("[LogMonitor] Cannot open Player.log")
            return
        }

        // Only watch new entries
        fh.seekToEndOfFile()
        print("[LogMonitor] Watching \(logPath.lastPathComponent)…")

        while !Task.isCancelled {
            let data = fh.availableData
            if !data.isEmpty, let text = String(data: data, encoding: .utf8) {
                for line in text.components(separatedBy: "\n") where !line.isEmpty {
                    processLine(line)
                }
            }
            try? await Task.sleep(for: .milliseconds(500))
        }

        fh.closeFile()
    }

    private func processLine(_ line: String) {
        // ── Scene change ─────────────────────────────────────────────────
        // Real log: "C# Enter Scene: <hostName>  <sceneId>"
        // e.g.    : "C# Enter Scene: Prontera  1010"
        if line.contains("C# Enter Scene:") {
            let tokens = line.components(separatedBy: CharacterSet.decimalDigits.inverted)
            // Pick the last 4-digit number — that's the sceneId
            if let idStr = tokens.last(where: { $0.count == 4 }), let id = Int(idStr) {
                currentSceneId = id
                print("[LogMonitor] Scene → \(id) (\(SceneID.name[id] ?? "unknown"))")
            }
        }
        if line.contains("C# Leave Scene") {
            // Don't clear sceneId — we want to remember where we were
            print("[LogMonitor] Leaving scene")
        }

        // ── Autopathfinding ──────────────────────────────────────────────
        // Real log start: "AutoPath:<toSceneId>,<startPos>,<target>"
        // Real log end:   "AutoPathing Completed"
        // Also: XLogger.Log("AutoPath:") at line 314821
        if line.hasPrefix("AutoPath:") || line.contains("AutoPath:") {
            isPathfinding = true
            print("[LogMonitor] Pathfinding started")
        }
        if line.contains("AutoPathing Completed") {
            isPathfinding = false
            print("[LogMonitor] Pathfinding completed")
        }
        // AutoPath stopped by user or error
        if line.contains("StopAutoPath") || line.contains("AutoPath Error") || line.contains("AutoPathError") {
            isPathfinding = false
            print("[LogMonitor] Pathfinding stopped")
        }
    }
}
