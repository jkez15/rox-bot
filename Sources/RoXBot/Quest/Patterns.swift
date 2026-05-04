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
        #"[Ee]xamin"#,         // Examine — magnifying glass icon
        #"[Ii1]nspect"#,       // Inspect
        #"\bTalk\b"#,           // Talk
        #"[Ii1]nvestigat"#,    // Investigate
        #"[Ii1]nquir"#,        // Inquire (when on NPC, not dialog)
        #"\bDisguis"#,          // Disguise
        #"\bInteract\b"#,       // Interact
        #"\bApproach\b"#,       // Approach
        #"\bGreet\b"#,          // Greet
        #"\bOperat"#,           // Operate
        #"\bProbe\b"#,          // Probe
        #"\bTouch\b"#,          // Touch
        #"\bObserv"#,           // Observe
        #"\bSurvey\b"#,         // Survey
        #"\bQuestion\b"#,       // Question (NPC interaction)
        #"\bPatrol\b"#,         // Patrol point
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

    // MARK: - Daily reward / golden chest popup
    // Matches the "Collect" / "Claim" / "Receive Reward" buttons on daily login popups,
    // achievement chests, and event reward banners.
    // Zone: anywhere outside the sidebar (cx > questPanelXMax) — popup can appear center-screen.
    static let dailyReward: [String] = [
        #"Daily\s*Reward"#,
        #"Daily\s*Login"#,
        #"Login\s*Reward"#,
        #"Sign.in\s*Reward"#,
        #"Attendance\s*Reward"#,
        #"Golden\s*Chest"#,
        #"Event\s*Reward"#,
        #"Lucky\s*Draw"#,
    ]

    // Buttons that appear ON daily reward / event popups to collect the reward.
    // These are more specific than the generic action buttons to avoid false positives.
    static let dailyRewardCollect: [String] = [
        #"Collect\s*Now"#,
        #"Claim\s*Now"#,
        #"Receive\s*Now"#,
        #"Get\s*Reward"#,
        #"One.?tap\s*Collect"#,
        #"Claim\s*All"#,
        #"Collect\s*All"#,
    ]

    // MARK: - Party invite auto-accept
    // Matches the party invite popup title.
    static let partyInvite: [String] = [
        #"Party\s*Invite"#,
        #"Team\s*Invite"#,
        #"Group\s*Invite"#,
        #"Invite.*to.*Party"#,
        #"Invite.*to.*Team"#,
    ]
    // The accept button on party invite popups.
    static let partyAccept: [String] = [
        #"\bJoin\b"#,
        #"\bAccept\b"#,   // safe here because we already confirmed partyInvite is present
    ]

    // MARK: - Dungeon / instance entry prompt
    // Matches the "Enter dungeon" / "Challenge" entry screen.
    static let dungeonEntry: [String] = [
        #"Enter\s*Dungeon"#,
        #"Enter\s*Instance"#,
        #"Challenge\s*Mode"#,
        #"Ready\s*to\s*Enter"#,
        #"Confirm\s*Entry"#,
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
