#!/usr/bin/env python3
"""
NC DMV Appointment Availability Monitor

Monitors the NC DOT "Skip the Line" appointment scheduler for available
appointment slots at specified DMV locations using headless browser automation.

Usage:
    python ncdmv_monitor.py                              # Single check
    python ncdmv_monitor.py --loop                       # Continuous monitoring
    python ncdmv_monitor.py --loop --interval 120        # Custom interval
    python ncdmv_monitor.py --json                       # JSON output
    python ncdmv_monitor.py --all                        # All locations
    python ncdmv_monitor.py --locations "Hendersonville,Asheville"
"""

import argparse
import json
import logging
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

# ─── Inline Configuration (overridden by config.py if present) ──────────────────
MONITORED_LOCATIONS = ["Hendersonville", "Brevard", "Asheville"]
SCHEDULER_URL = (
    "https://skiptheline.ncdot.gov/Webapp/Appointment/Index/"
    "a7ade79b-996d-4971-8766-97feb75254de"
)
SERVICE_TYPE = "Driver License - First Time"
CHECK_INTERVAL = 240
LOG_FILE = "ncdmv_monitor.log"
STATE_FILE = "ncdmv_state.json"
PAGE_TIMEOUT = 60000
MAX_RETRIES = 3
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
DASHBOARD_ENABLED = True
DASHBOARD_DATA_FILE = "docs/data.json"
DASHBOARD_HISTORY_LIMIT = 50
GIT_AUTO_PUSH = False

# Try to load external config.py if it exists alongside this script
_script_dir = os.path.dirname(os.path.abspath(__file__))
_config_path = os.path.join(_script_dir, "config.py")
if os.path.isfile(_config_path):
    import importlib.util

    _spec = importlib.util.spec_from_file_location("config", _config_path)
    _cfg = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_cfg)
    for _name in [
        "MONITORED_LOCATIONS", "SCHEDULER_URL", "SERVICE_TYPE", "CHECK_INTERVAL",
        "LOG_FILE", "STATE_FILE", "PAGE_TIMEOUT", "MAX_RETRIES", "USER_AGENT",
        "DASHBOARD_ENABLED", "DASHBOARD_DATA_FILE", "DASHBOARD_HISTORY_LIMIT",
        "GIT_AUTO_PUSH",
    ]:
        if hasattr(_cfg, _name):
            globals()[_name] = getattr(_cfg, _name)


# ─── Logging Setup ──────────────────────────────────────────────────────────────

logger = logging.getLogger("ncdmv_monitor")


