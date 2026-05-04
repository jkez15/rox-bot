import CoreGraphics

/// Screen zone constants in logical pixels (1× resolution, 1051×816 base window).
///
/// Matches the calibrated values from the original bot.
enum Zones {

    // ── Boundaries ──────────────────────────────────────────────────────────
    static let questPanelXMax = 260   // sidebar right edge
    static let hudTopYMax     = 300   // top HUD bottom edge
    static let gameWorldYMax  = 620   // game world bottom edge
    static let dialogYMin     = 620   // chat/dialog zone starts
    static let dialogYMax     = 770   // chat/dialog zone ends

    // ── HP / SP bar pixel regions (top-left HUD, logical px) ────────────────
    // These are approximate — calibrate on the Mac by inspecting the HUD.
    // HP bar: a red horizontal bar roughly at (30, 12) to (180, 22)
    // SP bar: a blue horizontal bar roughly at (30, 28) to (180, 38)
    static let hpBarX1 = 30;  static let hpBarX2 = 180
    static let hpBarY1 = 12;  static let hpBarY2 = 22
    static let spBarX1 = 30;  static let spBarX2 = 180
    static let spBarY1 = 28;  static let spBarY2 = 38

    // ── Potion thresholds (0.0 – 1.0 fill ratio) ────────────────────────────
    /// Use HP potion when HP fill < this fraction.
    static let hpPotionThreshold: Float = 0.60
    /// Use SP potion when SP fill < this fraction.
    static let spPotionThreshold: Float = 0.40

    // ── Potion hotkeys (CGKeyCode) ───────────────────────────────────────────
    // Default: F1 for HP potion, F2 for SP potion.
    // Override here if the game uses different bindings.
    static let hpPotionKey: CGKeyCode = 122   // F1
    static let spPotionKey: CGKeyCode = 120   // F2

    // ── Zone classification ──────────────────────────────────────────────────
    enum Kind { case sidebar, hudTop, world, dialog, hudBottom }

    static func classify(cx: Int, cy: Int) -> Kind {
        if cx < questPanelXMax { return .sidebar  }
        if cy < hudTopYMax     { return .hudTop   }
        if cy < gameWorldYMax  { return .world    }
        if cy < dialogYMax     { return .dialog   }
        return .hudBottom
    }

    /// True if the coordinate is in the interactive game world zone.
    static func isGameWorld(cx: Int, cy: Int) -> Bool {
        cx > questPanelXMax && cy > hudTopYMax && cy < gameWorldYMax
    }

    /// True if the coordinate is in the dialog/chat zone.
    static func isDialogZone(cx: Int, cy: Int) -> Bool {
        cy >= dialogYMin && cy < dialogYMax
    }
}
