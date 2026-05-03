import AppKit

/// Floating HUD dashboard — always-on-top NSPanel.
/// All methods are @MainActor since they touch AppKit.
@MainActor
final class DashboardPanel: NSObject {

    // ── State ─────────────────────────────────────────────────────────────
    private(set) var stopRequested = false
    private(set) var paused        = false
    private(set) var selectedMode: AutomationMode = .mainQuest

    private var started               = false
    private var startContinuation: CheckedContinuation<Void, Never>?

    private var cycleCount  = 0
    private var actionCount = 0

    // Callback — engine subscribes to mode changes
    var onModeChanged: ((AutomationMode) -> Void)?

    // ── UI ────────────────────────────────────────────────────────────────
    private var panel:        NSPanel!
    private var statusLabel:  NSTextField!
    private var actionLabel:  NSTextField!
    private var questLabel:   NSTextField!
    private var cycleLabel:   NSTextField!
    private var startBtn:     NSButton!
    private var pauseBtn:     NSButton!
    private var logTextView:  NSTextView!
    private var modeButtons:  [AutomationMode: NSButton] = [:]

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

    @objc private func modePressed(_ sender: NSButton) {
        guard let mode = AutomationMode.allCases.first(where: { $0.rawValue == sender.identifier?.rawValue }) else { return }
        selectedMode = mode
        updateModeHighlights()
        onModeChanged?(mode)
        log("\(mode.icon) Mode → \(mode.rawValue)")
    }

    // MARK: - Private helpers

    private func updateModeHighlights() {
        for (mode, btn) in modeButtons {
            if mode == selectedMode {
                btn.bezelColor = NSColor.systemBlue
                btn.contentTintColor = .white
            } else {
                btn.bezelColor = nil
                btn.contentTintColor = .secondaryLabelColor
            }
        }
    }

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
            contentRect: NSRect(x: 20, y: 200, width: 380, height: 620),
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
        stack.spacing     = 6
        stack.edgeInsets  = NSEdgeInsets(top: 10, left: 12, bottom: 10, right: 12)
        stack.translatesAutoresizingMaskIntoConstraints = false
        root.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor  .constraint(equalTo: root.leadingAnchor),
            stack.trailingAnchor .constraint(equalTo: root.trailingAnchor),
            stack.topAnchor      .constraint(equalTo: root.topAnchor),
            stack.bottomAnchor   .constraint(equalTo: root.bottomAnchor),
        ])

        // ── Section: Status ──────────────────────────────────────────────
        statusLabel = makeLabel("Idle — press ▶ Start", size: 11, bold: true)
        stack.addArrangedSubview(statusLabel)

        // ── Section: Quest info ──────────────────────────────────────────
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

        // ── Separator ────────────────────────────────────────────────────
        stack.addArrangedSubview(makeSeparator())

        // ── Section: Mode Selector ───────────────────────────────────────
        let modeHeader = makeLabel("AUTOMATION MODE", size: 9, bold: true)
        modeHeader.textColor = .tertiaryLabelColor
        stack.addArrangedSubview(modeHeader)

        // Row 1: Main Quest, Commission Board
        let modeRow1 = NSStackView()
        modeRow1.orientation = .horizontal
        modeRow1.spacing     = 6
        modeRow1.distribution = .fillEqually
        modeRow1.translatesAutoresizingMaskIntoConstraints = false

        let mainQuestBtn       = makeModeButton(.mainQuest)
        let commissionBoardBtn = makeModeButton(.commissionBoard)
        modeRow1.addArrangedSubview(mainQuestBtn)
        modeRow1.addArrangedSubview(commissionBoardBtn)
        stack.addArrangedSubview(modeRow1)
        modeRow1.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -24).isActive = true

        // Row 2: Daily Quests, Guild Quests, Auto-Potion
        let modeRow2 = NSStackView()
        modeRow2.orientation = .horizontal
        modeRow2.spacing     = 6
        modeRow2.distribution = .fillEqually
        modeRow2.translatesAutoresizingMaskIntoConstraints = false

        let dailyBtn  = makeModeButton(.dailyQuests)
        let guildBtn  = makeModeButton(.guildQuests)
        let potionBtn = makeModeButton(.autoPotion)
        modeRow2.addArrangedSubview(dailyBtn)
        modeRow2.addArrangedSubview(guildBtn)
        modeRow2.addArrangedSubview(potionBtn)
        stack.addArrangedSubview(modeRow2)
        modeRow2.widthAnchor.constraint(equalTo: stack.widthAnchor, constant: -24).isActive = true

        updateModeHighlights()

        // ── Separator ────────────────────────────────────────────────────
        stack.addArrangedSubview(makeSeparator())

        // ── Section: Control Buttons ─────────────────────────────────────
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

        // ── Section: Log Output ──────────────────────────────────────────
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
        scrollView.heightAnchor.constraint(equalToConstant: 200).isActive = true
    }

    // MARK: - UI factory helpers

    private func makeLabel(_ text: String, size: CGFloat, bold: Bool = false) -> NSTextField {
        let lbl = NSTextField(labelWithString: text)
        lbl.font = bold ? NSFont.boldSystemFont(ofSize: size) : NSFont.systemFont(ofSize: size)
        lbl.lineBreakMode = .byWordWrapping
        lbl.maximumNumberOfLines = 2
        return lbl
    }

    private func makeSeparator() -> NSBox {
        let sep = NSBox()
        sep.boxType = .separator
        return sep
    }

    private func makeModeButton(_ mode: AutomationMode) -> NSButton {
        let btn = NSButton(title: "\(mode.icon) \(mode.rawValue)", target: self, action: #selector(modePressed(_:)))
        btn.identifier = NSUserInterfaceItemIdentifier(mode.rawValue)
        btn.bezelStyle = .rounded
        btn.font       = NSFont.systemFont(ofSize: 10)
        btn.setButtonType(.momentaryPushIn)
        modeButtons[mode] = btn
        return btn
    }
}
