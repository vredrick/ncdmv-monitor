"""
NC DMV Appointment Monitor - Configuration

Edit this file to customize which locations to monitor and other settings.
Alternatively, use command-line flags to override these values.
"""

# ─── Locations to Monitor ───────────────────────────────────────────────────────
# Specify location names exactly as they appear on the site (case-insensitive).
# Use --all flag to monitor all ~100 locations, or --locations to override.
MONITORED_LOCATIONS = ["Hendersonville", "Brevard", "Asheville"]

# ─── Appointment Type ───────────────────────────────────────────────────────────
# The site requires selecting a service type before showing locations.
# This must match the text shown on the appointment type card on the site.
# Common options:
#   "Driver License - First Time"
#   "Driver License Duplicate"
#   "Driver License Renewal"
#   "ID Card"
#   "Knowledge/Computer Test"
#   "Permits"
#   "Non-CDL Road Test"
SERVICE_TYPE = "Driver License - First Time"

# ─── Scheduler URL ──────────────────────────────────────────────────────────────
SCHEDULER_URL = (
    "https://skiptheline.ncdot.gov/Webapp/Appointment/Index/"
    "a7ade79b-996d-4971-8766-97feb75254de"
)

# ─── Timing ─────────────────────────────────────────────────────────────────────
# Check interval in seconds (minimum 60). Actual interval is randomized ±15%.
CHECK_INTERVAL = 240

# ─── File Paths ─────────────────────────────────────────────────────────────────
LOG_FILE = "ncdmv_monitor.log"
STATE_FILE = "ncdmv_state.json"

# ─── Browser Settings ──────────────────────────────────────────────────────────
# Timeout for waiting for page elements (milliseconds)
PAGE_TIMEOUT = 60000

# Number of retries on failure before giving up for this cycle
MAX_RETRIES = 3

# User agent string (realistic Chrome on Windows)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# ─── Dashboard ─────────────────────────────────────────────────────────────────
# Write a docs/data.json after each check for the static web dashboard.
DASHBOARD_ENABLED = True

# Path to the dashboard data file (relative to script directory)
DASHBOARD_DATA_FILE = "docs/data.json"

# Maximum number of change events to keep in the history
DASHBOARD_HISTORY_LIMIT = 50

# Automatically git add/commit/push docs/data.json after each write
GIT_AUTO_PUSH = False
