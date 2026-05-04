import Foundation

// MARK: - Data Models

struct SceneNPC {
    let uniqueId: Int
    let sceneId:  Int
    let x: Float
    let z: Float
    let name: String

    /// First 4 digits of uniqueId = scene_id
    var inferredSceneId: Int { uniqueId / 10000 }
}

/// Rich metadata from npc_raw.txt (type, signContent, dialogueradius, etc.)
struct NPCMeta {
    let staticId:        Int
    let type:            Int       // 1=portal, 2=?, 4=?, 5=sign, 8=collection
    let signContent:     String    // localization key for floating button text
    let dialogueRadius:  Float     // interaction range in world units
    let hasDialogue:     Bool      // true if defaultDialogueIdList is non-empty
}

/// Derived catalog row from npc_interactive_catalog.csv.
/// Adds icon keys (e.g. "icon_entrust", "icon_NPC_0") that the game's minimap uses.
struct NPCInteractive {
    let npcGuid:     Int
    let sceneId:     Int
    let sceneX:      Float
    let sceneZ:      Float
    let staticId:    Int
    let icon1:       String   // e.g. "icon_entrust"
    let icon2:       String   // e.g. "icon_entrust_L"
    let isInteractive: Bool
}

// MARK: - Known scene IDs
enum SceneID {
    static let prontera  = 1010
    static let izlude    = 1110
    static let geffen    = 1210
    static let morroc    = 1310
    static let alberta   = 1410
    static let payon     = 1510
    static let aldebaran = 1610

    static let name: [Int: String] = [
        1010: "Prontera",
        1110: "Izlude",
        1210: "Geffen",
        1310: "Morroc",
        1410: "Alberta",
        1510: "Payon",
        1610: "Aldebaran",
        1710: "Lighthalzen",
        1810: "Einbroch",
        1910: "Brasilis",
    ]
}

// MARK: - Loader

/// Parses bundle_dumps/*.txt files (already committed to the repo).
/// Call `GameKnowledge.shared.load()` once at startup — ~0.05 s.
final class GameKnowledge {

    static let shared = GameKnowledge()
    private init() {}

    /// All scene NPCs keyed by uniqueId
    private(set) var npcByUniqueId: [Int: SceneNPC] = [:]
    /// Scene NPCs grouped by sceneId
    private(set) var npcByScene:    [Int: [SceneNPC]] = [:]

    // Well-known NPC uniqueIds for commission boards (委托板)
    // From entrust_raw.txt: data_entrust_QuestBoard entrustNpcId lists
    static let commissionBoardIds: Set<Int> = [
        10101013, // Prontera
        11101014, // Izlude
        11801007, // Payon
        12101007, // Geffen
        13101009, // Morroc
        14101007, // Alberta
        16101008, // Lighthalzen
        17101010, // Einbroch
        18101010, // Einbroch (2)
        19101013, // Brasilis
        50101013, // Special zone 1
        51101013, // Special zone 2
    ]

    /// NPC metadata from npc_raw.txt (type, signContent, etc.)
    private(set) var npcMeta: [Int: NPCMeta] = [:]

    /// Interactive NPC catalog from npc_interactive_catalog.csv (icon keys, interactivity)
    private(set) var npcInteractive: [Int: NPCInteractive] = [:]

    /// All unique icon keys that appear on interactive NPCs (e.g. "icon_entrust")
    private(set) var knownInteractiveIconKeys: Set<String> = []

