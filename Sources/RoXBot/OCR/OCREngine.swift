import Vision
import CoreGraphics

/// Apple Vision OCR wrapper — mirrors the Python ocr.py behaviour.
/// All heavy work runs on a detached task so the main actor is never blocked.
struct OCREngine {

    // MARK: - Recognition

    /// Recognise all text in `image`.  Returns regions sorted top→bottom, left→right.
    static func recognize(_ image: CGImage, minConfidence: Float = 0.30) async -> [TextRegion] {
        // Dispatch CPU-bound Vision work off the main thread
        return await Task.detached(priority: .userInitiated) {
            performRecognition(image: image, minConfidence: minConfidence)
        }.value
    }

    // MARK: - Search helpers

    /// First region whose text matches `pattern` (case-insensitive regex).
    static func find(
        _ regions: [TextRegion],
        pattern: String,
        minConfidence: Float = 0.30
    ) -> TextRegion? {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive)
        else { return nil }
        return regions.first { r in
            r.confidence >= minConfidence &&
            regex.firstMatch(in: r.text, range: NSRange(r.text.startIndex..., in: r.text)) != nil
        }
    }

    /// All regions matching `pattern`.
    static func findAll(
        _ regions: [TextRegion],
        pattern: String,
        minConfidence: Float = 0.30
    ) -> [TextRegion] {
        guard let regex = try? NSRegularExpression(pattern: pattern, options: .caseInsensitive)
        else { return [] }
        return regions.filter { r in
            r.confidence >= minConfidence &&
            regex.firstMatch(in: r.text, range: NSRange(r.text.startIndex..., in: r.text)) != nil
        }
    }

    // MARK: - Private

    private static func performRecognition(image: CGImage, minConfidence: Float) -> [TextRegion] {
        let request = VNRecognizeTextRequest()
        request.recognitionLevel       = .accurate
        request.usesLanguageCorrection = false          // preserve game text like [Main]
        request.recognitionLanguages   = ["en-US"]

        let handler = VNImageRequestHandler(cgImage: image, options: [:])
        do {
            try handler.perform([request])
        } catch {
            print("[OCR] Error: \(error)")
            return []
        }

        guard let observations = request.results else { return [] }

        let w = CGFloat(image.width)
        let h = CGFloat(image.height)

        return observations.compactMap { obs -> TextRegion? in
            guard let candidate = obs.topCandidates(1).first,
                  candidate.confidence >= minConfidence
            else { return nil }

            // Vision uses normalised coords with bottom-left origin → flip to top-left
            let b      = obs.boundingBox
            let x      = Int(b.minX * w)
            let y      = Int((1.0 - b.maxY) * h)
            let width  = max(Int(b.width  * w), 1)
            let height = max(Int(b.height * h), 1)

            return TextRegion(
                text:       candidate.string,
                x: x, y: y,
                width:  width,
                height: height,
                confidence: candidate.confidence
            )
        }
        .sorted { $0.cy == $1.cy ? $0.cx < $1.cx : $0.cy < $1.cy }
    }
}