def setup_logging(verbose: bool = False) -> None:
    """Configure logging to console and file."""
    level = logging.DEBUG if verbose else logging.INFO
    logger.setLevel(level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    logger.addHandler(console)

    # File handler
    try:
        fh = logging.FileHandler(LOG_FILE)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except OSError as e:
        logger.warning("Could not open log file %s: %s", LOG_FILE, e)


# ─── Notification Hook ──────────────────────────────────────────────────────────

def on_availability_change(event: dict) -> None:
    """
    Callback invoked when a location's availability changes.

    Override or extend this function to add custom notifications.

    Args:
        event: Dict with keys:
            - type: "new_opening" | "still_available" | "slot_taken"
            - location: Full location dict (name, data_id, address, etc.)
            - previous_state: bool (was it available before?)
            - current_state: bool (is it available now?)
            - timestamp: ISO 8601 timestamp string
    """
    if event["type"] == "new_opening":
        loc = event["location"]
        logger.info(
            "*** NEW OPENING at %s (%s) ***",
            loc["name"], loc["address"],
        )
        # Print a loud banner to the console so it's impossible to miss
        print("\n" + "!" * 60)
        print(f"  APPOINTMENT AVAILABLE AT {loc['name'].upper()}!")
        print(f"  Address: {loc['address']}")
        print(f"  Book now: {SCHEDULER_URL}")
        print("!" * 60 + "\n")
    elif event["type"] == "slot_taken":
        loc = event["location"]
        logger.info(
            "Slot no longer available at %s", loc["name"],
        )

    # ── Uncomment and configure one of the notification methods below ──

    # ── Email via SMTP (Gmail example) ──
    # import smtplib
    # from email.mime.text import MIMEText
    #
    # def send_email(event):
    #     loc = event["location"]
    #     msg = MIMEText(
    #         f"DMV appointment available at {loc['name']}!\n"
    #         f"Address: {loc['address']}\n"
    #         f"Check: {SCHEDULER_URL}"
    #     )
    #     msg["Subject"] = f"DMV Opening: {loc['name']}"
    #     msg["From"] = "your_email@gmail.com"
    #     msg["To"] = "your_email@gmail.com"
    #     with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
    #         server.login("your_email@gmail.com", "your_app_password")
    #         server.send_message(msg)
    #
    # if event["type"] == "new_opening":
    #     send_email(event)

    # ── SMS via Twilio ──
    # from twilio.rest import Client
    #
    # def send_sms(event):
    #     client = Client("TWILIO_ACCOUNT_SID", "TWILIO_AUTH_TOKEN")
    #     loc = event["location"]
    #     client.messages.create(
    #         body=f"DMV opening at {loc['name']}! {loc['address']}",
    #         from_="+1TWILIO_NUMBER",
    #         to="+1YOUR_NUMBER",
    #     )
    #
    # if event["type"] == "new_opening":
    #     send_sms(event)

    # ── Discord Webhook ──
    # import urllib.request
    #
    # def send_discord(event):
    #     loc = event["location"]
    #     payload = json.dumps({
    #         "content": (
    #             f"🚨 **DMV Opening at {loc['name']}!**\n"
    #             f"Address: {loc['address']}\n"
    #             f"Book now: {SCHEDULER_URL}"
    #         )
    #     }).encode()
    #     req = urllib.request.Request(
    #         "https://discord.com/api/webhooks/YOUR/WEBHOOK_URL",
    #         data=payload,
    #         headers={"Content-Type": "application/json"},
    #     )
    #     urllib.request.urlopen(req)
    #
    # if event["type"] == "new_opening":
    #     send_discord(event)

    # ── Slack Webhook ──
    # import urllib.request
    #
    # def send_slack(event):
    #     loc = event["location"]
    #     payload = json.dumps({
    #         "text": (
    #             f"🚨 DMV Opening at {loc['name']}!\n"
    #             f"Address: {loc['address']}\n"
    #             f"Book now: {SCHEDULER_URL}"
    #         )
    #     }).encode()
    #     req = urllib.request.Request(
    #         "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
    #         data=payload,
    #         headers={"Content-Type": "application/json"},
    #     )
    #     urllib.request.urlopen(req)
    #
    # if event["type"] == "new_opening":
    #     send_slack(event)

    # ── Desktop Notification (using plyer) ──
    # from plyer import notification
    #
    # def send_desktop_notification(event):
    #     loc = event["location"]
    #     notification.notify(
    #         title=f"DMV Opening: {loc['name']}",
    #         message=f"Appointment available at {loc['address']}",
    #         timeout=30,
    #     )
    #
    # if event["type"] == "new_opening":
    #     send_desktop_notification(event)


# ─── State Management ───────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load the previous availability state from disk."""
    if os.path.isfile(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load state file: %s", e)
    return {}


def save_state(state: dict) -> None:
    """Persist the current availability state to disk."""
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(state, f, indent=2)
    except OSError as e:
        logger.warning("Could not save state file: %s", e)


def process_changes(
    locations: list[dict], previous_state: dict
) -> tuple[dict, list[dict]]:
    """
    Compare current results against previous state and emit change events.

    Returns:
        (new_state, events) — updated state dict and list of change event dicts.
    """
    now = datetime.now(timezone.utc).astimezone().isoformat()
    new_state = {}
    events = []

    for loc in locations:
        key = loc["data_id"]
        was_available = previous_state.get(key, {}).get("available", False)
        is_available = loc["available"]
        new_state[key] = {"available": is_available, "name": loc["name"]}

        if is_available and not was_available:
            event = {
                "type": "new_opening",
                "location": loc,
                "previous_state": False,
                "current_state": True,
                "timestamp": now,
            }
            events.append(event)
            on_availability_change(event)
        elif is_available and was_available:
            event = {
                "type": "still_available",
                "location": loc,
                "previous_state": True,
                "current_state": True,
                "timestamp": now,
            }
            events.append(event)
            on_availability_change(event)
        elif not is_available and was_available:
            event = {
                "type": "slot_taken",
                "location": loc,
                "previous_state": True,
                "current_state": False,
                "timestamp": now,
            }
            events.append(event)
            on_availability_change(event)
        else:
            # Still unavailable — debug only
            logger.debug("No change: %s still unavailable", loc["name"])

    return new_state, events


# ─── Scraping ────────────────────────────────────────────────────────────────────

def scrape_locations() -> list[dict]:
    """
    Launch a headless browser, navigate through the appointment flow,
    and extract all location availability data.

    The flow is:
      1. GET welcome page
      2. Click "Make an Appointment"
      3. Select the appointment/service type (e.g. "Driver License - First Time")
      4. Wait for the "Select a Location" page with ~100 DMV locations
      5. Parse all location cards

    Returns:
        List of location dicts with name, data_id, address, distance, available,
        and checked_at fields.

    Raises:
        RuntimeError: If the page cannot be loaded or parsed.
    """
    now = datetime.now(timezone.utc).astimezone().isoformat()

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=USER_AGENT,
            viewport={"width": 1920, "height": 1080},
        )
        page = context.new_page()

        try:
            # ── Step 1: Load the welcome page ──
            logger.debug("Navigating to scheduler URL...")
            page.goto(SCHEDULER_URL, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT)
            # Give the page extra time to finish loading dynamic content
            page.wait_for_timeout(3000)

            # ── Step 2: Click "Make an Appointment" ──
            logger.debug("Clicking 'Make an Appointment'...")
            make_appt_btn = page.locator("button:has-text('Make an Appointment')")
            make_appt_btn.wait_for(state="visible", timeout=PAGE_TIMEOUT)
            make_appt_btn.click()

            # ── Step 3: Select the appointment/service type ──
            logger.debug("Waiting for appointment type selection...")
            page.wait_for_selector(
                ".QflowObjectItem", state="attached", timeout=PAGE_TIMEOUT
            )
            page.wait_for_timeout(1000)

            # Find and click the configured service type
            logger.debug("Selecting service type: %s", SERVICE_TYPE)
            service_card = page.locator(
                ".QflowObjectItem", has_text=SERVICE_TYPE
            )
            if service_card.count() == 0:
                # Take screenshot and list what's actually available
                page.screenshot(path="ncdmv_debug_screenshot.png")
                all_types = page.query_selector_all(".QflowObjectItem")
                available_types = []
                for t in all_types:
                    text = (t.inner_text() or "").strip().split("\n")[0]
                    if text:
                        available_types.append(text)
                raise RuntimeError(
                    f"Service type '{SERVICE_TYPE}' not found. "
                    f"Available types: {available_types}"
                )
            service_card.first.click()

            # ── Step 4: Wait for the location selection page ──
            logger.debug("Waiting for location selection page...")
            # The location page has a "Select a Location" heading
            page.wait_for_selector(
                "text=Select a Location", state="visible", timeout=PAGE_TIMEOUT
            )
            # Wait for all location cards to render
            page.wait_for_selector(
                ".QflowObjectItem", state="attached", timeout=PAGE_TIMEOUT
            )
            page.wait_for_timeout(2000)

            # ── Step 5: Extract location data ──
            cards = page.query_selector_all(".QflowObjectItem")
            if not cards:
                page.screenshot(path="ncdmv_debug_screenshot.png")
                raise RuntimeError(
                    "No .QflowObjectItem elements found on the location page"
                )

            logger.debug("Found %d location cards", len(cards))
            locations = []

            for card in cards:
                data_id = card.get_attribute("data-id") or ""
                classes = card.get_attribute("class") or ""

                # Extract child text elements
                # Structure: div > div (title wrapper) > div(name), div(.No-Availability),
                #            div(.form-control-child = address), div(.disabled-unitDistance)
                children = card.query_selector_all("div > div")
                name = ""
                address = ""
                distance = ""

                for child in children:
                    child_class = child.get_attribute("class") or ""
                    text = (child.inner_text() or "").strip()

                    if "No-Availability" in child_class:
                        # This div exists on all cards but may be display:none via
                        # inline style. The CSS overrides it for disabled cards.
                        # We rely on the parent card's class instead.
                        pass
                    elif "form-control-child" in child_class:
                        address = text
                    elif "Distance" in child_class:
                        # Handles both "disabled-unitDistance" and "Enabled-unit"
                        distance = text
                        if distance == "Distance":
                            distance = ""  # Placeholder text, no actual distance
                    elif not child_class and text:
                        # The name div has no CSS class
                        name = text

                # ── Availability detection ──
                # Primary signal: card-level CSS classes
                #   - "disabled-unit" → no availability
                #   - "Active-Unit"   → has availability
                has_disabled = "disabled-unit" in classes
                has_active = "Active-Unit" in classes

                # Edge case: a card might have Active-Unit but still show
                # the No-Availability message. Double-check by looking at whether
                # the No-Availability div is actually rendered visible.
                no_avail_el = card.query_selector(".No-Availability")
                no_avail_visible = False
                if no_avail_el:
                    # Check computed visibility — the inline style says display:none
                    # but CSS may override it for disabled cards.
                    no_avail_visible = no_avail_el.is_visible()

                if has_active and not no_avail_visible:
                    available = True
                elif has_active and no_avail_visible:
                    # Edge case from PRD: Active-Unit class but still showing
                    # "no availability" text — treat as unavailable
                    available = False
                    logger.debug(
                        "%s has Active-Unit but shows No-Availability text", name
                    )
                elif has_disabled:
                    available = False
                else:
                    # Fallback: no strong class signal — check text
                    available = not no_avail_visible

                locations.append({
                    "name": name,
                    "data_id": data_id,
                    "address": address,
                    "distance": distance,
                    "available": available,
                    "checked_at": now,
                })

            return locations

        except PlaywrightTimeout as e:
            try:
                page.screenshot(path="ncdmv_debug_screenshot.png")
                logger.error("Saved debug screenshot to ncdmv_debug_screenshot.png")
            except Exception:
                pass
            raise RuntimeError(f"Page load timeout: {e}") from e

        except Exception as e:
            try:
                page.screenshot(path="ncdmv_debug_screenshot.png")
                logger.error("Saved debug screenshot to ncdmv_debug_screenshot.png")
            except Exception:
                pass
            raise

        finally:
            context.close()
            browser.close()


def scrape_with_retries() -> list[dict] | None:
    """
    Attempt to scrape locations, retrying with exponential backoff on failure.

    Returns:
        List of location dicts, or None if all retries exhausted.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return scrape_locations()
        except Exception as e:
            if attempt < MAX_RETRIES:
                wait = 2 ** attempt + random.uniform(0, 1)
                logger.warning(
                    "Attempt %d/%d failed: %s — retrying in %.1fs",
                    attempt, MAX_RETRIES, e, wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "All %d attempts failed. Last error: %s", MAX_RETRIES, e,
                )
    return None


# ─── Filtering ───────────────────────────────────────────────────────────────────

def filter_locations(
    all_locations: list[dict],
    monitored_names: list[str] | None,
) -> list[dict]:
    """
    Filter locations to only those the user wants to monitor.

    If monitored_names is None, return all locations (--all mode).
    Otherwise, do case-insensitive name matching.
    """
    if monitored_names is None:
        return all_locations

    names_lower = {n.lower() for n in monitored_names}
    filtered = [loc for loc in all_locations if loc["name"].lower() in names_lower]

    # Warn about any configured names not found on the site
    found_lower = {loc["name"].lower() for loc in filtered}
    for name in monitored_names:
        if name.lower() not in found_lower:
            logger.warning(
                "Configured location '%s' was not found on the site", name,
            )

    return filtered


# ─── Dashboard ─────────────────────────────────────────────────────────────────

def load_dashboard_history() -> list[dict]:
    """Read existing history from docs/data.json so restarts don't lose it."""
    data_path = os.path.join(_script_dir, DASHBOARD_DATA_FILE)
    if os.path.isfile(data_path):
        try:
            with open(data_path, "r") as f:
                data = json.load(f)
            return data.get("history", [])
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Could not load dashboard history: %s", e)
    return []


def write_dashboard_data(
    locations: list[dict],
    events: list[dict],
    monitored_names: list[str] | None,
) -> None:
    """Write docs/data.json with current status and event history."""
    data_path = os.path.join(_script_dir, DASHBOARD_DATA_FILE)
    os.makedirs(os.path.dirname(data_path), exist_ok=True)

    # Build location entries (strip internal data_id)
    loc_entries = []
    for loc in locations:
        loc_entries.append({
            "name": loc["name"],
            "address": loc.get("address", ""),
            "distance": loc.get("distance", ""),
            "available": loc["available"],
            "checked_at": loc.get("checked_at", ""),
        })

    # Load existing history and prepend new events
    history = load_dashboard_history()
    for event in events:
        if event["type"] in ("new_opening", "slot_taken"):
            history.insert(0, {
                "type": event["type"],
                "location_name": event["location"]["name"],
                "location_address": event["location"].get("address", ""),
                "timestamp": event["timestamp"],
            })
    history = history[:DASHBOARD_HISTORY_LIMIT]

    data = {
        "last_check": datetime.now(timezone.utc).astimezone().isoformat(),
        "service_type": SERVICE_TYPE,
        "scheduler_url": SCHEDULER_URL,
        "locations": loc_entries,
        "history": history,
        "monitor_config": {
            "check_interval": CHECK_INTERVAL,
            "monitored_locations": monitored_names or ["(all)"],
        },
    }

    try:
        with open(data_path, "w") as f:
            json.dump(data, f, indent=2)
        logger.debug("Wrote dashboard data to %s", data_path)
    except OSError as e:
        logger.warning("Could not write dashboard data: %s", e)


def git_push_dashboard() -> None:
    """Stage, commit, and push docs/data.json. Fails gracefully."""
    try:
        subprocess.run(
            ["git", "add", DASHBOARD_DATA_FILE],
            cwd=_script_dir, check=True, capture_output=True,
        )
        result = subprocess.run(
            ["git", "diff", "--cached", "--quiet"],
            cwd=_script_dir, capture_output=True,
        )
        if result.returncode == 0:
            logger.debug("No dashboard changes to commit")
            return
        subprocess.run(
            ["git", "commit", "-m", "Update dashboard data"],
            cwd=_script_dir, check=True, capture_output=True,
        )
        subprocess.run(
            ["git", "push"],
            cwd=_script_dir, check=True, capture_output=True, timeout=30,
        )
        logger.info("Pushed dashboard update to remote")
    except FileNotFoundError:
        logger.warning("git not found — skipping dashboard push")
    except subprocess.CalledProcessError as e:
        logger.warning("git push failed: %s", e.stderr.decode().strip() if e.stderr else e)
    except subprocess.TimeoutExpired:
        logger.warning("git push timed out")


# ─── Output Formatting ──────────────────────────────────────────────────────────

def print_results(locations: list[dict], json_mode: bool = False) -> None:
    """Print check results to stdout."""
    if json_mode:
        print(json.dumps(locations, indent=2))
        return

    available = [loc for loc in locations if loc["available"]]
    unavailable = [loc for loc in locations if not loc["available"]]

    print()
    print(f"{'=' * 60}")
    print(f"  NC DMV Availability Check — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Service type: {SERVICE_TYPE}")
    print(f"{'=' * 60}")

    if available:
        print(f"\n  AVAILABLE ({len(available)}):")
        for loc in available:
            print(f"    [*] {loc['name']}")
            print(f"        {loc['address']}")
            if loc["distance"]:
                print(f"        {loc['distance']}")
    else:
        print("\n  No availability found at monitored locations.")

    if unavailable:
        print(f"\n  Unavailable ({len(unavailable)}):")
        for loc in unavailable:
            print(f"    [ ] {loc['name']}")

    print(f"\n{'=' * 60}")
    print()


# ─── Main Logic ─────────────────────────────────────────────────────────────────

def run_check(
    monitored_names: list[str] | None,
    json_mode: bool = False,
) -> list[dict] | None:
    """
    Run a single availability check.

    Returns:
        Filtered list of location dicts, or None on failure.
    """
    logger.info("Starting availability check...")

    all_locations = scrape_with_retries()
    if all_locations is None:
        logger.error("Check failed — could not retrieve location data")
        return None

    logger.info("Retrieved %d locations from site", len(all_locations))

    filtered = filter_locations(all_locations, monitored_names)
    available_count = sum(1 for loc in filtered if loc["available"])
    logger.info(
        "Monitoring %d locations — %d available",
        len(filtered), available_count,
    )

    print_results(filtered, json_mode=json_mode)
    return filtered


def run_loop(
    monitored_names: list[str] | None,
    interval: int,
    json_mode: bool = False,
    dashboard: bool = True,
    git_push: bool = False,
) -> None:
    """Run continuous monitoring in a loop."""
    logger.info(
        "Starting continuous monitoring (interval: %ds, ±15%% jitter)", interval,
    )

    state = load_state()
    cycle = 0

    while True:
        cycle += 1
        logger.info("─── Check cycle #%d ───", cycle)

        locations = run_check(monitored_names, json_mode=json_mode)

        if locations is not None:
            new_state, events = process_changes(locations, state)
            state = new_state
            save_state(state)

            for event in events:
                if event["type"] == "new_opening":
                    logger.info(
                        "CHANGE: %s → NOW AVAILABLE", event["location"]["name"],
                    )
                elif event["type"] == "slot_taken":
                    logger.info(
                        "CHANGE: %s → no longer available",
                        event["location"]["name"],
                    )

            if dashboard:
                write_dashboard_data(locations, events, monitored_names)
                if git_push:
                    git_push_dashboard()
        else:
            logger.warning("Check cycle #%d failed, will retry next cycle", cycle)

        # Randomize interval ±15%
        jitter = interval * 0.25
        sleep_time = interval + random.uniform(-jitter, jitter)
        sleep_time = max(60, sleep_time)  # Enforce minimum
        logger.info("Next check in %.0f seconds", sleep_time)

        try:
            time.sleep(sleep_time)
        except KeyboardInterrupt:
            logger.info("Interrupted by user — shutting down")
            break


# ─── CLI ─────────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="NC DMV Appointment Availability Monitor",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python ncdmv_monitor.py                              # Single check\n"
            "  python ncdmv_monitor.py --loop                       # Continuous\n"
            "  python ncdmv_monitor.py --loop --interval 120        # 2-min interval\n"
            "  python ncdmv_monitor.py --json                       # JSON output\n"
            "  python ncdmv_monitor.py --all                        # All locations\n"
            '  python ncdmv_monitor.py --locations "Hendersonville,Asheville"\n'
        ),
    )
    parser.add_argument(
        "--loop", action="store_true",
        help="Run continuously instead of a single check",
    )
    parser.add_argument(
        "--interval", type=int, default=CHECK_INTERVAL,
        help=f"Check interval in seconds (default: {CHECK_INTERVAL}, minimum: 60)",
    )
    parser.add_argument(
        "--json", action="store_true", dest="json_mode",
        help="Output results as JSON",
    )
    parser.add_argument(
        "--all", action="store_true",
        help="Monitor all ~100 NC DMV locations",
    )
    parser.add_argument(
        "--locations", type=str, default=None,
        help="Comma-separated list of location names to monitor (overrides config)",
    )
    parser.add_argument(
        "--service-type", type=str, default=None,
        help=f"Appointment type to check (default: '{SERVICE_TYPE}')",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="Disable writing docs/data.json for the web dashboard",
    )
    parser.add_argument(
        "--git-push", action="store_true",
        help="Auto git commit and push docs/data.json after each check",
    )
    return parser.parse_args()


