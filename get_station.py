import os
import hashlib
import requests

BASE_URL = "https://eu1-developer.deyecloud.com/v1.0"

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
        raise SystemExit("No accessToken in response - check the fields above for errors")
    return data["accessToken"]

def main():
    token = get_token()
    resp = requests.post(
        f"{BASE_URL}/station/list",
        headers={"Content-Type": "application/json", "Authorization": f"bearer {token}"},
        json={"page": 1, "size": 20},
    )
    resp.raise_for_status()
    data = resp.json()
    print("Full response:", data)
    for station in data.get("stationList", []):
        print(f"Station ID: {station.get('id')}  Name: {station.get('name')}")

if __name__ == "__main__":
    main()

if __name__ == "__main__":
    main()
