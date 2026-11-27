"""End-to-end test of the whole pipeline: API -> S3 -> SQS -> worker -> S3 -> API.

Uploads N generated PNGs plus one corrupt file, waits for the batch to finish, then
downloads every result and checks its dimensions. Standard library only. Usage:

    docker compose up -d --wait
    python3 scripts/smoke_test_pipeline.py [N]
"""
import json
import os
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

API = os.environ.get("API_URL", "http://localhost:8000")
N = int(sys.argv[1]) if len(sys.argv) > 1 else 25
SRC_W, SRC_H, MAX = 1600, 1200, 512
EXPECTED = (512, 384)


def make_png(w: int, h: int, seed: int) -> bytes:
    """A w x h RGB gradient PNG, built by hand so no imaging library is needed."""
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    rows = b"".join(
        b"\x00" + bytes(v for x in range(w) for v in ((x + seed) % 256, (y * 2) % 256, seed % 256))
        for y in range(h)
    )
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(rows, 6)) + chunk(b"IEND", b"")


def png_size(data: bytes) -> tuple[int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "not a PNG"
    return struct.unpack(">II", data[16:24])


def call(method, url, body=None, raw=None, headers=None, binary=False):
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    h = {"Content-Type": "application/json"} if body is not None else {}
    h.update(headers or {})
    with urllib.request.urlopen(urllib.request.Request(url, data=data, method=method, headers=h)) as r:
        payload = r.read()
        return payload if binary or raw is not None else json.loads(payload)


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        sys.exit(1)


files = [{"filename": f"photo{i:03d}.png", "content_type": "image/png"} for i in range(N)]
files.append({"filename": "corrupt.png", "content_type": "image/png"})
batch = call("POST", f"{API}/batches", {"files": files, "params": {"max_width": MAX, "max_height": MAX}})
bid = batch["batch_id"]
print(f"batch {bid}: {N} images + 1 corrupt")

base = make_png(SRC_W, SRC_H, 7)
for u in batch["uploads"]:
    data = b"definitely not a png" if u["filename"] == "corrupt.png" else base
    call("PUT", u["upload_url"], raw=data, headers={"Content-Type": u["content_type"]})
print(f"uploaded {len(batch['uploads'])} files directly to S3 ({len(base) // 1024} KB each)")

start = time.monotonic()
status = call("POST", f"{API}/batches/{bid}/confirm")
while status["status"] == "processing" and time.monotonic() - start < 120:
    time.sleep(0.5)
    status = call("GET", f"{API}/batches/{bid}")
elapsed = time.monotonic() - start
print(f"finished in {elapsed:.1f}s ({N / elapsed:.1f} images/s, single worker): {status['counts']}")

check(status["status"] == "partial_failure", f"batch status is partial_failure (got {status['status']})")
check(status["counts"] == {"done": N, "failed": 1}, "all good images done, corrupt one failed")
bad = next(j for j in status["jobs"] if j["filename"] == "corrupt.png")
check(bad["error"] == "could not decode image", f"corrupt job has a clear error: {bad['error']!r}")

results = call("GET", f"{API}/batches/{bid}/results")["results"]
check(len(results) == N, f"{len(results)} download links returned")
sizes = {png_size(call("GET", r["download_url"], binary=True)) for r in results}
check(sizes == {EXPECTED}, f"every result is {EXPECTED[0]}x{EXPECTED[1]} (got {sizes})")
