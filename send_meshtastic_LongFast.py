import requests
import subprocess
import time
from datetime import datetime
import os
import pickle
import signal
import sys

# CAP-EAS API URLs for US States "ST"
CAP_API_URLS = {
    "MO": "https://api.weather.gov/alerts/active?area=MO"
}

# Mapping of SAME codes to counties and states (add more mappings as needed)
SAME_CODE_MAP = {
    "029071": ("Franklin County", "MO"),
    "029099": ("Jefferson County", "MO"),
    "029221": ("Washington County", "MO"),
    "029187": ("St. Francois County", "MO")
}

# List of SAME codes to filter alerts
SAME_CODES = set(SAME_CODE_MAP.keys())

# Path to the file where sent alert IDs will be stored
SENT_ALERTS_FILE = "/home/tsalisbury0/meshtastic_test/sent_alerts_local.pkl"  # Updated path

# Load previously sent alert IDs from file
def load_sent_alerts():
    if os.path.exists(SENT_ALERTS_FILE):
        with open(SENT_ALERTS_FILE, "rb") as f:
            return pickle.load(f)
    return set()

# Save sent alert IDs to file
def save_sent_alerts(sent_alerts):
    with open(SENT_ALERTS_FILE, "wb") as f:
        pickle.dump(sent_alerts, f)

# Store sent alerts to prevent duplicate messages
sent_alerts = load_sent_alerts()

# Signal handler to clear sent alerts on exit
def signal_handler(sig, frame):
    print("\nExiting... Clearing sent alerts.")
    # Clear sent alerts
    sent_alerts.clear()
    save_sent_alerts(sent_alerts)  # Save empty set to file to clear it
    sys.exit(0)

# Register signal handler for graceful exit
signal.signal(signal.SIGINT, signal_handler)

# Function to fetch and parse CAP-EAS data
def fetch_cap_alert():
    try:
        messages = []
        severe_weather_events = [
            "Severe Thunderstorm Warning",
            "Tornado Warning",
            "Flash Flood Warning",
            "Tornado Watch",
            "Severe Thunderstorm Watch",
            "Flood Warning",
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
            "Special Weather Statement"
        ]
        
        for state, url in CAP_API_URLS.items():
            response = requests.get(url, headers={"User-Agent": "MeshtasticCAPFetcher"})
            response.raise_for_status()
            data = response.json()

            if "features" in data and len(data["features"]) > 0:
                for feature in data["features"]:
                    alert = feature["properties"]
                    title = alert.get("event", "No Title")
                    expires = alert.get("expires", "Unknown Time")
                    certainty = alert.get("certainty", "Unknown Certainty")
                    same_codes = set(alert.get("geocode", {}).get("SAME", []))
                    alert_id = alert.get("id", "")

                    # Filter for severe weather events
                    if title in severe_weather_events:
                        # Check if the SAME code matches the desired codes and if it's not already sent
                        if not SAME_CODES.isdisjoint(same_codes) and alert_id not in sent_alerts:
                            try:
                                expires_dt = datetime.fromisoformat(expires[:-6])  # Remove timezone offset for parsing
                                expires_str = expires_dt.strftime("%b %d, %I:%M %p")
                            except ValueError:
                                expires_str = "Unknown Time"

                            # Get the county and state from SAME_CODE_MAP
                            for code in same_codes:
                                if code in SAME_CODE_MAP:
                                    county, state = SAME_CODE_MAP[code]
                                    if county == "St. Louis City":
                                        county = "St. Louis City, MO"  # Correct formatting for St. Louis City
                                    message = f"⚠️ {title} for {county} until {expires_str}"
                                    messages.append(message[:200])  # Ensure message length limit
                                    sent_alerts.add(alert_id)  # Mark alert as sent
        save_sent_alerts(sent_alerts)  # Save sent alerts to file
        return messages
    except Exception as e:
        print(f"Error fetching CAP-EAS: {e}")
        return []

# Function to send message via Meshtastic CLI
def send_meshtastic_message(messages):
    for message in messages:
        try:
            subprocess.run(["meshtastic", "--sendtext", message, "--ch-index", "0", "--dest", "^all"], check=True)
            print(f"Message sent successfully: {message}")
        except subprocess.CalledProcessError as e:
            print(f"Error sending message: {e}")

# Main script execution with loop
if __name__ == "__main__":
    while True:
        alert_messages = fetch_cap_alert()
        if alert_messages:
            send_meshtastic_message(alert_messages)
        else:
            print("No new alerts found.")
        time.sleep(60)  # Wait 60 seconds before checking again

