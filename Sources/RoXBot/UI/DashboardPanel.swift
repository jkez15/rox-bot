import AppKit

/// Floating HUD dashboard — always-on-top NSPanel.
/// All methods are @MainActor since they touch AppKit.
@MainActor
final class DashboardPanel: NSObject {

    // ── State ─────────────────────────────────────────────────────────────
    private(set) var stopRequested = false
    private(set) var paused        = false

    private var started               = false
    private var startContinuation: CheckedContinuation<Void, Never>?

    private var cycleCount  = 0
    private var actionCount = 0

    // ── UI ────────────────────────────────────────────────────────────────
    private var panel:        NSPanel!
    private var statusLabel:  NSTextField!
    private var actionLabel:  NSTextField!
    private var questLabel:   NSTextField!
    private var cycleLabel:   NSTextField!
    private var startBtn:     NSButton!
    private var pauseBtn:     NSButton!
    private var logTextView:  NSTextView!

    // MARK: - Lifecycle

    func show() {
        buildWindow()
        panel.makeKeyAndOrderFront(nil)
        NSApp.activate(ignoringOtherApps: true)
    }

    // MARK: - Async gate (called by AutomationEngine before loop starts)

    func waitForStart() async {
        if started { return }
        await withCheckedContinuation { cont in
            if started {
                cont.resume()   // clicked between the check above and here
            } else {
                startContinuation = cont
            }
        }
    }

    // MARK: - Public state

    func setStatus(_ message: String) {
        statusLabel?.stringValue = message
    }

    func setAction(_ message: String) {
        actionLabel?.stringValue = message
    }

    func setQuest(title: String, step: String, distance: Int?) {
        let distStr = distance.map { "  \($0) m" } ?? ""
        questLabel?.stringValue = "\(title)\n\(step)\(distStr)"
    }

    func log(_ message: String) {
        let time = timeString()
        let line = "[\(time)] \(message)\n"
        let attrs: [NSAttributedString.Key: Any] = [
            .font:            NSFont(name: "Menlo", size: 8) ?? NSFont.systemFont(ofSize: 8),
            .foregroundColor: NSColor.green,
        ]
        logTextView?.textStorage?.append(NSAttributedString(string: line, attributes: attrs))
        logTextView?.scrollToEndOfDocument(nil)
    }

    func incrementCycle() {
        cycleCount += 1
        refreshCycleLabel()
    }

    func incrementActions() {
        actionCount += 1
        refreshCycleLabel()
    }

    // MARK: - Button actions

    @objc private func startPressed() {
        started = true
        startBtn.title   = "▶ Running"
        startBtn.isEnabled = false
        startContinuation?.resume()
        startContinuation = nil
    }

    @objc private func pausePressed() {
        paused.toggle()
        pauseBtn.title = paused ? "▶ Resume" : "⏸ Pause"
        setStatus(paused ? "Paused" : "Running")
    }

    @objc private func stopPressed() {
        stopRequested = true
        startContinuation?.resume()   // unblock waitForStart if still waiting
        startContinuation = nil
        setStatus("Stopping…")
    }

    // MARK: - Private helpers

    private func refreshCycleLabel() {
        cycleLabel?.stringValue = "Cycles: \(cycleCount)   Actions: \(actionCount)"
    }

    private func timeString() -> String {
        let f = DateFormatter()
        f.dateFormat = "HH:mm:ss"
        return f.string(from: Date())
    }

    // MARK: - Window construction

    private func buildWindow() {
        panel = NSPanel(
            contentRect: NSRect(x: 20, y: 200, width: 320, height: 520),
            styleMask:   [.titled, .closable, .utilityWindow,
                          .nonactivatingPanel, .hudWindow],
            backing:     .buffered,
            defer:       false
        )
        panel.title            = "RöX Bot"
        panel.level            = .floating
        panel.isFloatingPanel  = true
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        panel.isMovableByWindowBackground = true

        let root = panel.contentView!

        let stack = NSStackView()
        stack.orientation = .vertical
        stack.alignment   = .leading
        stack.spacing     = 8
        stack.edgeInsets  = NSEdgeInsets(top: 12, left: 12, bottom: 12, right: 12)
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor  .constraint(equalTo: root.leadingAnchor),
            stack.trailingAnchor .constraint(equalTo: root.trailingAnchor),
            stack.topAnchor      .constraint(equalTo: root.topAnchor),
            stack.bottomAnchor   .constraint(equalTo: root.bottomAnchor),
        ])

        // Status
        statusLabel = makeLabel("Idle — press ▶ Start", size: 11, bold: true)
        stack.addArrangedSubview(statusLabel)

        // Quest info
        questLabel = makeLabel("No quest detected", size: 10)
        questLabel.maximumNumberOfLines = 3
        stack.addArrangedSubview(questLabel)

        // Current action
        actionLabel = makeLabel("—", size: 10)
        actionLabel.maximumNumberOfLines = 2
        stack.addArrangedSubview(actionLabel)

        // Cycle counter
        cycleLabel = makeLabel("Cycles: 0   Actions: 0", size: 9)
        stack.addArrangedSubview(cycleLabel)

        // Separator
        let sep = NSBox(); sep.boxType = .separator
        stack.addArrangedSubview(sep)

        // Button row
        let btnRow = NSStackView()
        btnRow.orientation = .horizontal
        btnRow.spacing     = 8

        startBtn = NSButton(title: "▶ Start",  target: self, action: #selector(startPressed))
        pauseBtn = NSButton(title: "⏸ Pause",  target: self, action: #selector(pausePressed))
        let stopBtn = NSButton(title: "⏹ Stop", target: self, action: #selector(stopPressed))

        for btn in [startBtn!, pauseBtn!, stopBtn] {
            btn.bezelStyle = .rounded
            btn.font       = NSFont.systemFont(ofSize: 11)
            btnRow.addArrangedSubview(btn)
        }
        stack.addArrangedSubview(btnRow)

        // Log scroll view
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller  = true
        scrollView.autohidesScrollers   = true
        scrollView.translatesAutoresizingMaskIntoConstraints = false

        let tv = NSTextView(frame: .zero)
        tv.isEditable        = false
        tv.backgroundColor   = NSColor.black.withAlphaComponent(0.7)
        tv.textColor         = .green
        tv.font              = NSFont(name: "Menlo", size: 8) ?? NSFont.systemFont(ofSize: 8)
        tv.isVerticallyResizable   = true
        tv.isHorizontallyResizable = false
        tv.textContainer?.widthTracksTextView = true

        scrollView.documentView = tv
        logTextView = tv

        stack.addArrangedSubview(scrollView)
        scrollView.widthAnchor .constraint(equalTo: stack.widthAnchor, constant: -24).isActive = true
        scrollView.heightAnchor.constraint(equalToConstant: 220).isActive = true
    }

    private func makeLabel(_ text: String, size: CGFloat, bold: Bool = false) -> NSTextField {
        let lbl = NSTextField(labelWithString: text)
        lbl.font = bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size)
        lbl.lineBreakMode = .byWordWrapping
        lbl.maximumNumberOfLines = 2
        return lbl
    }
}
