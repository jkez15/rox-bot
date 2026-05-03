import AppKit

// Top-level code in main.swift runs on the main thread.
// assumeIsolated asserts this to the Swift 6 concurrency checker.
MainActor.assumeIsolated {
    let app = NSApplication.shared
    app.setActivationPolicy(.accessory)   // No Dock icon — floating HUD only
    let delegate = AppDelegate()
    app.delegate = delegate
    app.run()
}
