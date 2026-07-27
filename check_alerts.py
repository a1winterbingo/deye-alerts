import os
import hashlib
import requests

BASE_URL = "https://eu1-developer.deyecloud.com/v1.0"
STATION_ID = 62060154

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

def main():
    token = get_token()
    headers = {"Content-Type": "application/json", "Authorization": f"bearer {token}"}

    devices = requests.post(
        f"{BASE_URL}/station/device",
        headers=headers,
        json={"page": 1, "size": 10, "stationIds": [STATION_ID]},
    )
    print("DEVICE LIST RESPONSE:")
    print(devices.json())

    device_data = devices.json()
    device_sns = [d.get("deviceSn") for d in device_data.get("deviceListItems", []) if d.get("deviceSn")]
    print("Found device SNs:", device_sns)

    if device_sns:
        latest = requests.post(
            f"{BASE_URL}/device/latest",
            headers=headers,
            json={"deviceList": device_sns[:10]},
        )
        print("DEVICE LATEST RESPONSE:")
        print(latest.json())

if __name__ == "__main__":
    main()
