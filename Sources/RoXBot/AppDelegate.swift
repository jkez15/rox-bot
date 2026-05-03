import AppKit

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {

    nonisolated func applicationDidFinishLaunching(_ notification: Notification) {
        MainActor.assumeIsolated {
            let dashboard = DashboardPanel()
            dashboard.show()
            let engine = AutomationEngine(dashboard: dashboard)
            Task { await engine.start() }
        }
    }

    nonisolated func applicationWillTerminate(_ notification: Notification) {
        // Engine stops itself when stop is requested via dashboard
    }

    nonisolated func applicationShouldTerminateAfterLastWindowClosed(_ sender: NSApplication) -> Bool {
        false
    }
}
