import os
import json
import hashlib
import requests
from datetime import datetime, timedelta, timezone

BASE_URL = "https://eu1-developer.deyecloud.com/v1.0"
STATION_ID = 62060154
STATE_FILE = "state/seen_alerts.json"

def get_token():
    password_hash = hashlib.sha256(os.environ["DEYE_PASSWORD"].encode()).hexdigest()
    resp = requests.post(
        f"{BASE_URL}/account/token?appId={os.environ['DEYE_APP_ID']}",
        headers={"Content-Type": "application/json"},
        json={
            "appSecret": os.environ["DEYE_APP_SECRET"],
            "email": os.environ["DEYE_EMAIL"],
            "companyId": "0",
            "password": password_hash,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if "accessToken" not in data:
        print("Token response:", data)
        raise SystemExit("No accessToken - check response above")
    return data["accessToken"]

def get_alerts(token):
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=7)
    resp = requests.post(
        f"{BASE_URL}/station/alert",
        headers={"Content-Type": "application/json", "Authorization": f"bearer {token}"},
        json={
            "stationId": STATION_ID,
            "startTime": start.strftime("%Y-%m-%d"),
            "endTime": now.strftime("%Y-%m-%d"),
            "page": 1,
            "size": 100,
        },
    )
    resp.raise_for_status()
    data = resp.json()
    if "stationAlertItems" not in data:
        print("Alert response:", data)
        raise SystemExit("No stationAlertItems - check response above, endpoint/fields may need adjusting")
    return data["stationAlertItems"]

def alert_key(item):
    raw = f"{item.get('deviceSn')}|{item.get('code')}|{item.get('alertTime')}"
    return hashlib.sha1(raw.encode()).hexdigest()

def load_seen():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return set(json.load(f))
    return None

def save_seen(keys):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(keys), f)

def send_push(item):
    topic = os.environ["NTFY_TOPIC"]
    title = f"Deye Alert: {item.get('showName', 'Unknown')}"
    message = f"Device {item.get('deviceSn')} - Level {item.get('level')} - {item.get('alertTime')}"
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "warning"},
    )

def main():
    token = get_token()
    alerts = get_alerts(token)
    print(f"Fetched {len(alerts)} alert(s) from the last 7 days")

    seen = load_seen()
    current_keys = {alert_key(a) for a in alerts}

    if seen is None:
        print("First run - recording current alerts as baseline, no notifications sent")
        save_seen(current_keys)
        return

    new_keys = current_keys - seen
    if new_keys:
        print(f"{len(new_keys)} new alert(s) found - sending notifications")
        for a in alerts:
            if alert_key(a) in new_keys:
                send_push(a)
    else:
        print("No new alerts")

    save_seen(current_keys | seen)

if __name__ == "__main__":
    main()
