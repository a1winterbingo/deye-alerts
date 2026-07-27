import os
import json
import hashlib
import requests

BASE_URL = "https://eu1-developer.deyecloud.com/v1.0"
STATION_ID = 62060154
STATE_FILE = "state/device_status.json"

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
    return resp.json()["accessToken"]

def get_current_status(token):
    headers = {"Content-Type": "application/json", "Authorization": f"bearer {token}"}

    devices = requests.post(
        f"{BASE_URL}/station/device",
        headers=headers,
        json={"page": 1, "size": 10, "stationIds": [STATION_ID]},
    )
    devices.raise_for_status()
    device_items = devices.json().get("deviceListItems", [])
    device_sns = [d.get("deviceSn") for d in device_items if d.get("deviceSn")]

    status = {}
    for d in device_items:
        status[d["deviceSn"]] = {
            "deviceType": d.get("deviceType"),
            "connectStatus": d.get("connectStatus"),
            "deviceState": None,
        }

    if device_sns:
        latest = requests.post(
            f"{BASE_URL}/device/latest",
            headers=headers,
            json={"deviceList": device_sns[:10]},
        )
        latest.raise_for_status()
        for d in latest.json().get("deviceDataList", []):
            sn = d.get("deviceSn")
            if sn in status:
                status[sn]["deviceState"] = d.get("deviceState")

    return status

def load_previous():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

def save_status(status):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(status, f, indent=2)

def send_push(sn, device_type, field, old_value, new_value):
    topic = os.environ["NTFY_TOPIC"]
    title = f"Deye status change: {device_type} {sn}"
    message = f"{field} changed from {old_value} to {new_value}"
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "warning"},
    )

def main():
    token = get_token()
    current = get_current_status(token)
    print("Current status:", current)

    previous = load_previous()
    if previous is None:
        print("First run - saving baseline, no notifications sent")
        save_status(current)
        return

    for sn, fields in current.items():
        prev_fields = previous.get(sn, {})
        for field in ("connectStatus", "deviceState"):
            old_value = prev_fields.get(field)
            new_value = fields.get(field)
            if old_value is not None and new_value != old_value:
                print(f"CHANGE: {sn} {field} {old_value} -> {new_value}")
                send_push(sn, fields.get("deviceType", "device"), field, old_value, new_value)

    save_status(current)

if __name__ == "__main__":
    main()
