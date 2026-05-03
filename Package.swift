// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "RoXBot",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "RoXBot", targets: ["RoXBot"]),
    ],
    targets: [
        .executableTarget(
            name: "RoXBot",
            path: "Sources/RoXBot"
        ),
    ]
)
