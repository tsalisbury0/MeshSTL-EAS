import requests
import subprocess
import time
from datetime import datetime
import os
import pickle
import signal
import sys
import logging
from dateutil.parser import isoparse

# Setup logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# CAP-EAS API URLs for Missouri (MO) and Illinois (IL)
CAP_API_URLS = {
    "MO": "https://api.weather.gov/alerts/active?area=MO",
    "IL": "https://api.weather.gov/alerts/active?area=IL"
}

# Per-channel SAME codes
CHANNEL_SAME_CODES = {
    0: {"017005", "017027", "017013", "017083", "017119", "017133", "017157", "017163", "017189", "029510", "029055", "029071", "029073", "029099", "029113", "029183", "029186", "029187", "029189", "029219", "029221"},
    1: {"029099"}
}

# Per-channel event types
CHANNEL_EVENT_TYPES = {
    0: [
        "Severe Thunderstorm Warning",
        "Tornado Warning",
        "Flash Flood Warning",
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Flood Advisory",
        "Air Quality Alert",
        "Extreme Heat Watch",
        "Extreme Heat Warning"
    ],
    1: [
        "Severe Thunderstorm Warning",
        "Tornado Warning",
        "Flash Flood Warning",
        "Tornado Watch",
        "Severe Thunderstorm Watch",
        "Fire Warning",
        "Earthquake Warning",
        "Shelter in Place Warning",
        "Snow Squall Warning",
        "911 Telephone Outage Emergency",
        "Child Abduction Emergency",
        "Civil Danger Warning",
        "Dust Storm Warning",
        "Evacuation Immediate",
        "Extreme Wind Warning",
        "Law Enforcement Warning",
        "Ice Storm Warning",
        "Civil Emergency Message",
        "Blizzard Warning",
        "Winter Storm Warning",
        "High Wind Warning",
        "Blowing Dust Warning",
        "Flood Advisory",
        "Winter Weather Advisory",
        "Winter Storm Watch",
        "Blowing Dust Advisory",
        "Dust Advisory",
        "Freeze Warning",
        "Freeze Watch",
        "Extreme Cold Watch",
        "Extreme Cold Warning",
        "Cold Weather Advisory",
        "Fire Weather Watch",
        "Excessive Heat Warning",
        "Excessive Heat Watch",
        "Frost Advisory",
        "Heat Advisory",
        "Air Quality Alert",
        "Air Stagnation Advisory",
        "Dense Fog Advisory",
        "Freezing Fog Advisory",
        "Dense Smoke Advisory",
        "High Wind Watch",
        "Special Weather Statement",
        "Extreme Heat Watch",
        "Extreme Heat Warning"
    ]
}

# SAME code to county/state mapping
SAME_CODE_MAP = {
    "029071": ("Franklin County, MO", "MO"),
    "029099": ("Jefferson County, MO", "MO"),
    "029189": ("St. Louis County, MO", "MO"),
    "029510": ("St. Louis City, MO", "MO"),
    "017013": ("Calhoun County, IL", "IL"),
    "017083": ("Jersey County, IL", "IL"),
    "017119": ("Madison County, IL", "IL"),
    "017133": ("Monroe County, IL", "IL"),
    "017163": ("St. Clair County, IL", "IL"),
    "029183": ("St. Charles County, MO", "MO"),
    "029221": ("Washington County, MO", "MO"),
    "029187": ("St. Francois County, MO", "MO"),
    "029186": ("Ste. Genevieve County, MO", "MO"),
    "029113": ("Lincoln County, MO", "MO"),
    "029219": ("Warren County, MO", "MO"),
    "017005": ("Bond County, IL", "IL"),
    "017027": ("Clinton County, IL", "IL"),
    "017157": ("Randolph County, IL", "IL"),
    "017189": ("Washington County, IL", "IL"),
    "029055": ("Crawford County, MO", "MO"),
    "029073": ("Gasconade County, MO", "MO")
}

SENT_ALERTS_FILE = "/home/tsalisbury0/meshtastic_test/sent_alerts.pkl"
LOCK_FILE = "/tmp/meshtastic_send.lock"
MAX_LOCK_AGE = 300
CHECK_INTERVAL = int(os.getenv("CAP_CHECK_INTERVAL", 60))
DRY_RUN = "--dry-run" in sys.argv

# Load sent alert IDs

def load_sent_alerts():
    if os.path.exists(SENT_ALERTS_FILE):
        with open(SENT_ALERTS_FILE, "rb") as f:
            data = pickle.load(f)
            if isinstance(data, dict):
                return data
            else:
                return {}  # migration from old set format
    return {}

