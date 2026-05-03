import ScreenCaptureKit
import CoreGraphics
import Foundation

// MARK: - Frame handler type

typealias FrameHandler = @Sendable (CGImage, CGRect) async -> Void

// MARK: - FramePipeline

/// Polls the RöX window at a fixed interval using SCScreenshotManager.
/// Each captured frame is passed to `onFrame` for OCR processing.
actor FramePipeline {

    // ── Configuration ─────────────────────────────────────────────────────
    /// Interval between captures. 700 ms ≈ 1.4 fps.
    private let interval: Duration = .milliseconds(700)

    // ── State ─────────────────────────────────────────────────────────────
    private var running  = false
    private var onFrame: FrameHandler?

    // MARK: - Public API

    enum PipelineError: Error {
        case windowNotFound
    }

    /// Start polling. Throws `windowNotFound` if RöX isn't visible on first call.
    func start(handler: @escaping FrameHandler) async throws {
        onFrame = handler
        running = true

        // Verify window is reachable on first call (log only once for diagnostics)
        let content = try await SCShareableContent.current
        if ProcessInfo.processInfo.environment["ROX_DEBUG_WINDOWS"] != nil {
            for w in content.windows {
                if let a = w.owningApplication {
                    print("[Pipeline] Window '\(a.applicationName)'  bundle '\(a.bundleIdentifier)'  title '\(w.title ?? "-")'")
                }
            }
        }
        guard WindowCapture.findRoXWindow(in: content) != nil else {
            throw PipelineError.windowNotFound
        }

        // Kick off poll loop on background task
        Task.detached(priority: .userInitiated) { [weak self] in
            await self?.pollLoop()
        }
    }

    func stop() {
        running = false
        onFrame = nil
    }

    // MARK: - Poll loop

    private func pollLoop() async {
        while running {
            await captureAndDeliver()
            try? await Task.sleep(for: interval)
        }
    }

    private func captureAndDeliver() async {
        do {
            let content = try await SCShareableContent.current
            guard let window = WindowCapture.findRoXWindow(in: content) else {
                print("[Pipeline] RöX window lost")
                return
            }
            let bounds = window.frame
            let filter = SCContentFilter(desktopIndependentWindow: window)
            let config = SCStreamConfiguration()
            config.width       = max(1, Int(bounds.width))
            config.height      = max(1, Int(bounds.height))
            config.scalesToFit = true
            config.pixelFormat = kCVPixelFormatType_32BGRA
            config.showsCursor = false

            let image = try await SCScreenshotManager.captureImage(
                contentFilter: filter,
                configuration: config
            )
            print("[Pipeline] Frame \(image.width)x\(image.height)")
            await onFrame?(image, bounds)
        } catch {
            print("[Pipeline] Capture error: \(error)")
        }
    }
}
