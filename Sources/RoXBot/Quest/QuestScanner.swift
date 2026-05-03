import Foundation

// MARK: - Data models

struct QuestInfo {
    var title:    String  = ""
    var stepText: String  = ""
    var distance: Int?    = nil
    var target:   String  = ""
}

/// The action the scanner has decided to take this cycle.
enum ScanAction {
    case none
    case titleScreen(cx: Int, cy: Int)
    case pathfinding
    case dialog(cx: Int, cy: Int, label: String)
    case interact(cx: Int, cy: Int, label: String)
    case action(cx: Int, cy: Int, label: String)
    case navigate(cx: Int, cy: Int, label: String)
}

// MARK: - Scanner

/// Pure OCR-region analyser — no I/O, no state, no async.
/// Called each cycle with a fresh snapshot of OCR regions.
struct QuestScanner {

    private static let confButton:  Float = 0.50
    private static let confAction:  Float = 0.45
    private static let confDialog:  Float = 0.40
    private static let confSidebar: Float = 0.30

    // MARK: - Main entry

    static func scan(regions: [TextRegion]) -> (info: QuestInfo?, action: ScanAction) {

        // ── Pre-check: login / title screen ───────────────────────────────
        if let r = OCREngine.find(regions, pattern: Patterns.tapToEnter, minConfidence: 0.5) {
            return (nil, .titleScreen(cx: r.cx, cy: r.cy))
        }

        // ── Step 0: Pathfinding active — don't interrupt ──────────────────
        if OCREngine.find(regions, pattern: Patterns.pathfinding, minConfidence: 0.30) != nil {
            return (parseSidebar(regions), .pathfinding)
        }

        let info = parseSidebar(regions)

        // ── Step 1: Dialog / conversation control button ──────────────────
        if let action = dialogButton(regions) {
            return (info, action)
        }

        // ── Step 2: NPC / object interaction button ───────────────────────
        if let action = interactionButton(regions) {
            return (info, action)
        }

        // ── Step 3: World action button (Collect, Activate, …) ───────────
        if let action = actionButton(regions) {
            return (info, action)
        }

        // ── Step 4: Quest row tap to set navigation target ────────────────
        if let action = questRow(regions) {
            return (info, action)
        }

        return (info, .none)
    }

    // MARK: - Sidebar

    static func parseSidebar(_ regions: [TextRegion]) -> QuestInfo? {
        guard
            let titleRegion = OCREngine.find(regions, pattern: Patterns.questRow, minConfidence: confSidebar),
            titleRegion.cx < Zones.questPanelXMax
        else { return nil }

        var info = QuestInfo()
        info.title = titleRegion.text

        // Step text: first sidebar region below the title
        let step = regions
            .filter { $0.cx < Zones.questPanelXMax && $0.cy > titleRegion.cy && $0.cy < titleRegion.cy + 80 }
            .sorted { $0.cy < $1.cy }
            .first
        info.stepText = step?.text ?? ""

        // Distance: any sidebar region containing "NNN m"
        for r in regions where r.cx < Zones.questPanelXMax {
            if let d = Patterns.capture(r.text, pattern: Patterns.distance), let dist = Int(d) {
                info.distance = dist
                break
            }
        }

        return info
    }

    // MARK: - Button finders

    private static func dialogButton(_ regions: [TextRegion]) -> ScanAction? {
        // Skip button — anywhere outside sidebar
        if let r = OCREngine.find(regions, pattern: Patterns.skip, minConfidence: confDialog),
           r.cx > Zones.questPanelXMax {
            return .dialog(cx: r.cx, cy: r.cy, label: r.text)
        }

        // Named choice buttons (Next, Close, Accept, …)
        // Search both game world AND dialog zone — NPC dialogs can place buttons anywhere
        for pattern in Patterns.dialogChoice {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > Zones.questPanelXMax,
               r.cy > Zones.hudTopYMax {
                return .dialog(cx: r.cx, cy: r.cy, label: r.text)
            }
        }

        // NPC conversation fallback: if there is dialog text in the dialog zone
        // but no button found yet, tap the right side of the dialog zone to advance
        let hasDialogText = regions.contains { r in
            Zones.isDialogZone(cx: r.cx, cy: r.cy) &&
            r.cx > Zones.questPanelXMax &&
            r.text.split(separator: " ").count >= 3 &&
            r.text.filter(\.isLetter).count > 10
        }
        if hasDialogText {
            // Tap the bottom-right of the dialog area — where "Next/▶" typically lives
            return .dialog(cx: 900, cy: Zones.dialogYMin + 60, label: "advance")
        }

        return nil
    }

    private static func interactionButton(_ regions: [TextRegion]) -> ScanAction? {
        for pattern in Patterns.interaction {
            guard
                let r = OCREngine.find(regions, pattern: pattern, minConfidence: confButton),
                Zones.isGameWorld(cx: r.cx, cy: r.cy)
            else { continue }
            // Icon sits above the label — click above it
            let iconY = max(r.cy - max(24, r.height * 2), Zones.hudTopYMax + 10)
            return .interact(cx: r.cx, cy: iconY, label: r.text)
        }
        return nil
    }

    private static func actionButton(_ regions: [TextRegion]) -> ScanAction? {
        for pattern in Patterns.action {
            guard
                let r = OCREngine.find(regions, pattern: pattern, minConfidence: confAction),
                r.cx > Zones.questPanelXMax,
                r.cy > Zones.hudTopYMax,
                r.cy < Zones.gameWorldYMax
            else { continue }
            return .action(cx: r.cx, cy: r.cy, label: r.text)
        }
        return nil
    }

    private static func questRow(_ regions: [TextRegion]) -> ScanAction? {
        guard
            let r = OCREngine.find(regions, pattern: Patterns.questRow, minConfidence: confSidebar),
            r.cx < Zones.questPanelXMax
        else { return nil }
        return .navigate(cx: r.cx, cy: r.cy, label: r.text)
    }

    // MARK: - Helpers

    private static func looksLikeDialogLine(_ r: TextRegion) -> Bool {
        let t = r.text.trimmingCharacters(in: .whitespaces)
        guard t.count >= 18, r.width >= 180 else { return false }
        let words = t.split(separator: " ")
        guard words.count >= 4 else { return false }
        // Reject UI noise tokens
        let noisy = ["[Main]", "[Sub]", "Lv", "Realm", "Send", "auto", "NONE"]
        if noisy.contains(where: { t.contains($0) }) { return false }
        // Must be mostly alphabetic text
        let letterCount = t.filter(\.isLetter).count
        return Double(letterCount) / Double(t.count) > 0.6
    }
}
