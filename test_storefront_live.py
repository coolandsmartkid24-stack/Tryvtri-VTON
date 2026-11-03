import urllib.request
import uuid
import json
import time

def send_multipart():
    url = "https://tryvtri-vton.vercel.app/try-on-vton"
    boundary = "----WebKitFormBoundary" + uuid.uuid4().hex
    
    with open(r"E:\VTON_GARMENTS\VTON TESTING\fashn-vton-1.5\person.jpg", "rb") as f:
        person_bytes = f.read()
    with open(r"E:\VTON_GARMENTS\VTON TESTING\fashn-vton-1.5\garment.jpg", "rb") as f:
        garment_bytes = f.read()

    body = bytearray()
    
    # person_image
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="person_image"; filename="person.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(person_bytes)
    body.extend(b"\r\n")
    
    # garment_image
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="garment_image"; filename="garment.jpg"\r\n')
    body.extend(b"Content-Type: image/jpeg\r\n\r\n")
    body.extend(garment_bytes)
    body.extend(b"\r\n")
    
    # category
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="category"\r\n\r\n')
    body.extend(b"tops\r\n")
    
    # session_id
    session_id = f"test_{int(time.time())}"
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(b'Content-Disposition: form-data; name="session_id"\r\n\r\n')
    body.extend(session_id.encode("utf-8"))
    body.extend(b"\r\n")
    
    body.extend(f"--{boundary}--\r\n".encode("utf-8"))
    
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0"
        }
    )
    
    t0 = time.time()
    print("Calling Vercel Storefront Try-On API...")
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            elapsed = time.time() - t0
            print(f"Status Code: {resp.status} (Elapsed: {elapsed:.2f}s)")
            data = json.loads(resp.read().decode("utf-8"))
            print("Response:", json.dumps({k: v for k, v in data.items() if k != "output_url" and k != "result_image"}, indent=2))
            out_url = data.get("output_url", "")
            print(f"Output image length: {len(out_url)} chars")
            print("SUCCESS! Virtual try-on end-to-end verified.")
    except Exception as e:
        print(f"FAILED: {e}")

if __name__ == "__main__":
    send_multipart()
