import urllib.request
import json

base_url = "https://tryvtri-vton.vercel.app"

# 1. Admin Login
login_payload = json.dumps({"username": "admin", "password": "tryvtri_admin_2026!"}).encode()
req = urllib.request.Request(f"{base_url}/admin/login", data=login_payload, headers={"Content-Type": "application/json"})
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    token = data.get("access_token")
    print("Login successful! Token acquired:", bool(token))

# 2. Trigger GPU Start
req_start = urllib.request.Request(
    f"{base_url}/admin/gpu/start",
    data=b"{}",
    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"}
)
with urllib.request.urlopen(req_start) as resp:
    start_data = json.loads(resp.read().decode())
    print("GPU Start Result:", json.dumps(start_data, indent=2))

# 3. Check GPU status
req_status = urllib.request.Request(f"{base_url}/gpu/status")
with urllib.request.urlopen(req_status) as resp:
    status_data = json.loads(resp.read().decode())
    print("GPU Status:", json.dumps(status_data, indent=2))
