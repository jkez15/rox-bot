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
        // Scene change
        if line.contains("LoadScene") || line.contains("EnterScene") {
            // Extract a 4-digit scene ID (e.g. 1010, 1110 …)
            let tokens = line.components(separatedBy: CharacterSet.decimalDigits.inverted)
            if let idStr = tokens.first(where: { $0.count == 4 }), let id = Int(idStr) {
                currentSceneId = id
                print("[LogMonitor] Scene → \(id)")
            }
        }

        // Pathfinding
        if line.contains("AutoPath") || line.lowercased().contains("pathfind") {
            if line.contains("Start") || line.contains("Begin") || line.contains("Active") {
                isPathfinding = true
            } else if line.contains("End") || line.contains("Stop") || line.contains("Arriv") {
                isPathfinding = false
            }
        }
    }
}
