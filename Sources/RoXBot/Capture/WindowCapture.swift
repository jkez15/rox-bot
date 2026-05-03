import ScreenCaptureKit
import CoreGraphics
import AppKit

/// Utilities for detecting and capturing the RöX game window.
struct WindowCapture {

    /// Shared bundle ID — used by FramePipeline and ClickEngine too.
    static let bundleID = "com.play.rosea"

    // MARK: - Process detection

    static func isRoXRunning() -> Bool {
        !NSRunningApplication.runningApplications(withBundleIdentifier: bundleID).isEmpty
    }

    // MARK: - Single-frame capture (diagnostics / one-shot use)

    static func captureFrame() async -> (image: CGImage, bounds: CGRect)? {
        do {
            let content = try await SCShareableContent.current
            guard let window = findRoXWindow(in: content) else {
                print("[Capture] RöX window not found. Visible windows:")
                for w in content.windows {
                    if let a = w.owningApplication {
                        print("  '\(a.applicationName)'  bundle='\(a.bundleIdentifier)'")
                    }
                }
                return nil
            }
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.width       = Int(window.frame.width)
            config.height      = Int(window.frame.height)
            config.scalesToFit = true
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.showsCursor = false
            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter, configuration: config)
            return (image, window.frame)
        } catch {
            print("[Capture] Error: \(error.localizedDescription)")
            return nil
        }
    }

    // MARK: - Window finder (shared with FramePipeline)

    static func findRoXWindow(in content: SCShareableContent) -> SCWindow? {
        let matches = content.windows.filter { window in
            guard let app = window.owningApplication else { return false }
            if app.bundleIdentifier == bundleID { return true }
            // Strip NFD combining umlaut (U+0308) so "Ro\u{308}X" matches "rox"
            let name = app.applicationName
                .replacingOccurrences(of: "\u{0308}", with: "")
                .lowercased()
            return name == "rox" || name == "rx"
        }
        // Pick the largest window — avoids grabbing splash screens or sub-windows
        return matches.max(by: {
            ($0.frame.width * $0.frame.height) < ($1.frame.width * $1.frame.height)
        })
    }
}
