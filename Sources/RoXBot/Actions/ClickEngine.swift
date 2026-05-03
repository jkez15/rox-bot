import CoreGraphics
import AppKit

/// Injects mouse clicks into the RöX game via the HID event tap.
///
/// Strategy:
///   1. Activate the RöX window so Unity's input system is listening.
///   2. Post mouseDown + mouseUp via CGEventPost(.cghidEventTap) — the only
///      method Unity/Catalyst reliably accepts.
///   3. Warp the cursor back to its saved position and restore the previously
///      focused app, keeping the automation nearly invisible.
struct ClickEngine {

    private static let targetBundleID = "com.play.rosea"
    private static let hidSource = CGEventSource(stateID: .combinedSessionState)

    // MARK: - Public API (called from @MainActor execute())

    /// Click at window-relative coords (wx, wy).
    /// Must be called from MainActor so NSEvent / NSWorkspace access is safe.
    @MainActor
    static func click(wx: Int, wy: Int, windowBounds: CGRect) async {
        let sx = windowBounds.minX + CGFloat(wx)
        let sy = windowBounds.minY + CGFloat(wy)

        // Capture main-thread state before going async
        let screenH     = NSScreen.main?.frame.height ?? 800
        let savedAppKit = NSEvent.mouseLocation
        let saved       = CGPoint(x: savedAppKit.x, y: screenH - savedAppKit.y)
        let previousApp = NSWorkspace.shared.frontmostApplication

        await postClick(x: sx, y: sy, saved: saved, previousApp: previousApp)
    }

    // MARK: - Core click implementation

    private static func postClick(
        x: CGFloat, y: CGFloat,
        saved: CGPoint,
        previousApp: NSRunningApplication?
    ) async {
        let target = CGPoint(x: x, y: y)

        // 1. Activate RöX — Unity only processes mouse events when it has focus
        if let rox = NSRunningApplication
            .runningApplications(withBundleIdentifier: targetBundleID).first {
            rox.activate(options: .activateIgnoringOtherApps)
            try? await Task.sleep(for: .milliseconds(150))
        }

        // 2. Post HID-level click
        guard
            let down = CGEvent(mouseEventSource: hidSource,
                               mouseType: .leftMouseDown,
                               mouseCursorPosition: target,
                               mouseButton: .left),
            let up   = CGEvent(mouseEventSource: hidSource,
                               mouseType: .leftMouseUp,
                               mouseCursorPosition: target,
                               mouseButton: .left)
        else { return }

        down.post(tap: .cghidEventTap)
        try? await Task.sleep(for: .milliseconds(60))
        up.post(tap: .cghidEventTap)

        print("[Click] HID (\(Int(x)),\(Int(y)))")

        // 3. Snap cursor back
        CGWarpMouseCursorPosition(saved)
        CGAssociateMouseAndMouseCursorPosition(1)

        // 4. Restore previous app focus
        try? await Task.sleep(for: .milliseconds(80))
        previousApp?.activate(options: .activateIgnoringOtherApps)
    }
}
