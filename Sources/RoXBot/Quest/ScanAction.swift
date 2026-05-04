import Foundation

// MARK: - Automation mode — selectable from the dashboard

enum AutomationMode: String, CaseIterable, CustomStringConvertible {
    case mainQuest       = "Main Quest"
    case commissionBoard = "Commission Board"
    case dailyQuests     = "Daily Quests"
    case guildQuests     = "Guild Quests"
    case autoPotion      = "Auto-Potion"

    var description: String { rawValue }

    /// The sidebar quest prefix this mode targets (nil = all / N/A).
    var questPrefix: String? {
        switch self {
        case .mainQuest:       return "[Main]"
        case .dailyQuests:     return "[Daily]"
        case .guildQuests:     return "[Guild]"
        case .commissionBoard: return nil
        case .autoPotion:      return nil
        }
    }

    /// Short icon for dashboard labels.
    var icon: String {
        switch self {
        case .mainQuest:       return "📜"
        case .commissionBoard: return "📋"
        case .dailyQuests:     return "📅"
        case .guildQuests:     return "⚔️"
        case .autoPotion:      return "🧪"
        }
    }
}

// MARK: - Quest state parsed from OCR sidebar each frame

struct QuestState {
    var title:    String  = ""
    var stepText: String  = ""
    var distance: Int?    = nil

    /// True when the sidebar shows a distance ≤ 5 m (including 0).
    /// At distance 0 the NPC is right next to the character — the interaction button
    /// should be visible. Don't re-tap the quest row; wait for the interaction scan.
    var isAtTarget: Bool {
        guard let d = distance else { return false }
        return d <= 5
    }
    var hasActiveQuest: Bool { !title.isEmpty }
}

// MARK: - Observed screen context passed to the scanner each cycle

struct ScreenContext {
    let regions:      [TextRegion]
    let questState:   QuestState
    let isPathfinding: Bool      // from LogMonitor
    let currentScene:  Int?      // from LogMonitor
    let mode:          AutomationMode
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
    /// Press a potion hotkey (no click coords — sends a CGEvent keypress).
    case usePotion(kind: PotionKind)

    enum PotionKind: String {
        case hp = "HP"
        case sp = "SP"
    }

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
        case .usePotion(let k):                 return "usePotion(\(k.rawValue))"
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
