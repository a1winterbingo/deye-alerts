import os
import json
import time
import hashlib
import requests

BASE_URL = "https://eu1-developer.deyecloud.com/v1.0"
STATION_ID = 62060154
STATE_FILE = "state/device_status.json"
GRID_VOLTAGE_THRESHOLD = 100

DEVICE_LABELS = {"INVERTER": "inverter", "COLLECTOR": "data logger"}

def post_with_retry(url, headers, json_body, retries=3, delay=5):
    last_error = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=json_body, timeout=15)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_error = e
            print(f"Request to {url} failed (attempt {attempt}/{retries}): {e}")
            if attempt < retries:
                time.sleep(delay)
    raise last_error

def get_token():
    password_hash = hashlib.sha256(os.environ["DEYE_PASSWORD"].encode()).hexdigest()
    resp = post_with_retry(
        f"{BASE_URL}/account/token?appId={os.environ['DEYE_APP_ID']}",
        headers={"Content-Type": "application/json"},
        json_body={
            "appSecret": os.environ["DEYE_APP_SECRET"],
            "email": os.environ["DEYE_EMAIL"],
            "companyId": "0",
            "password": password_hash,
        },
    )
    return resp.json()["accessToken"]

def get_current_status(token):
    headers = {"Content-Type": "application/json", "Authorization": f"bearer {token}"}

    devices = post_with_retry(
        f"{BASE_URL}/station/device",
        headers=headers,
        json_body={"page": 1, "size": 10, "stationIds": [STATION_ID]},
    )
    device_items = devices.json().get("deviceListItems", [])
    device_sns = [d.get("deviceSn") for d in device_items if d.get("deviceSn")]

    status = {}
    for d in device_items:
        status[d["deviceSn"]] = {
            "deviceType": d.get("deviceType"),
            "connectStatus": d.get("connectStatus"),
            "deviceState": None,
        }

    grid_voltage = None
    if device_sns:
        latest = post_with_retry(
            f"{BASE_URL}/device/latest",
            headers=headers,
            json_body={"deviceList": device_sns[:10]},
        )
        for d in latest.json().get("deviceDataList", []):
            sn = d.get("deviceSn")
            if sn in status:
                status[sn]["deviceState"] = d.get("deviceState")
            for point in d.get("dataList", []):
                if point.get("key") == "GridVoltageL1L2":
                    try:
                        grid_voltage = float(point.get("value"))
                    except (TypeError, ValueError):
                        grid_voltage = None

    return status, grid_voltage

def load_previous():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return None

def save_status(status, grid_online):
    os.makedirs("state", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump({"devices": status, "grid_online": grid_online}, f, indent=2)

def send_push(title, message):
    topic = os.environ["NTFY_TOPIC"]
    requests.post(
        f"https://ntfy.sh/{topic}",
        data=message.encode("utf-8"),
        headers={"Title": title, "Priority": "high", "Tags": "warning"},
    )

def notify_change(sn, device_type, field, old_value, new_value):
    label = DEVICE_LABELS.get(device_type, device_type)
    if field == "connectStatus":
        went_offline = old_value == 1 and new_value != 1
        went_online = new_value == 1 and old_value != 1
        if went_offline:
            send_push(f"Your {label} went offline", f"{sn} disconnected from Deye Cloud just now.")
        elif went_online:
            send_push(f"Your {label} is back online", f"{sn} reconnected to Deye Cloud.")
        else:
            send_push(f"Your {label} connection status changed", f"{sn}: code {old_value} to {new_value}.")
    else:
        send_push(
            f"Your {label} status changed",
            f"{sn} reported a status change (code {old_value} to {new_value}). Check the Deye Cloud app for details.",
        )

def main():
    token = get_token()
    current, grid_voltage = get_current_status(token)
    grid_online = grid_voltage is not None and grid_voltage >= GRID_VOLTAGE_THRESHOLD
    print(f"Current status: {current}, grid voltage: {grid_voltage}, grid_online: {grid_online}")

    previous = load_previous()
    if previous is None:
        print("First run - saving baseline, no notifications sent")
        save_status(current, grid_online)
        return

    prev_devices = previous.get("devices", {})
    for sn, fields in current.items():
        prev_fields = prev_devices.get(sn, {})
        for field in ("connectStatus", "deviceState"):
            old_value = prev_fields.get(field)
            new_value = fields.get(field)
            if old_value is not None and new_value != old_value:
                print(f"CHANGE: {sn} {field} {old_value} -> {new_value}")
                notify_change(sn, fields.get("deviceType"), field, old_value, new_value)

    prev_grid_online = previous.get("grid_online")
    if prev_grid_online is not None and grid_online != prev_grid_online:
        if not grid_online:
            send_push("Grid power lost", f"No grid voltage detected ({grid_voltage}V). You're running on battery/solar only.")
        else:
            send_push("Grid power restored", f"Grid voltage back to normal ({grid_voltage}V).")

    save_status(current, grid_online)

if __name__ == "__main__":
    main()
