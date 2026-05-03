import Foundation

// MARK: - Quest state parsed from OCR sidebar each frame

struct QuestState {
    var title:    String  = ""
    var stepText: String  = ""
    var distance: Int?    = nil

    /// True when the sidebar shows a distance and it's ≤ this threshold (units).
    /// At distance 0 the NPC should be right next to the character.
    var isAtTarget: Bool { (distance ?? Int.max) <= 5 }
    var hasActiveQuest: Bool { !title.isEmpty }
}

// MARK: - Observed screen context passed to the scanner each cycle

struct ScreenContext {
    let regions:      [TextRegion]
    let questState:   QuestState
    let isPathfinding: Bool      // from LogMonitor
    let currentScene:  Int?      // from LogMonitor
}

// MARK: - Rich action type

enum ScanAction: CustomStringConvertible {
    case none
    case titleScreen(cx: Int, cy: Int)
    case pathfinding
    case dialog(cx: Int, cy: Int, label: String)
    /// Dismiss a blocking popup (×, Close button, etc.) — not subject to normal dedup.
    case dismiss(cx: Int, cy: Int, label: String)
    case interact(cx: Int, cy: Int, label: String)
    case action(cx: Int, cy: Int, label: String)
    case navigate(cx: Int, cy: Int, label: String)

    var description: String {
        switch self {
        case .none:                             return "none"
        case .titleScreen(let x, let y):        return "titleScreen(\(x),\(y))"
        case .pathfinding:                      return "pathfinding"
        case .dialog(let x, let y, let l):      return "dialog(\(x),\(y)) '\(l)'"
        case .dismiss(let x, let y, let l):     return "dismiss(\(x),\(y)) '\(l)'"
        case .interact(let x, let y, let l):    return "interact(\(x),\(y)) '\(l)'"
        case .action(let x, let y, let l):      return "action(\(x),\(y)) '\(l)'"
        case .navigate(let x, let y, let l):    return "navigate(\(x),\(y)) '\(l)'"
        }
    }

    /// Coordinate for deduplication
    var coord: (Int, Int)? {
        switch self {
        case .titleScreen(let x, let y),
             .dialog(let x, let y, _),
             .dismiss(let x, let y, _),
             .interact(let x, let y, _),
             .action(let x, let y, _),
             .navigate(let x, let y, _):
            return (x, y)
        default: return nil
        }
    }
}