# Save sent alert IDs

def save_sent_alerts(sent_alerts):
    with open(SENT_ALERTS_FILE, "wb") as f:
        pickle.dump(sent_alerts, f)

sent_alerts = load_sent_alerts()

# Graceful exit

def signal_handler(sig, frame):
    log.info("\nExiting... Clearing sent alerts.")
    sent_alerts.clear()
    save_sent_alerts(sent_alerts)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Locking

def acquire_lock():
    if os.path.exists(LOCK_FILE):
        lock_age = time.time() - os.path.getmtime(LOCK_FILE)
        if lock_age > MAX_LOCK_AGE:
            log.warning("Stale lock detected. Removing it.")
            os.remove(LOCK_FILE)
        else:
            log.info("Another process is using the Meshtastic node. Waiting...")
            time.sleep(2)
            return acquire_lock()
    with open(LOCK_FILE, "w") as f:
        f.write(str(os.getpid()))

def release_lock():
    if os.path.exists(LOCK_FILE):
        os.remove(LOCK_FILE)

# Fetch CAP alerts

def fetch_cap_alerts():
    try:
        alerts = []
        for state, url in CAP_API_URLS.items():
            response = requests.get(url, headers={"User-Agent": "MeshtasticCAPFetcher"})
            response.raise_for_status()
            data = response.json()
            if "features" in data and data["features"]:
                for feature in data["features"]:
                    alert = feature["properties"]
                    alerts.append({
                        "id": alert.get("id", ""),
                        "title": alert.get("event", "No Title"),
                        "expires": alert.get("expires", "Unknown Time"),
                        "same_codes": set(alert.get("geocode", {}).get("SAME", []))
                    })
        return alerts
    except Exception as e:
        log.error(f"Error fetching CAP-EAS alerts: {e}")
        return []

# Filter alerts

def filter_alerts_for_channel(alerts, channel_index):
    messages = []
    allowed_same_codes = CHANNEL_SAME_CODES[channel_index]
    allowed_events = CHANNEL_EVENT_TYPES[channel_index]

    for alert in alerts:
        log.debug(f"[Channel {channel_index}] Evaluating alert: {alert['title']} - SAME: {alert['same_codes']}")

        if alert["title"] not in allowed_events:
            log.debug(f"[Channel {channel_index}] Skipped (title '{alert['title']}' not in allowed events)")
            continue

        if channel_index in sent_alerts.get(alert["id"], set()):
            log.debug(f"[Channel {channel_index}] Skipped (already sent)")
            continue

        matching_codes = alert["same_codes"] & allowed_same_codes
        if not matching_codes:
            log.debug(f"[Channel {channel_index}] Skipped (no SAME code match)")
            continue

        try:
            expires_dt = isoparse(alert["expires"])
            expires_str = expires_dt.strftime("%b %d, %I:%M %p")
        except Exception:
            expires_str = "Unknown Time"

        for code in matching_codes:
            if code in SAME_CODE_MAP:
                county, state = SAME_CODE_MAP[code]
                prefix = "MeshSTL Alert:" if channel_index == 0 else "Local Alert:"
                message = f"{prefix}\n⚠️ {alert['title']} for {county} until {expires_str}"
                messages.append(message[:200])

        sent_alerts.setdefault(alert["id"], set()).add(channel_index)

    return messages

# Send message

def send_meshtastic_message(messages, channel_index):
    if not messages:
        return
    acquire_lock()
    try:
        for idx, message in enumerate(messages):
            if DRY_RUN:
                log.info(f"[Dry Run] Would send on channel {channel_index}: {message}")
            else:
                subprocess.run([
                    "meshtastic", "--sendtext", message,
                    "--ch-index", str(channel_index),
                    "--dest", "^all"
                ], check=True)
                log.info(f"Sent on channel {channel_index}: {message}")

            if idx < len(messages) - 1:
                time.sleep(5)
        time.sleep(5)
    except subprocess.CalledProcessError as e:
        log.error(f"Error sending message: {e}")
    finally:
        release_lock()

# Main loop

if __name__ == "__main__":
    while True:
        all_alerts = fetch_cap_alerts()

        for channel_index in CHANNEL_SAME_CODES.keys():
            messages = filter_alerts_for_channel(all_alerts, channel_index)
            send_meshtastic_message(messages, channel_index)

        save_sent_alerts(sent_alerts)
        log.info(f"Check complete — sleeping for {CHECK_INTERVAL} seconds.\n")
        time.sleep(CHECK_INTERVAL)

