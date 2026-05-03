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
