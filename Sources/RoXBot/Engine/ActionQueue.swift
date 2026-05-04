import Foundation
import CoreGraphics

/// Deduplicates and rate-limits actions produced by QuestScanner.
///
/// Rules:
///   - Same action type + same coords (within `dedupeRadius`) within `dedupeWindow(for:)` → skip
///   - Any two clicks closer together than `minInterval` → skip
///   - `.none` and `.pathfinding` (no-click actions) are always allowed through
///   - `.dismiss` always passes (popups must always be closeable)
actor ActionQueue {

    // ── Tunables ─────────────────────────────────────────────────────────
    private let minInterval:  Duration = .milliseconds(800)
    private let dedupeRadius: Int      = 40

    /// Per-kind dedup windows.
    /// `.dialog` is short so multi-page NPC dialogs ("Next" at same coords 3–8×) page through quickly.
    private func dedupeWindow(for kind: ActionKind) -> Duration {
        switch kind {
        case .dialog:                  return .milliseconds(1500)
        case .dismiss:                 return .milliseconds(500)
        case .interact:                return .seconds(3)
        case .action:                  return .seconds(5)
        case .navigate:                return .seconds(15)
        case .usePotion:               return .seconds(8)   // cooldown between presses
        default:                       return .seconds(10)
        }
    }

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

        // .dismiss must always fire — popups can reappear at the same coords
        guard kind != .dismiss else { return true }

        // Deduplicate: same kind + same location + within per-kind window?
        if kind == lastKind,
           abs(cx - lastCX) < dedupeRadius,
           abs(cy - lastCY) < dedupeRadius,
           now - lastTime   < dedupeWindow(for: kind) {
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
    case none, pathfinding, titleScreen, dialog, dismiss, interact, action, navigate, usePotion

    init(_ s: ScanAction) {
        switch s {
        case .none:        self = .none
        case .pathfinding: self = .pathfinding
        case .titleScreen: self = .titleScreen
        case .dialog:      self = .dialog
        case .dismiss:     self = .dismiss
        case .interact:    self = .interact
        case .action:      self = .action
        case .navigate:    self = .navigate
        case .usePotion:   self = .usePotion
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
