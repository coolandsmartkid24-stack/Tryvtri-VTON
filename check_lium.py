import requests

api_key = "sk_r93i642i3EO20DaLiUPgB2Zt2LhmAapg9aF0-cKDKK4"
url = "https://lium.io/api/pods"
headers = {
    "X-API-Key": api_key,
    "Authorization": f"Bearer {api_key}"
}

try:
    r = requests.get(url, headers=headers, timeout=10)
    print("Status:", r.status_code)
    print("Response:", r.text)
except Exception as e:
    print("Error:", e)
