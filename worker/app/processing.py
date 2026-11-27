"""Image operations. Pure functions on bytes, so they are easy to test and deterministic:
processing the same input twice gives the same output, which keeps retries idempotent."""
import cv2
import numpy as np


class PermanentError(Exception):
    """The job can never succeed (bad input), so retrying is pointless."""


ENCODE_PARAMS = {
    ".jpg": [cv2.IMWRITE_JPEG_QUALITY, 90],
    ".png": [cv2.IMWRITE_PNG_COMPRESSION, 6],
    ".webp": [cv2.IMWRITE_WEBP_QUALITY, 90],
}


def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None:
        raise PermanentError("could not decode image")
    return img


def encode(img: np.ndarray, ext: str) -> bytes:
    if ext not in ENCODE_PARAMS:
        raise PermanentError(f"unsupported output format {ext}")
    ok, buf = cv2.imencode(ext, img, ENCODE_PARAMS[ext])
    if not ok:
        raise PermanentError(f"could not encode image as {ext}")
    return buf.tobytes()


def resize(img: np.ndarray, max_width: int, max_height: int) -> np.ndarray:
    """Shrink to fit inside max_width x max_height, keeping aspect ratio. Never upscales."""
    h, w = img.shape[:2]
    scale = min(max_width / w, max_height / h, 1.0)
    if scale == 1.0:
        return img
    new_size = (max(1, round(w * scale)), max(1, round(h * scale)))
    return cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)


def run(operation: str, params: dict, data: bytes, ext: str) -> bytes:
    img = decode(data)
    if operation == "resize":
        out = resize(img, int(params.get("max_width", 1024)), int(params.get("max_height", 1024)))
    else:
        raise PermanentError(f"unknown operation {operation!r}")
    return encode(out, ext)