    func load() {
        let base = bundleDumpsURL()

        // 1. Scene NPC positions
        let sceneURL = base.appendingPathComponent("npc_scene.txt")
        if let text = try? String(contentsOf: sceneURL, encoding: .utf8) {
            parseNPCScene(text)
            print("[GameKnowledge] Loaded \(npcByUniqueId.count) scene NPCs across \(npcByScene.count) scenes")
        } else {
            print("[GameKnowledge] ⚠️ npc_scene.txt not found — NPC data unavailable")
        }

        // 2. NPC metadata (type, signContent, dialogueradius)
        let rawURL = base.appendingPathComponent("npc_raw.txt")
        if let text = try? String(contentsOf: rawURL, encoding: .utf8) {
            parseNPCRaw(text)
            print("[GameKnowledge] Loaded \(npcMeta.count) NPC metadata entries")
        } else {
            print("[GameKnowledge] ⚠️ npc_raw.txt not found — NPC metadata unavailable")
        }

        // 3. Interactive NPC catalog (icon keys, interactivity flags)
        let catalogURL = base.appendingPathComponent("npc_interactive_catalog.csv")
        if let text = try? String(contentsOf: catalogURL, encoding: .utf8) {
            parseInteractiveCatalog(text)
            print("[GameKnowledge] Loaded \(npcInteractive.count) interactive NPC entries (\(knownInteractiveIconKeys.count) icon keys)")
        } else {
            print("[GameKnowledge] ⚠️ npc_interactive_catalog.csv not found")
        }
    }

    func npcsInScene(_ sceneId: Int) -> [SceneNPC] {
        npcByScene[sceneId] ?? []
    }

    func npc(uniqueId: Int) -> SceneNPC? {
        npcByUniqueId[uniqueId]
    }

    func meta(staticId: Int) -> NPCMeta? {
        npcMeta[staticId]
    }

    /// Returns the icon key for a given NPC uniqueId (e.g. "icon_entrust").
    func iconKey(for npcUniqueId: Int) -> String? {
        guard let entry = npcInteractive[npcUniqueId], !entry.icon1.isEmpty else { return nil }
        return entry.icon1
    }

    /// Returns true if a given NPC is marked interactive in the catalog.
    func isInteractive(_ npcUniqueId: Int) -> Bool {
        npcInteractive[npcUniqueId]?.isInteractive ?? true  // default true if unknown
    }

    /// Returns the commission board NPC closest to the given scene/position.
    func nearestCommissionBoard(sceneId: Int, x: Float, z: Float) -> SceneNPC? {
        npcsInScene(sceneId)
            .filter { Self.commissionBoardIds.contains($0.uniqueId) }
            .min { a, b in
                let da = (a.x - x) * (a.x - x) + (a.z - z) * (a.z - z)
                let db = (b.x - x) * (b.x - x) + (b.z - z) * (b.z - z)
                return da < db
            }
    }

    /// Returns true if the given NPC uniqueId is a commission board.
    func isCommissionBoard(_ uniqueId: Int) -> Bool {
        Self.commissionBoardIds.contains(uniqueId)
    }

    // MARK: - Private

    private func parseNPCScene(_ text: String) {
        // Format: "  scene_id  unique_id  posx  posz  name"
        // Lines starting with # are comments
        for line in text.components(separatedBy: "\n") {
            let trimmed = line.trimmingCharacters(in: .whitespaces)
            guard !trimmed.isEmpty, !trimmed.hasPrefix("#") else { continue }
            let parts = trimmed.components(separatedBy: .whitespaces).filter { !$0.isEmpty }
            guard parts.count >= 5,
                  let sceneId   = Int(parts[0]),
                  let uniqueId  = Int(parts[1]),
                  let x         = Float(parts[2]),
                  let z         = Float(parts[3])
            else { continue }
            let name = parts[4...].joined(separator: " ")
            let npc  = SceneNPC(uniqueId: uniqueId, sceneId: sceneId, x: x, z: z, name: name)
            npcByUniqueId[uniqueId] = npc
            npcByScene[sceneId, default: []].append(npc)
        }
    }

    // MARK: - Parse npc_raw.txt (Lua table format)

    private func parseNPCRaw(_ text: String) {
        // Lightweight parser for Lua-style NPC table.
        // Extracts staticId, type, signContent, dialogueradius, defaultDialogueIdList presence.
        var currentId: Int?
        var type = 0
        var sign = ""
        var radius: Float = 0
        var hasDialogue = false

        for line in text.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)

