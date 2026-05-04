import Foundation

/// Lightweight adaptive learning system for click offset calibration.
///
/// Tracks whether interaction clicks result in game state changes (dialog opening,
/// scene transition, etc.) and adjusts the vertical offset between OCR text positions
/// and actual NPC model collider positions over time.
///
/// Learning cycle:
///   1. Scanner detects "Examine" text at (cx, labelY)
///   2. Engine clicks at (cx, labelY + learnedOffset)
///   3. Next frame: if game state changed (dialog appeared, pathfinding started) → success
///   4. If no change after N frames → failure; adjust offset for next attempt
///
/// Persists learned offsets to disk so the bot improves across restarts.
actor ClickCalibrator {

    static let shared = ClickCalibrator()

    // MARK: - Learned state

    /// Current best vertical offset from OCR label → NPC model click point.
    /// Positive = below text (toward NPC body). Starts at default estimate.
    private var interactOffset: Int = 60

    /// Tracks pending interaction attempts awaiting confirmation.
    private var pendingInteract: PendingClick?

    /// History of successful offsets — used to compute weighted average.
    private var successHistory: [OffsetRecord] = []

    /// Maximum history size before pruning oldest entries.
    private let maxHistory = 50

    // MARK: - Types

    private struct PendingClick {
        let label: String
        let cx: Int
        let labelY: Int
        let offsetUsed: Int
        let frameNumber: Int
    }

    private struct OffsetRecord: Codable {
        let offset: Int
        let timestamp: TimeInterval
    }

    // MARK: - Public API

    /// Returns the current best offset to add to labelY for NPC body clicks.
    /// Positive = click BELOW the text (where the model is).
    func bestOffset() -> Int {
        return interactOffset
    }

    /// Called when an interaction click is about to fire.
    func recordAttempt(label: String, cx: Int, labelY: Int, offsetUsed: Int, frameNumber: Int) {
        pendingInteract = PendingClick(
            label: label, cx: cx, labelY: labelY,
            offsetUsed: offsetUsed, frameNumber: frameNumber
        )
    }

    /// Called each frame to check if a pending click was successful.
    /// `stateChanged` = true if a dialog appeared, pathfinding started, or scene changed
    /// since the click was fired. `currentFrame` = current frame number.
    func evaluateResult(stateChanged: Bool, currentFrame: Int) {
        guard let pending = pendingInteract else { return }

        // Wait at least 2 frames for the game to respond
        guard currentFrame - pending.frameNumber >= 2 else { return }

        if stateChanged {
            // Click worked — reinforce this offset
            let record = OffsetRecord(offset: pending.offsetUsed, timestamp: Date().timeIntervalSince1970)
            successHistory.append(record)
            if successHistory.count > maxHistory {
                successHistory.removeFirst(successHistory.count - maxHistory)
            }
            recalculateOffset()
            print("[Calibrator] ✅ offset \(pending.offsetUsed) worked for '\(pending.label)' — learned offset now \(interactOffset)")
        } else if currentFrame - pending.frameNumber >= 5 {
            // 5 frames passed with no state change — click likely missed
            // Slightly adjust offset for next attempt (try a bit further down)
            let adjusted = pending.offsetUsed + 15
            if adjusted < 200 {  // don't go too far
                interactOffset = adjusted
                print("[Calibrator] ❌ offset \(pending.offsetUsed) missed for '\(pending.label)' — trying \(interactOffset) next")
            }
            pendingInteract = nil
        }

        if stateChanged {
            pendingInteract = nil
        }
    }

    /// Reset learned state (e.g. on game restart).
    func reset() {
        pendingInteract = nil
        // Keep successHistory — learned offsets are still valid after restart
    }

    // MARK: - Persistence

    func loadFromDisk() {
        guard let data = try? Data(contentsOf: calibrationFileURL()),
              let records = try? JSONDecoder().decode([OffsetRecord].self, from: data)
        else { return }
        successHistory = records
        recalculateOffset()
        print("[Calibrator] Loaded \(records.count) calibration records, offset = \(interactOffset)")
    }

    func saveToDisk() {
        guard let data = try? JSONEncoder().encode(successHistory) else { return }
        try? data.write(to: calibrationFileURL(), options: .atomic)
    }

    // MARK: - Internal

    private func recalculateOffset() {
        guard !successHistory.isEmpty else { return }
        // Weighted average: recent successes count more
        let now = Date().timeIntervalSince1970
        var weightedSum = 0.0
        var totalWeight = 0.0
        for record in successHistory {
            let age = now - record.timestamp
            let weight = 1.0 / (1.0 + age / 3600.0)  // decay over hours
            weightedSum += Double(record.offset) * weight
            totalWeight += weight
        }
        if totalWeight > 0 {
            interactOffset = Int(weightedSum / totalWeight)
        }
    }

    private func calibrationFileURL() -> URL {
        let appSupport = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask).first!
        let dir = appSupport.appendingPathComponent("RoXBot")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent("click_calibration.json")
    }
}
