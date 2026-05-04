import Foundation

/// Pure OCR-region analyser — no I/O, no side-effects, no async.
/// Called every frame with the full OCR snapshot + current game state.
///
/// Priority order (highest wins):
///   0. Title/login screen
///   1. Pathfinding active (OCR OR LogMonitor)  → wait, don't interrupt
///   2. Explicit dialog/choice button visible   → click it
///   3. NPC/object interaction button visible   → click icon above label
///   4. World action button (Collect/Enter/…)   → click
///   5. Quest row in sidebar                    → tap to set nav target
struct QuestScanner {

    private static let confButton:  Float = 0.50
    private static let confAction:  Float = 0.45
    private static let confDialog:  Float = 0.40
    private static let confSidebar: Float = 0.30

    // MARK: - Main entry

    /// Returns (parsed sidebar state, action to execute this cycle).
    static func scan(context: ScreenContext) -> (quest: QuestState, action: ScanAction) {
        let regions = context.regions
        let mode = context.mode

        // ── Pre-check: login / title screen ───────────────────────────────
        if let r = OCREngine.find(regions, pattern: Patterns.tapToEnter, minConfidence: 0.5) {
            return (QuestState(), .titleScreen(cx: r.cx, cy: r.cy))
        }

        let quest = parseSidebar(regions, mode: mode)

        // ── Step 0: Pathfinding active — never interrupt movement ──────────
        // Trust BOTH LogMonitor (reliable) and OCR "Pathfinding" text (visible HUD)
        let pathfindingOCR = OCREngine.find(regions, pattern: Patterns.pathfinding,
                                             minConfidence: 0.30) != nil
        if context.isPathfinding || pathfindingOCR {
            return (quest, .pathfinding)
        }

        // ── Step 0.5: Dismiss blocking popup (×, Close) ───────────────────
        // Must run before dialog so a stray "Close" popup doesn't eat dialog turns.
        if let action = dismissButton(regions) {
            return (quest, action)
        }

        // ── Step 0.75: Daily reward / event chest — collect if visible ─────
        if let action = dailyRewardButton(regions) {
            return (quest, action)
        }

        // ── Step 0.8: Party invite auto-accept ────────────────────────────
        if let action = partyInviteButton(regions) {
            return (quest, action)
        }

        // ── Step 0.9: Dungeon / instance entry confirm ────────────────────
        if let action = dungeonEntryButton(regions) {
            return (quest, action)
        }

        // ── Step 1: Dialog / conversation choice button ────────────────────
        if let action = dialogButton(regions) {
            return (quest, action)
        }

        // ── Step 2: NPC / object interaction button ────────────────────────
        if let action = interactionButton(regions) {
            return (quest, action)
        }

        // ── Step 3: World action button (Collect, Activate, Enter, …) ─────
        if let action = actionButton(regions) {
            return (quest, action)
        }

        // ── Step 3.5: Commission board buttons (only in commission mode) ───
        if mode == .commissionBoard {
            if let action = commissionBoardButton(regions) {
                return (quest, action)
            }
        }

        // ── Step 4: Quest row tap — only when NOT already at target ────────
        // If distance == 0 we're already there; tapping the row would just stall.
        if let action = questRow(regions, quest: quest, mode: mode) {
            return (quest, action)
        }

        return (quest, .none)
    }

    // MARK: - Sidebar parser

    static func parseSidebar(_ regions: [TextRegion], mode: AutomationMode = .mainQuest) -> QuestState {
        let pattern = Patterns.questRowForMode(mode)
        guard
            let titleRegion = OCREngine.find(regions, pattern: pattern,
                                             minConfidence: confSidebar),
            titleRegion.cx < Zones.questPanelXMax
        else { return QuestState() }

        var state = QuestState()
        state.title = titleRegion.text

        // Step text: the first sidebar line directly below the title row
        if let step = regions
            .filter({ $0.cx < Zones.questPanelXMax
                   && $0.cy > titleRegion.cy
                   && $0.cy < titleRegion.cy + 80 })
            .min(by: { $0.cy < $1.cy }) {
            state.stepText = step.text
        }

        // Distance: look for "NNN m" anywhere in the sidebar
        for r in regions where r.cx < Zones.questPanelXMax {
            if let d = Patterns.capture(r.text, pattern: Patterns.distance),
               let dist = Int(d) {
                state.distance = dist
                break
            }
        }

        return state
    }

    // MARK: - Step 0.5 – dismiss blocking popups

    private static func dismissButton(_ regions: [TextRegion]) -> ScanAction? {
        // Close buttons are always top-right (cx > 500) and in the upper half (cy < 500).
        // This prevents matching an NPC "Close" dialog response in the lower game world.
        for pattern in Patterns.dismiss {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > 500,
               r.cy < 500 {
                return .dismiss(cx: r.cx, cy: r.cy, label: r.text)
            }
        }
        return nil
    }

    // MARK: - Step 0.75 – daily reward / event chest collect