def main() -> None:
    global SERVICE_TYPE

    args = parse_args()
    setup_logging(verbose=args.verbose)

    # Override service type from CLI if provided
    if args.service_type:
        SERVICE_TYPE = args.service_type

    # Determine which locations to monitor
    if args.all:
        monitored_names = None  # None = monitor everything
    elif args.locations:
        monitored_names = [s.strip() for s in args.locations.split(",") if s.strip()]
    else:
        monitored_names = MONITORED_LOCATIONS

    # Enforce minimum interval
    interval = max(60, args.interval)
    if args.interval < 60:
        logger.warning("Interval increased to 60s (minimum to be respectful)")

    # Dashboard settings
    dashboard = DASHBOARD_ENABLED and not args.no_dashboard
    git_push = GIT_AUTO_PUSH or args.git_push

    if args.loop:
        try:
            run_loop(
                monitored_names, interval,
                json_mode=args.json_mode,
                dashboard=dashboard,
                git_push=git_push,
            )
        except KeyboardInterrupt:
            logger.info("Shutting down")
    else:
        result = run_check(monitored_names, json_mode=args.json_mode)
        if result is not None and dashboard:
            # Single-check mode: still write dashboard data (no change events)
            write_dashboard_data(result, [], monitored_names)
            if git_push:
                git_push_dashboard()
        sys.exit(0 if result is not None else 1)


if __name__ == "__main__":
    main()
