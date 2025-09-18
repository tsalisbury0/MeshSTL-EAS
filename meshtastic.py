import requests
import subprocess
import time
from datetime import datetime, timedelta
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

# Shared event types for ALL channels
COMMON_EVENT_TYPES = [
    "Severe Thunderstorm Warning",
    "Tornado Warning",
    "Flash Flood Warning",
    "Tornado Watch",
    "Severe Thunderstorm Watch",
    "Flood Advisory",
    "Air Quality Alert",
    "Extreme Heat Watch",
    "Extreme Heat Warning"
]

# Per-channel SAME codes (fill in as needed)
CHANNEL_SAME_CODES = {
    0: {"029221", "029510", "029071", "029099", "029113", "029183", "029189", "029219", "017013", "017083", "017117", "017119", "017133", "017163"},
    1: {"029035", "029187", "029186", "029179", "029093", "029123", "029223", "029017", "029031", "029157", "017157", "017055", "017077", "017145", "017181", "017199"},
    2: {"029019", "029027", "029053", "029051", "029007", "029073", "029089", "029139", "029131", "029141", "029125", "029151", "029135", "029175"},
    3: {"029073", "029131", "029141", "029125", "029029", "029169", "029161", "029105", "029215", "029203", "029035", "029065", "029055", "029221"},
    4: {"017135", "017005", "017027", "017189", "017051", "017025", "017081", "017121", "017049", "017191"},
    5: {"029103", "029111", "029205", "029127", "029137", "029173", "029163", "017001", "017009", "017061", "017149", "017171"}
}

# All channels share the same events
CHANNEL_EVENT_TYPES = {ch: COMMON_EVENT_TYPES for ch in CHANNEL_SAME_CODES.keys()}

# Prefixes per channel
CHANNEL_PREFIXES = {
    0: "MeshSTL Alert:",
    1: "SEMO Mesh Alert:",
    2: "CMRG Mesh Alert:",
    3: "FLWMesh Alert:",
    4: "ILMesh Alert:",
    5: "NEMO Alert:"
}

# SAME code to county/state mapping (trimmed to your set, expand if needed)
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
    "029073": ("Gasconade County, MO", "MO"),
    "029139": ("Montgomery County, MO", "MO"),
    "029161": ("Phelps County, MO", "MO"),
    "029169": ("Pulaski County, MO", "MO"),
    "029065": ("Dent County, MO", "MO"),
    "029125": ("Maries County, MO", "MO"),
    "017117": ("Macoupin County, IL", "IL"),
    "017135": ("Montgomery County, IL", "IL"),
    "029175": ("Randolph County, MO", "MO"),
    "029135": ("Moniteau County, MO", "MO"),
    "029151": ("Osage County, MO", "MO"),
    "029141": ("Morgan County, MO", "MO"),
    "029131": ("Miller County, MO", "MO"),
    "029089": ("Howard County, MO", "MO"),
    "029007": ("Audrain County, MO", "MO"),
    "029051": ("Cole County, MO", "MO"),
    "029053": ("Cooper County, MO", "MO"),
    "029027": ("Callaway County, MO", "MO")'
    "029019": ("Boone County, MO", "MO"),
    "029035": ("Carter County, MO", "MO"),
    "029029": ("Camden County, MO", "MO"),
    "029105": ("Laclede County, MO", "MO"),
    "029215": ("Texas County, MO", "MO"),
    "029203": ("Shannon County, MO", "MO"),
    "029179": ("Reynolds County, MO", "MO"),
    "029157": ("Perry County, MO", "MO"),
    "029031": ("Cape Girardeau County, MO", "MO"),
    "029017": ("Bollinger County, MO", "MO"),
    "029223": ("Wayne County, MO", "MO"),
    "029123": ("Madison County, MO", "MO"),
    "029093": ("Iron County, MO", "MO"),
    "029103": ("Knox County, MO", "MO"),
    "029111": ("Lewis County, MO", "MO"),
    "029205": ("Shelby County, MO", "MO"),
    "029127": ("Marion County, MO", "MO"),
    "029137": ("Monroe County, MO", "MO"),
    "029173": ("Ralls County, MO", "MO"),
    "029163": ("Pike County, MO", "MO"),
    "017001": ("Adams County, IL", "IL"),
    "017009": ("Brown County, IL", "IL"),
    "017061": ("Greene County, IL", "IL"),
    "017149": ("Pike County, IL", "IL"),
    "017171": ("Scott County, IL", "IL"),
    "017191": ("Wayne County, IL", "IL"),
    "017049": ("Effingham County, IL", "IL"),
    "017121": ("Marion County, IL", "IL"),
    "017081": ("Jefferson County, IL", "IL"),
    "017025": ("Clay County, IL", "IL"),
    "017051": ("Fayette County, IL", "IL"),
    "017055": ("Franklin County, IL", "IL"),
    "017077": ("Jackson County, IL", "IL"),
    "017145": ("Perry County, IL", "IL"),
    "017181": ("Union County, IL", "IL"),
    "017199": ("Williamson County, IL", "IL")
}

