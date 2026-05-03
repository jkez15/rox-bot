import Foundation

// MARK: - Data models

/// A recurring commission quest from recurring_quests_raw.txt
struct RecurringQuest {
    let id:               Int
    let joinType:         Int       // 0 = generic, 1 = NPC-specific
    let joinTypeParam:    String    // NPC uniqueId (if joinType==1) or UI name
    let targetType:       Int       // Maps to game's TaskStepType roughly
    let targetParam:      [Int]
    let times:            Int       // Repetitions needed to complete
    let prizeIds:         [Int]
    let prizeNums:        [Int]
    let reward:           Int       // Reward table ID
    let boxId:            Int
    let day:              Int?      // Day-of-week restriction (nil = any day)

    /// Total reward units — sum of all prize amounts.
    var totalReward: Int { prizeNums.reduce(0, +) }

    /// Reward efficiency — total reward divided by repetitions needed.
    var rewardPerTask: Double {
        times > 0 ? Double(totalReward) / Double(times) : 0
    }
}

/// A commission quest board from entrust_raw.txt
struct QuestBoard {
    let id:             Int
    let npcIds:         [Int]     // NPC uniqueIds that host this board
    let dailyMaxAccept: Int       // Max quests per day from this board (0 = default 10)
}

// MARK: - Loader

/// Parses bundle_dumps/recurring_quests_raw.txt and entrust_raw.txt.
/// Call `CommissionData.shared.load()` once at startup.
final class CommissionData {

    static let shared = CommissionData()
    private init() {}

    private(set) var quests: [RecurringQuest] = []
    private(set) var boards: [QuestBoard]     = []

    /// Quests grouped by NPC uniqueId (only for joinType==1 quests).
    private(set) var questsByNPC: [Int: [RecurringQuest]] = [:]

    /// Top quests ranked by reward efficiency.
    var topQuests: [RecurringQuest] {
        quests.sorted { $0.rewardPerTask > $1.rewardPerTask }
    }

    /// Filter quests available on a given day of week (1=Mon..7=Sun). Includes day=nil (any day).
    func questsForDay(_ dayOfWeek: Int) -> [RecurringQuest] {
        quests.filter { $0.day == nil || $0.day == dayOfWeek }
    }

    func load() {
        let base = bundleDumpsURL()

        let recurURL = base.appendingPathComponent("recurring_quests_raw.txt")
        if let text = try? String(contentsOf: recurURL, encoding: .utf8) {
            quests = parseRecurringQuests(text)
            buildQuestsByNPC()
            print("[CommissionData] Loaded \(quests.count) recurring quests (\(questsByNPC.count) NPC-specific)")
        } else {
            print("[CommissionData] ⚠️ recurring_quests_raw.txt not found")
        }

        let entrustURL = base.appendingPathComponent("entrust_raw.txt")
        if let text = try? String(contentsOf: entrustURL, encoding: .utf8) {
            boards = parseQuestBoards(text)
            print("[CommissionData] Loaded \(boards.count) quest boards")
        } else {
            print("[CommissionData] ⚠️ entrust_raw.txt not found")
        }
    }

    // MARK: - Parsing recurring_quests_raw.txt

    private func parseRecurringQuests(_ text: String) -> [RecurringQuest] {
        var results: [RecurringQuest] = []

        // State machine for Lua table parsing
        var inBlock = false
        var id = 0, joinType = 0, joinParam = "0", targetType = 0
        var targetParam: [Int] = [], times = 1
        var prizeIds: [Int] = [], prizeNums: [Int] = []
        var reward = 0, boxId = 0
        var day: Int?

        // Track which array we're collecting into
        var collectingArray: String?

        for line in text.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)

            // New entry: [N] = {
            if t.hasPrefix("[") && t.contains("] = {") && !t.contains("\"") {
                if inBlock && id > 0 {
                    results.append(RecurringQuest(
                        id: id, joinType: joinType, joinTypeParam: joinParam,
                        targetType: targetType, targetParam: targetParam, times: times,
                        prizeIds: prizeIds, prizeNums: prizeNums,
                        reward: reward, boxId: boxId, day: day
                    ))
                }
                inBlock = true
                id = 0; joinType = 0; joinParam = "0"; targetType = 0
                targetParam = []; times = 1; prizeIds = []; prizeNums = []
                reward = 0; boxId = 0; day = nil; collectingArray = nil
                continue
            }

            guard inBlock else { continue }

            // End of sub-array
            if t == "}," || t == "}" {
                collectingArray = nil
                continue
            }

