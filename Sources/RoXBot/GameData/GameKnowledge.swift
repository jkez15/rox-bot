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
    // From npc_scene.txt: unique_id 10101013 = 委托板 (commission board Prontera)
    static let commissionBoardIds: Set<Int> = [
        10101013, // Prontera
        11101013, // Izlude  (pattern: scene*10000 + 1013)
        12101009, // Geffen
        13101009, // Morroc
        14101007, // Alberta
    ]

    func load() {
        let url = bundleDumpsURL().appendingPathComponent("npc_scene.txt")
        guard let text = try? String(contentsOf: url, encoding: .utf8) else {
            print("[GameKnowledge] ⚠️ npc_scene.txt not found — NPC data unavailable")
            return
        }
        parseNPCScene(text)
        print("[GameKnowledge] Loaded \(npcByUniqueId.count) scene NPCs across \(npcByScene.count) scenes")
    }

    func npcsInScene(_ sceneId: Int) -> [SceneNPC] {
        npcByScene[sceneId] ?? []
    }

    func npc(uniqueId: Int) -> SceneNPC? {
        npcByUniqueId[uniqueId]
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
