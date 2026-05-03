import CoreGraphics

/// One OCR text result with position in the captured image (top-left origin).
struct TextRegion {
    let text: String
    let x: Int
    let y: Int
    let width: Int
    let height: Int
    let confidence: Float

    /// Centre x in image coordinates
    var cx: Int { x + width  / 2 }
    /// Centre y in image coordinates
    var cy: Int { y + height / 2 }

    var bounds: CGRect { CGRect(x: x, y: y, width: width, height: height) }
}
