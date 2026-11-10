import json, base64

with open(r"C:\Users\heart\.gemini\antigravity\brain\e87bd53a-1a73-4644-93f7-40ac25c24ba8\.system_generated\steps\2501\output.txt", "r", encoding="utf-8") as f:
    text = f.read()

start_marker = "data:image/png;base64,"
idx = text.find(start_marker)
if idx != -1:
    end_idx = text.find('"', idx)
    b64_data = text[idx + len(start_marker):end_idx]
    import os
    os.makedirs(r"E:\VTON_GARMENTS\outputs", exist_ok=True)
    with open(r"E:\VTON_GARMENTS\outputs\test_vercel_tryon_output_clean.png", "wb") as out:
        out.write(base64.b64decode(b64_data))
    print("Saved to E:\\VTON_GARMENTS\\outputs\\test_vercel_tryon_output_clean.png")
else:
    print("Marker not found")
