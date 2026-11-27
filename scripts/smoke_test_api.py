"""End-to-end smoke test for the API against the local Docker stack.

Runs the client flow: create batch -> upload to presigned URLs -> confirm -> poll status.
Uses only the standard library. Usage:

    docker compose up -d --wait postgres redis localstack api
    python3 scripts/smoke_test_api.py
"""
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API = os.environ.get("API_URL", "http://localhost:8000")
# 1x1 transparent PNG
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def call(method, url, body=None, headers=None, raw=None):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    req = urllib.request.Request(url, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req) as r:
            payload = r.read()
            return r.status, (json.loads(payload) if payload and raw is None else payload)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"null")


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


# Validation
code, _ = call("POST", f"{API}/batches", {"files": [{"filename": "a.gif", "content_type": "image/gif"}]})
check(code == 422, "unsupported content type rejected")
code, _ = call("POST", f"{API}/batches", {"files": []})
check(code == 422, "empty batch rejected")

# Create a batch of 3, upload only 2
files = [{"filename": f"img{i}.png", "content_type": "image/png"} for i in range(3)]
code, batch = call("POST", f"{API}/batches", {"files": files, "params": {"max_width": 512, "max_height": 512}})
check(code == 201 and len(batch["uploads"]) == 3, "batch created with 3 presigned upload URLs")
bid = batch["batch_id"]

code, st = call("GET", f"{API}/batches/{bid}")
check(code == 200 and st["status"] == "awaiting_upload", "status is awaiting_upload before confirm")

code, _ = call("POST", f"{API}/batches/00000000-0000-0000-0000-000000000000/confirm")
check(code == 404, "confirm on unknown batch returns 404")

for u in batch["uploads"][:2]:
    code, _ = call("PUT", u["upload_url"], raw=PNG, headers={"Content-Type": u["content_type"]})
    check(code == 200, f"direct S3 upload of {u['filename']}")

code, st = call("POST", f"{API}/batches/{bid}/confirm")
check(code == 200 and st["counts"] == {"queued": 2, "upload_missing": 1}, f"confirm queued 2, flagged 1 missing: {st['counts']}")
check(st["status"] == "processing", "batch status is processing")

code, st2 = call("POST", f"{API}/batches/{bid}/confirm")
check(code == 200 and st2["counts"] == st["counts"], "second confirm is a no-op")

code, res = call("GET", f"{API}/batches/{bid}/results")
check(code == 200 and res["results"] == [], "no results before processing")

job_id = batch["uploads"][0]["job_id"]
code, _ = call("GET", f"{API}/jobs/{job_id}/result")
check(code == 409, "job result returns 409 while not done")

print(f"\nbatch {bid} OK")