            // Collecting array elements (bare integers inside { })
            if let arr = collectingArray {
                if let v = Int(t.replacingOccurrences(of: ",", with: "")) {
                    switch arr {
                    case "TargetParameter": targetParam.append(v)
                    case "prize_id":        prizeIds.append(v)
                    case "prize_num":       prizeNums.append(v)
                    default: break
                    }
                }
                continue
            }

            // Key-value pairs
            if t.contains("[\"Id\"] =") {
                id = extractInt(t) ?? 0
            } else if t.contains("[\"JoinType\"] =") {
                joinType = extractInt(t) ?? 0
            } else if t.contains("[\"JoinTypeParameter\"] =") {
                joinParam = extractString(t) ?? "0"
            } else if t.contains("[\"TargetType\"] =") {
                targetType = extractInt(t) ?? 0
            } else if t.contains("[\"Times\"] =") {
                times = extractInt(t) ?? 1
            } else if t.contains("[\"reward\"] =") {
                reward = extractInt(t) ?? 0
            } else if t.contains("[\"box_id\"] =") {
                boxId = extractInt(t) ?? 0
            } else if t.contains("[\"Day\"] =") {
                day = extractInt(t)
            } else if t.contains("[\"TargetParameter\"] =") {
                collectingArray = "TargetParameter"
            } else if t.contains("[\"prize_id\"] =") {
                collectingArray = "prize_id"
            } else if t.contains("[\"prize_num\"] =") {
                collectingArray = "prize_num"
            }
        }
        // Flush last
        if inBlock && id > 0 {
            results.append(RecurringQuest(
                id: id, joinType: joinType, joinTypeParam: joinParam,
                targetType: targetType, targetParam: targetParam, times: times,
                prizeIds: prizeIds, prizeNums: prizeNums,
                reward: reward, boxId: boxId, day: day
            ))
        }

        return results
    }

    // MARK: - Parsing entrust_raw.txt

    private func parseQuestBoards(_ text: String) -> [QuestBoard] {
        var results: [QuestBoard] = []
        var inBlock = false
        var boardId = 0
        var npcIds: [Int] = []
        var dailyMax = 10  // default from game
        var collectingNpcs = false

        for line in text.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)

            if t.hasPrefix("[") && t.contains("] = {") && !t.contains("\"") {
                if inBlock && boardId > 0 {
                    results.append(QuestBoard(id: boardId, npcIds: npcIds, dailyMaxAccept: dailyMax))
                }
                inBlock = true
                boardId = 0; npcIds = []; dailyMax = 10; collectingNpcs = false
                continue
            }

            // Only parse the QuestBoard section
            if t.contains("data_entrust_QuestBoard") { continue }
            if t.contains("data_entrust_") && !t.contains("QuestBoard") {
                // Flush and stop — we've left the QuestBoard section
                if inBlock && boardId > 0 {
                    results.append(QuestBoard(id: boardId, npcIds: npcIds, dailyMaxAccept: dailyMax))
                }
                break
            }

            guard inBlock else { continue }

            if t == "}," || t == "}" {
                collectingNpcs = false
                continue
            }

            if collectingNpcs {
                if let v = Int(t.replacingOccurrences(of: ",", with: "")) {
                    npcIds.append(v)
                }
                continue
            }

            if t.contains("[\"Id\"] =") {
                boardId = extractInt(t) ?? 0
            } else if t.contains("[\"dailyMaximumAccept\"] =") {
                dailyMax = extractInt(t) ?? 10
            } else if t.contains("[\"entrustNpcId\"] =") {
                collectingNpcs = true
            }
        }
        if inBlock && boardId > 0 {
            results.append(QuestBoard(id: boardId, npcIds: npcIds, dailyMaxAccept: dailyMax))
        }

        return results
    }

    // MARK: - Index building

    private func buildQuestsByNPC() {
        questsByNPC = [:]
        for quest in quests where quest.joinType == 1 {
            if let npcId = Int(quest.joinTypeParam) {
                questsByNPC[npcId, default: []].append(quest)
            }
        }
    }

    // MARK: - Helpers

    private func extractInt(_ line: String) -> Int? {
        guard let rhs = line.components(separatedBy: "=").last else { return nil }
        let cleaned = rhs.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "")
        return Int(cleaned)
    }

    private func extractString(_ line: String) -> String? {
        let parts = line.components(separatedBy: "\"")
        // ["key"] = "value",  → parts[3] is the value
        return parts.count >= 4 ? parts[3] : nil
    }

    private func bundleDumpsURL() -> URL {
        let exe = URL(fileURLWithPath: CommandLine.arguments[0])
        var candidate = exe
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("bundle_dumps")
        if FileManager.default.fileExists(atPath: candidate.path) { return candidate }

        candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("bundle_dumps")
        return candidate
    }
}
