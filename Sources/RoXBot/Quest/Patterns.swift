import Foundation

/// All OCR regex patterns used to identify game UI elements.
///
/// Patterns mirror the Python bot's INTERACTION_PATTERNS, ACTION_BUTTON_PATTERNS, etc.
enum Patterns {

    // MARK: - System / navigation
    static let tapToEnter  = #"Tap\s+to\s+enter\s+game"#
    static let pathfinding = #"Pathfinding|Path\s*finding|Auto.?walk|Auto\s*Path|Navigat|Route"#

    // MARK: - Quest sidebar
    static let questRow    = #"\[Main\]|\[Sub\]|\[Daily\]|\[Guild\]"#
    static let mainQuest   = #"\[Main\]"#
    static let dailyQuest  = #"\[Daily\]"#
    static let guildQuest  = #"\[Guild\]"#
    static let subQuest    = #"\[Sub\]"#
    static let distance    = #"(\d+)\s*m\b"#

    /// Returns the sidebar quest pattern for a specific mode.
    static func questRowForMode(_ mode: AutomationMode) -> String {
        switch mode {
        case .mainQuest:       return mainQuest
        case .dailyQuests:     return dailyQuest
        case .guildQuests:     return guildQuest
        case .commissionBoard: return questRow   // any quest type while doing commissions
        case .autoPotion:      return questRow   // monitor all
        }
    }

    // MARK: - Interaction buttons (NPC / object — game world only)
    // Only include words that are exclusively used as NPC/object interaction button labels.
    // Generic English words (Open, Read, Look, Search, Press, Pull, Push) are removed
    // because they appear in item tooltips, map labels, and chat — causing false clicks.
    static let interaction: [String] = [
        #"[Ee]xamin"#,
        #"[Ii1]nspect"#,
        #"\bTalk\b"#,
        #"[Ii1]nvestigat"#,
        #"[Ii1]nquir"#,
        #"\bDisguis"#,
        #"\bInteract\b"#,
        #"\bApproach\b"#,
        #"\bGreet\b"#,
        #"\bOperat"#,
        #"\bProbe\b"#,
        #"\bTouch\b"#,
    ]

    // MARK: - Dialog control buttons
    static let skip = #"\bSkip\b"#

    // Dialog choice buttons — words that appear ONLY as NPC dialog response buttons.
    // "Accept" and "Start" are in `dialogChoiceAmbiguous` — the scanner applies a stricter
    // zone guard (cy > 400) for those to avoid HUD false-positives.
    static let dialogChoice: [String] = [
        #"Inquir"#,
        #"\bNext\b"#,
        #"Continu"#,
        #"\bOk\b"#, #"\bOK\b"#,
        #"\bYes\b"#,
        #"\bAgree\b"#,
        #"Got\s*it"#,
        #"Understood"#,
        #"\bBye\b"#,
        #"\bConfirm\b"#,
        #"Let.s\s*go"#,
        // Death / resurrection recovery
        #"\bRevive\b"#,
        #"Resurrect"#,
        #"Return\s+to\s+Town"#,
    ]

    // Ambiguous dialog words — valid quest accept/start buttons but also appear in HUD menus.
    // Scanner applies extra zone guard: cy > 400 && cy < dialogYMax.
    static let dialogChoiceAmbiguous: [String] = [
        #"\bAccept\b"#,
        #"\bStart\b"#,
        #"\bReceive\b"#,
        #"\bFinish\b"#,
    ]

    // MARK: - Dismiss / close buttons
    // Strict zone required: cx > 500 && cy < 500 (top-right close buttons on popups).
    static let dismiss: [String] = [
        #"[×✕✖]"#,
        #"\bClose\b"#,
    ]

    // MARK: - Action buttons (game world)
    static let action: [String] = [
        #"\bShow\b"#, #"\bPresent\b"#, #"\bDisplay\b"#,
        #"\bCollect\b"#, #"\bGather\b"#, #"\bPick\s*up\b"#,
        #"\bActivate\b"#, #"\bUse\b"#,
        #"\bInvestigate\b"#,
        #"\bEnter\b"#, #"\bChallenge\b"#,
        #"\bDeliver\b"#, #"\bGive\b"#, #"\bHand\s*over\b"#,
        #"\bReport\b"#, #"\bComplete\b"#,
        #"\bClaim\b"#, #"\bReceive\b"#,
        #"\bPlay\b"#, #"\bFight\b"#,
        #"\bRepair\b"#, #"\bCraft\b"#,
        #"\bSummon\b"#,
    ]

    // MARK: - Commission board buttons
    // These appear inside the commission board popup window (not game world).
    // Used only when AutomationMode == .commissionBoard.
    static let commissionBoard: [String] = [
        #"Commission"#,
        #"Quest\s*Board"#,
        #"Accept\s*Quest"#,
        #"Claim\s*Reward"#,
        #"\bSubmit\b"#,
        #"\bDecline\b"#,
        #"Refresh"#,
    ]

    // MARK: - Helpers

    static func matches(_ text: String, pattern: String) -> Bool {
        (try? NSRegularExpression(pattern: pattern, options: .caseInsensitive))?
            .firstMatch(in: text, range: NSRange(text.startIndex..., in: text)) != nil
    }

    static func capture(_ text: String, pattern: String, group: Int = 1) -> String? {
        guard
            let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive),
            let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
            match.numberOfRanges > group,
            let range = Range(match.range(at: group), in: text)
        else { return nil }
        return String(text[range])
    }
}
