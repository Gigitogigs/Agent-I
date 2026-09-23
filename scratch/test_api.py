import urllib.request
import json
import urllib.error

BASE_URL = "http://127.0.0.1:8000/api/v1"

def test_register():
    print("Testing /auth/register...")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/register",
        data=json.dumps({
            "email": "testagent@example.com",
            "password": "password123",
            "full_name": "Agent Tester"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            print("Status:", response.status)
            print("Response:", response.read().decode())
    except urllib.error.HTTPError as e:
        print("Status:", e.code)
        print("Response:", e.read().decode())
    except Exception as e:
        print("Error:", e)

def test_login():
    print("\nTesting /auth/login...")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/login",
        data=json.dumps({
            "email": "testagent@example.com",
            "password": "password123"
        }).encode("utf-8"),
        headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req) as response:
            print("Status:", response.status)
            body = response.read().decode()
            print("Response:", body)
            data = json.loads(body)
            return data.get("access_token")
    except urllib.error.HTTPError as e:
        print("Status:", e.code)
        print("Response:", e.read().decode())
        return None
    except Exception as e:
        print("Error:", e)
        return None

def test_me(token):
    print("\nTesting /auth/me...")
    req = urllib.request.Request(
        f"{BASE_URL}/auth/me",
        headers={
            "Authorization": f"Bearer {token}"
        }
    )
    try:
        with urllib.request.urlopen(req) as response:
            print("Status:", response.status)
            print("Response:", response.read().decode())
    except urllib.error.HTTPError as e:
        print("Status:", e.code)
        print("Response:", e.read().decode())
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_register()
    token = test_login()
    if token:
        test_me(token)
