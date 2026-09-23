from fastapi.testclient import TestClient
from backend.main import app
import json

client = TestClient(app)

def test_api():
    print("Testing /auth/register...")
    res = client.post("/api/v1/auth/register", json={
        "email": "testclient@example.com",
        "password": "password123",
        "full_name": "Test Client"
    })
    print("Register Status:", res.status_code)
    
    print("Testing /auth/login...")
    res = client.post("/api/v1/auth/login", json={
        "email": "testclient@example.com",
        "password": "password123"
    })
    print("Login Status:", res.status_code)
    if res.status_code == 200:
        token = res.json().get("access_token")
        print("Testing /auth/me...")
        res = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        print("Me Status:", res.status_code)
        if res.status_code >= 400:
            print(res.text)

if __name__ == "__main__":
    test_api()
