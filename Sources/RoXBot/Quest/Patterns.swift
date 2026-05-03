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
    static let distance    = #"(\d+)\s*m\b"#

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
    // Generic words (Close, Done, Start, Return, Accept, Receive, Claim) removed from here
    // because they appear in HUD menus, inventory, and quest panels causing false clicks.
    // Those are allowed only as action buttons (step 3) where zone checks are stricter.
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
