import Foundation
import CoreGraphics

/// Deduplicates and rate-limits actions produced by QuestScanner.
///
/// Rules:
///   - Same action type + same coords (within `dedupeRadius`) within `dedupeWindow` → skip
///   - Any two clicks closer together than `minInterval` → skip
///   - `.none` and `.pathfinding` (no-click actions) are always allowed through
actor ActionQueue {

    // ── Tunables ─────────────────────────────────────────────────────────
    private let minInterval:   Duration = .milliseconds(800)
    private let dedupeWindow:  Duration = .seconds(10)
    private let dedupeRadius:  Int      = 40

    // ── State ─────────────────────────────────────────────────────────────
    private var lastKind: ActionKind               = .none
    private var lastCX:   Int                      = 0
    private var lastCY:   Int                      = 0
    private var lastTime: ContinuousClock.Instant  = .now - .seconds(60)

    // MARK: - Public API

    /// Returns `true` if the engine should execute this action.
    func shouldExecute(_ action: ScanAction) -> Bool {
        let kind = ActionKind(action)
        guard kind.isClick else { return true }   // .none / .pathfinding → always pass

        let now = ContinuousClock.now
        let (cx, cy) = action.coords

        // Rate limit: too soon after last click?
        if now - lastTime < minInterval { return false }

        // Deduplicate: same kind + same location + recent?
        if kind == lastKind,
           abs(cx - lastCX) < dedupeRadius,
           abs(cy - lastCY) < dedupeRadius,
           now - lastTime   < dedupeWindow {
            return false
        }

        return true
    }

    /// Record that an action was executed.  Call immediately before executing.
    func record(_ action: ScanAction) {
        let (cx, cy) = action.coords
        lastKind = ActionKind(action)
        lastCX   = cx
        lastCY   = cy
        lastTime = .now
    }

    /// Reset state (e.g. after a scene change or game restart).
    func reset() {
        lastKind = .none
        lastCX   = 0
        lastCY   = 0
        lastTime = .now - .seconds(60)
    }
}

// MARK: - Helpers

private enum ActionKind: Equatable {
    case none, pathfinding, titleScreen, dialog, interact, action, navigate

    init(_ s: ScanAction) {
        switch s {
        case .none:        self = .none
        case .pathfinding: self = .pathfinding
        case .titleScreen: self = .titleScreen
        case .dialog:      self = .dialog
        case .interact:    self = .interact
        case .action:      self = .action
        case .navigate:    self = .navigate
        }
    }

    /// True if this action actually sends a click.
    var isClick: Bool { self != .none && self != .pathfinding }
}

private extension ScanAction {
    var coords: (Int, Int) {
        return coord ?? (0, 0)
    }
}