    private static func dailyRewardButton(_ regions: [TextRegion]) -> ScanAction? {
        // First look for specific collect-now buttons that appear on reward popups.
        for pattern in Patterns.dailyRewardCollect {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > Zones.questPanelXMax {
                return .action(cx: r.cx, cy: r.cy, label: r.text)
            }
        }
        // If a reward popup TITLE is visible but no specific collect button yet, look for
        // a generic "Collect" or "Claim" near the popup (must be center-screen).
        let hasRewardPopup = Patterns.dailyReward.contains {
            OCREngine.find(regions, pattern: $0, minConfidence: confDialog) != nil
        }
        if hasRewardPopup {
            // Look for collect/claim in any action button within popup area
            for pattern in [#"Collect\b"#, #"\bClaim\b"#, #"Receive\b"#] {
                if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confAction),
                   r.cx > Zones.questPanelXMax,
                   r.cy > 200, r.cy < 700 {
                    return .action(cx: r.cx, cy: r.cy, label: r.text)
                }
            }
        }
        return nil
    }

    // MARK: - Step 0.8 – party invite auto-accept

    private static func partyInviteButton(_ regions: [TextRegion]) -> ScanAction? {
        // Only fire if a party invite popup title is visible
        guard Patterns.partyInvite.contains(where: {
            OCREngine.find(regions, pattern: $0, minConfidence: confDialog) != nil
        }) else { return nil }
        for pattern in Patterns.partyAccept {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > Zones.questPanelXMax {
                return .dialog(cx: r.cx, cy: r.cy, label: "Party: \(r.text)")
            }
        }
        return nil
    }

    // MARK: - Step 0.9 – dungeon / instance entry confirm

    private static func dungeonEntryButton(_ regions: [TextRegion]) -> ScanAction? {
        guard Patterns.dungeonEntry.contains(where: {
            OCREngine.find(regions, pattern: $0, minConfidence: confDialog) != nil
        }) else { return nil }
        // Look for an Enter / Challenge / Confirm button
        for pattern in [#"\bEnter\b"#, #"\bChallenge\b"#, #"\bConfirm\b"#, #"\bReady\b"#] {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confAction),
               r.cx > Zones.questPanelXMax {
                return .action(cx: r.cx, cy: r.cy, label: "Dungeon: \(r.text)")
            }
        }
        return nil
    }

    // MARK: - Step 1 – dialog buttons

    private static func dialogButton(_ regions: [TextRegion]) -> ScanAction? {
        // "Skip" can appear anywhere outside the sidebar
        if let r = OCREngine.find(regions, pattern: Patterns.skip, minConfidence: confDialog),
           r.cx > Zones.questPanelXMax {
            return .dialog(cx: r.cx, cy: r.cy, label: r.text)
        }

        // Unambiguous choice buttons — below HUD top and above dialog zone end
        for pattern in Patterns.dialogChoice {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > Zones.questPanelXMax,
               r.cy > Zones.hudTopYMax,
               r.cy < Zones.dialogYMax {
                return .dialog(cx: r.cx, cy: r.cy, label: r.text)
            }
        }

        // Ambiguous words (Accept, Start, Receive, Finish) — require extra vertical guard
        // to avoid matching HUD buttons which sit above y=400.
        for pattern in Patterns.dialogChoiceAmbiguous {
            if let r = OCREngine.find(regions, pattern: pattern, minConfidence: confDialog),
               r.cx > Zones.questPanelXMax,
               r.cy > 400,
               r.cy < Zones.dialogYMax {
                return .dialog(cx: r.cx, cy: r.cy, label: r.text)
            }
        }

        return nil
    }

    // MARK: - Step 2 – NPC / object interaction

    private static func interactionButton(_ regions: [TextRegion]) -> ScanAction? {
        for pattern in Patterns.interaction {
            guard
                let r = OCREngine.find(regions, pattern: pattern, minConfidence: confButton),
                Zones.isGameWorld(cx: r.cx, cy: r.cy)
            else { continue }
            // The NPC sign in RöX is a combined icon+text element.  The interactive
            // hit area covers both the icon (above) and the label (below).  Click the
            // label centre — this is always within the sign's tap region and avoids
            // overshooting into the HUD when the icon offset lands outside game world.
            return .interact(cx: r.cx, cy: r.cy, label: r.text)
        }
        return nil
    }

    // MARK: - Step 3 – world action buttons

    private static func actionButton(_ regions: [TextRegion]) -> ScanAction? {
        for pattern in Patterns.action {
            guard
                let r = OCREngine.find(regions, pattern: pattern, minConfidence: confAction),
                Zones.isGameWorld(cx: r.cx, cy: r.cy)
            else { continue }
            return .action(cx: r.cx, cy: r.cy, label: r.text)
        }
        return nil
    }

    // MARK: - Step 3.5 – commission board buttons

    private static func commissionBoardButton(_ regions: [TextRegion]) -> ScanAction? {
        for pattern in Patterns.commissionBoard {
            guard
                let r = OCREngine.find(regions, pattern: pattern, minConfidence: confAction),
                r.cx > Zones.questPanelXMax
            else { continue }
            return .action(cx: r.cx, cy: r.cy, label: r.text)
        }
        return nil
    }

    // MARK: - Step 4 – quest row navigation

    private static func questRow(_ regions: [TextRegion], quest: QuestState, mode: AutomationMode) -> ScanAction? {
        // Already at target → don't re-tap, an interaction button should appear
        if quest.isAtTarget { return nil }

        let pattern = Patterns.questRowForMode(mode)
        guard
            let r = OCREngine.find(regions, pattern: pattern,
                                   minConfidence: confSidebar),
            r.cx < Zones.questPanelXMax
        else { return nil }

        return .navigate(cx: r.cx, cy: r.cy, label: r.text)
    }
}
