"""End-to-end test: download fresh JPEG, POST multipart to production webhook, print response."""
import json
import time
import urllib.request
import urllib.error
import uuid

from n8n_common import BASE_URL

with open("webhook_token.txt", "r", encoding="utf-8") as f:
    TOKEN = f.read().strip()

# fresh test image
url = "https://picsum.photos/id/237/200/140"
req = urllib.request.Request(url, headers={"User-Agent": "kb-e2e-test/1.0"})
with urllib.request.urlopen(req, timeout=30) as r:
    img = r.read()
print("downloaded test image bytes:", len(img), img[:4])

ocr_text = ("Facture Orange Mobile - Montant 19,99 EUR - Echeance 2026-10-05 - "
            "Test e2e kb-capture after workflow fix")
boundary = "----kbe2e" + uuid.uuid4().hex[:12]
parts = []
parts.append(
    f'--{boundary}\r\nContent-Disposition: form-data; name="text"\r\n\r\n{ocr_text}\r\n'.encode()
)
parts.append(
    f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="kb-e2e-test.jpg"\r\n'
    f'Content-Type: image/jpeg\r\n\r\n'.encode() + img + b"\r\n"
)
parts.append(f"--{boundary}--\r\n".encode())
body = b"".join(parts)

req = urllib.request.Request(
    BASE_URL + "/webhook/kb-capture", data=body, method="POST",
    headers={
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "X-KB-capture-token": TOKEN,
        "User-Agent": "kb-e2e-test/1.0",
    },
)
t0 = time.time()
try:
    with urllib.request.urlopen(req, timeout=120) as r:
        status = r.status
        raw = r.read().decode("utf-8", "replace")
except urllib.error.HTTPError as e:
    status = e.code
    raw = e.read().decode("utf-8", "replace")
elapsed = time.time() - t0
print(f"webhook -> HTTP {status} in {elapsed:.1f}s")
try:
    resp = json.loads(raw)
    print("response JSON keys:", sorted(resp.keys()))
    for k, v in resp.items():
        if isinstance(v, str) and len(v) > 160:
            print(f"  {k}: {v[:160]!r}... (len={len(v)})")
        else:
            print(f"  {k}: {json.dumps(v, ensure_ascii=False)[:160]}")
except Exception:
    print("raw response:", raw[:800])
