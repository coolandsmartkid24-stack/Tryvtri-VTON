import urllib.request
import urllib.parse
import uuid
import json

boundary = "----WebKitFormBoundary" + uuid.uuid4().hex

person_path = r"E:\VTON_GARMENTS\IDM-VTON-LOCAL\inputs\person\model.jpg"
with open(person_path, "rb") as f:
    person_bytes = f.read()

# Build multipart body
body = bytearray()

def add_field(name, value):
    global body
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
    body.extend(f"{value}\r\n".encode())

def add_file(name, filename, data, content_type="image/jpeg"):
    global body
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'.encode())
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode())
    body.extend(data)
    body.extend(b"\r\n")

add_file("person_image", "model.jpg", person_bytes)
add_field("garment_url", "https://images.unsplash.com/photo-1521572267360-ee0c2909d518?w=800")
add_field("category", "tops")
add_field("email", "test_customer@tryvtri.com")
add_field("shop", "tryvtri-store.myshopify.com")
add_field("product_id", "prod_123")
add_field("product_title", "Classic T-Shirt")

body.extend(f"--{boundary}--\r\n".encode())

url = "https://tryvtri-vton.vercel.app/try-on-vton"
req = urllib.request.Request(
    url,
    data=bytes(body),
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "User-Agent": "TryVtri-Test-Client/1.0"
    }
)

print("Sending virtual try-on request to Vercel production API...")
try:
    with urllib.request.urlopen(req, timeout=120) as resp:
        res_data = json.loads(resp.read().decode())
        print("Success! Status:", resp.status)
        print("Response:", json.dumps(res_data, indent=2))
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode()}")
except Exception as e:
    print(f"Error: {e}")