SENT_ALERTS_FILE = "/home/tsalisbury0/meshtastic_test/sent_alerts.pkl"
LOCK_FILE = "/tmp/meshtastic_send.lock"
MAX_LOCK_AGE = 300
CHECK_INTERVAL = int(os.getenv("CAP_CHECK_INTERVAL", 60))
ALERT_EXPIRY_HOURS = 24  # prune sent alerts older than this many hours
DRY_RUN = "--dry-run" in sys.argv

# Load sent alert IDs
def load_sent_alerts():
    if os.path.exists(SENT_ALERTS_FILE):
        with open(SENT_ALERTS_FILE, "rb") as f:
            data = pickle.load(f)
            if isinstance(data, dict):
                return data
            else:
                return {}
    return {}

# Save sent alert IDs
def save_sent_alerts(sent_alerts):
    with open(SENT_ALERTS_FILE, "wb") as f:
        pickle.dump(sent_alerts, f)

sent_alerts = load_sent_alerts()

# Graceful exit
def signal_handler(sig, frame):
    log.info("\nExiting... Saving sent alerts.")
    save_sent_alerts(sent_alerts)
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Locking
def acquire_lock():
    while os.path.exists(LOCK_FILE):
        lock_age = time.time() - os.path.getmtime(LOCK_FILE)
        if lock_age > MAX_LOCK_AGE:
            log.warning("Stale lock detected. Removing it.")
            os.remove(LOCK_FILE)
            break
        else:
            log.info("Another process is using the Meshtastic node. Waiting...")
            time.sleep(2)
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
                        "same_codes": set(alert.get("geocode", {}).get("SAME", [])),
                        "fetched": time.time()  # track when we saw this alert
                    })
        return alerts
    except Exception as e:
        log.error(f"Error fetching CAP-EAS alerts: {e}")
        return []

# Prune old alerts from memory
def prune_sent_alerts():
    cutoff = time.time() - (ALERT_EXPIRY_HOURS * 3600)
    before = len(sent_alerts)
    to_delete = [aid for aid, entry in sent_alerts.items() if entry.get("timestamp", 0) < cutoff]
    for aid in to_delete:
        del sent_alerts[aid]
    if to_delete:
        log.info(f"Pruned {len(to_delete)} old sent alerts (kept {before - len(to_delete)})")

# Filter alerts
def filter_alerts_for_channel(alerts, channel_index):
    messages = []
    allowed_same_codes = CHANNEL_SAME_CODES[channel_index]
    allowed_events = CHANNEL_EVENT_TYPES[channel_index]

    for alert in alerts:
        if alert["title"] not in allowed_events:
            continue

        sent_entry = sent_alerts.setdefault(alert["id"], {"channels": set(), "timestamp": time.time()})
        if channel_index in sent_entry["channels"]:
            continue

        matching_codes = alert["same_codes"] & allowed_same_codes
        if not matching_codes:
            continue

        try:
            expires_dt = isoparse(alert["expires"])
            expires_str = expires_dt.strftime("%b %d, %I:%M %p")
        except Exception:
            expires_str = "Unknown Time"

        prefix = CHANNEL_PREFIXES.get(channel_index, "Alert:")

        for code in matching_codes:
            if code in SAME_CODE_MAP:
                county, state = SAME_CODE_MAP[code]
                message = f"{prefix}\n⚠️ {alert['title']} for {county} until {expires_str}"
                messages.append(message[:200])

        sent_entry["channels"].add(channel_index)
        sent_entry["timestamp"] = time.time()

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

        prune_sent_alerts()
        save_sent_alerts(sent_alerts)

        log.info(f"Check complete — sleeping for {CHECK_INTERVAL} seconds.\n")
        time.sleep(CHECK_INTERVAL)
