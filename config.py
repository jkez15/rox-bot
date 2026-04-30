# ─── RoX Bot Configuration ────────────────────────────────────────────────────

# Exact process name as it appears in `ps aux`
APP_PROCESS_NAME = "RX"

# Exact window owner name as reported by macOS Quartz (used for window capture)
# macOS reports this in Unicode NFD form: o + combining umlaut (\u0308)
APP_WINDOW_NAME = "Ro\u0308X"

# How often (seconds) to poll for the app when it's not yet running
POLL_INTERVAL = 3.0

# How often (seconds) to run the main automation loop when app is running
LOOP_INTERVAL = 1.0

# Path to folder containing UI template images for matching
TEMPLATES_DIR = "templates"

# Confidence threshold for template matching (0.0 – 1.0)
MATCH_THRESHOLD = 0.8

# Set to True to show live annotated capture window (useful for debugging)
DEBUG_PREVIEW = False

# ─── Quest Automation ─────────────────────────────────────────────────────────

# Seconds to wait between quest clicks (gives the character time to walk/run)
QUEST_CLICK_INTERVAL = 3.0

# If template matching fails but the quest panel IS open, fall back to
# clicking a hardcoded relative coordinate inside the panel.
QUEST_PANEL_FALLBACK = True
