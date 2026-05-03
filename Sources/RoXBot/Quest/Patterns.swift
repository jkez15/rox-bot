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
        #"\bActivat"#,
        #"\bOperat"#,
        #"\bProbe\b"#,
        #"\bSearch\b"#,
        #"\bTouch\b"#,
        #"\bPress\b"#,
        #"\bPull\b"#,
        #"\bPush\b"#,
        #"\bOpen\b"#,
        #"\bRead\b"#,
        #"\bLook\b"#,
    ]

    // MARK: - Dialog control buttons
    static let skip = #"\bSkip\b"#

    static let dialogChoice: [String] = [
        #"Inquir"#,
        #"\bNext\b"#,
        #"Continu"#,
        #"\bClose\b"#,
        #"\bOk\b"#, #"\bOK\b"#,
        #"\bYes\b"#,
        #"\bAgree\b"#,
        #"Got\s*it"#,
        #"Understood"#,
        #"\bDone\b"#,
        #"\bFinish\b"#,
        #"\bBye\b"#,
        #"\bAccept\b"#,
        #"\bConfirm\b"#,
        #"\bStart\b"#,
        #"\bReceive\b"#,
        #"\bClaim\b"#,
        #"Let.s\s*go"#,
        #"\bReturn\b"#,
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