            // New NPC block: [12345] = {  (numeric key only, not ["string"] = {)
            if t.hasPrefix("[") && !t.hasPrefix("[\"") && t.contains("] = {") {
                // Flush previous
                if let id = currentId {
                    npcMeta[id] = NPCMeta(staticId: id, type: type, signContent: sign,
                                          dialogueRadius: radius, hasDialogue: hasDialogue)
                }
                currentId = Int(t.drop(while: { $0 == "[" }).prefix(while: { $0.isNumber }))
                type = 0; sign = ""; radius = 0; hasDialogue = false
            }

            if t.hasPrefix("[\"type\"] =") {
                if let v = Int(t.components(separatedBy: "=").last?.trimmingCharacters(in: CharacterSet.decimalDigits.inverted) ?? "") {
                    type = v
                }
            }
            if t.hasPrefix("[\"signContent\"] =") {
                sign = t.components(separatedBy: "\"").dropFirst(3).first.map { String($0) } ?? ""
            }
            if t.hasPrefix("[\"dialogueradius\"] =") {
                if let v = Float(t.components(separatedBy: "=").last?.trimmingCharacters(in: .whitespaces).replacingOccurrences(of: ",", with: "") ?? "") {
                    radius = v
                }
            }
            if t.hasPrefix("[\"defaultDialogueIdList\"] =") {
                hasDialogue = true
            }
        }
        // Flush last
        if let id = currentId {
            npcMeta[id] = NPCMeta(staticId: id, type: type, signContent: sign,
                                  dialogueRadius: radius, hasDialogue: hasDialogue)
        }
    }

    // MARK: - Parse npc_interactive_catalog.csv

    private func parseInteractiveCatalog(_ text: String) {
        // Columns: entry_key,npc_guid,scene_id,scene_x,scene_z,scene_name_key,
        //          static_id,npc_name_key,sign_content_key,sign_icon_id,icon1,icon2,is_interactive
        var first = true
        for line in text.components(separatedBy: "\n") {
            let t = line.trimmingCharacters(in: .whitespaces)
            guard !t.isEmpty else { continue }
            if first { first = false; continue }  // skip header
            let cols = t.components(separatedBy: ",")
            guard cols.count >= 13,
                  let guid    = Int(cols[1]),
                  let sceneId = Int(cols[2]),
                  let sceneX  = Float(cols[3]),
                  let sceneZ  = Float(cols[4]),
                  let staticId = Int(cols[6])
            else { continue }
            let icon1         = cols[10].trimmingCharacters(in: .whitespaces)
            let icon2         = cols[11].trimmingCharacters(in: .whitespaces)
            let isInteractive = cols[12].trimmingCharacters(in: .whitespaces) == "1"
            let entry = NPCInteractive(npcGuid: guid, sceneId: sceneId,
                                       sceneX: sceneX, sceneZ: sceneZ,
                                       staticId: staticId,
                                       icon1: icon1, icon2: icon2,
                                       isInteractive: isInteractive)
            npcInteractive[guid] = entry
            if isInteractive && !icon1.isEmpty {
                knownInteractiveIconKeys.insert(icon1)
            }
        }
    }

    private func bundleDumpsURL() -> URL {
        // Resolve relative to the executable: go up from .app/Contents/MacOS → project root
        let exe = URL(fileURLWithPath: CommandLine.arguments[0])
        // Try going 3 levels up (MacOS → Contents → RoXBot.app → project)
        var candidate = exe
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("bundle_dumps")
        if FileManager.default.fileExists(atPath: candidate.path) { return candidate }

        // Fallback: current working directory
        candidate = URL(fileURLWithPath: FileManager.default.currentDirectoryPath)
            .appendingPathComponent("bundle_dumps")
        return candidate
    }
}
