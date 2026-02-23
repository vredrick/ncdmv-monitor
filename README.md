# NC DMV Appointment Availability Monitor

Monitors the NC DOT "Skip the Line" appointment scheduler for available appointment slots at specified DMV locations. Uses headless browser automation (Playwright) to navigate the session-based web application and detect openings.

## Quick Start

```bash
# 1. Install Python dependencies
pip install playwright

# 2. Install Chromium for Playwright
playwright install chromium

# 3. (Optional) Edit config.py to set your locations
#    Default: Hendersonville, Brevard, Asheville

# 4. Run a single check
python ncdmv_monitor.py

# 5. Run continuous monitoring
python ncdmv_monitor.py --loop
```

## Usage

```
python ncdmv_monitor.py                              # Single check, console output
python ncdmv_monitor.py --loop                       # Continuous monitoring
python ncdmv_monitor.py --loop --interval 120        # Custom interval (seconds)
python ncdmv_monitor.py --json                       # Single check, JSON output
python ncdmv_monitor.py --all                        # Monitor all ~100 locations
python ncdmv_monitor.py --locations "Hendersonville,Asheville"  # Override config
python ncdmv_monitor.py -v                           # Verbose/debug logging
```

### Flags

| Flag | Description |
|------|-------------|
| `--loop` | Run continuously instead of a single check |
| `--interval N` | Check interval in seconds (default: 180, minimum: 60) |
| `--json` | Output results as JSON to stdout |
| `--all` | Monitor all ~100 NC DMV locations |
| `--locations "A,B,C"` | Comma-separated location names (overrides config.py) |
| `-v, --verbose` | Enable debug-level logging |
| `--no-dashboard` | Disable writing `docs/data.json` for the web dashboard |
| `--git-push` | Auto git commit and push `docs/data.json` after each check |

## Configuration

Edit `config.py` to change defaults:

```python
MONITORED_LOCATIONS = ["Hendersonville", "Brevard", "Asheville"]
CHECK_INTERVAL = 180       # seconds
```

Or configure inline at the top of `ncdmv_monitor.py`.

### Supported Locations

The site has ~100 DMV locations across North Carolina. Some commonly monitored ones:

| Name | Data ID | Address |
|------|---------|---------|
| Hendersonville | 130 | 125 Baystone Dr., Hendersonville, NC 28791 |
| Brevard | 101 | 50 Commerce St., Unit 4, Brevard, NC 28712 |
| Asheville | 124 | 1624 Patton Ave., Asheville, NC 28806 |

Use `--all` to see all locations, or run once with `--all --json` to get a full list.

## Notifications

The bot provides a callback hook `on_availability_change(event)` in `ncdmv_monitor.py`. The event dict contains:

```python
{
    "type": "new_opening",      # or "still_available", "slot_taken"
    "location": { ... },        # full location dict
    "previous_state": False,
    "current_state": True,
    "timestamp": "2026-02-22T11:30:00-05:00"
}
```

Commented-out example implementations are included for:
- Email via SMTP (Gmail)
- SMS via Twilio
- Discord webhook
- Slack webhook
- Desktop notification (plyer)

Uncomment and configure whichever method you prefer.

## Running as a Service

Copy and edit the included systemd unit file:

```bash
# Edit the service file with your paths
sudo cp ncdmv_monitor.service /etc/systemd/system/
sudo nano /etc/systemd/system/ncdmv_monitor.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable ncdmv_monitor
sudo systemctl start ncdmv_monitor

# Check status / logs
sudo systemctl status ncdmv_monitor
journalctl -u ncdmv_monitor -f
```

## Dashboard

The monitor writes a `docs/data.json` file after each check cycle. A static `docs/index.html` dashboard reads that file and displays location availability, so you can check status from any device.

The dashboard is a secondary "check whenever" status page — the primary alerting mechanism is `on_availability_change()` (email, SMS, Discord, Slack, desktop notifications).

### GitHub Pages Setup

```bash
# 1. Initialize repo and push
git init && git add . && git commit -m "Initial commit"
gh repo create ncdmv-monitor --private --source=. --push

# 2. Enable GitHub Pages
#    Settings > Pages > Source: Deploy from a branch
#    Branch: main, folder: /docs

# 3. Run the monitor with auto-push
python ncdmv_monitor.py --loop --git-push
```

The dashboard auto-refreshes every 30 seconds. For local testing:

```bash
python -m http.server 8000 --directory docs
# Open http://localhost:8000
```

### Dashboard Config

In `config.py`:

```python
DASHBOARD_ENABLED = True           # Set to False to disable
DASHBOARD_DATA_FILE = "docs/data.json"
DASHBOARD_HISTORY_LIMIT = 50       # Max change events to keep
GIT_AUTO_PUSH = False              # Or use --git-push flag
```

## Files

| File | Description |
|------|-------------|
| `ncdmv_monitor.py` | Main script (self-contained) |
| `config.py` | External configuration (optional) |
| `docs/index.html` | Static web dashboard |
| `docs/data.json` | Auto-generated dashboard data (do not edit) |
| `docs/.nojekyll` | Tells GitHub Pages to skip Jekyll processing |
| `ncdmv_state.json` | Auto-generated state tracking between checks |
| `ncdmv_monitor.log` | Auto-generated log file |
| `ncdmv_monitor.service` | Sample systemd unit file |
| `requirements.txt` | Python dependencies |

## How It Works

1. Launches a headless Chromium browser via Playwright
2. Navigates to the NC DOT appointment scheduler
3. Clicks "Make an Appointment" to reach the location selection page
4. Parses all ~100 location cards, checking CSS classes and content to determine availability
5. Filters to your monitored locations and reports results
6. In loop mode, compares against previous state to detect changes and fires the notification hook
7. Closes the browser after each check to keep resource usage low

## Troubleshooting

- **No locations found**: Check `ncdmv_debug_screenshot.png` — the site may have changed its layout
- **Timeouts**: The site can be slow; try increasing `PAGE_TIMEOUT` in config
- **Rate limiting/CAPTCHA**: If the site starts blocking, increase the check interval
- **"playwright not found"**: Make sure you ran `playwright install chromium`
