import cv2
import numpy as np
import pytest

from app import processing
from app.processing import PermanentError


def make_image(w, h, channels=3):
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, size=(h, w, channels), dtype=np.uint8)


def encoded(img, ext):
    ok, buf = cv2.imencode(ext, img)
    assert ok
    return buf.tobytes()


@pytest.mark.parametrize("ext", [".jpg", ".png", ".webp"])
def test_resize_fits_within_bounds_and_keeps_aspect(ext):
    out = processing.run("resize", {"max_width": 400, "max_height": 400}, encoded(make_image(2000, 1000), ext), ext)
    h, w = processing.decode(out).shape[:2]
    assert (w, h) == (400, 200)


def test_never_upscales():
    img = make_image(100, 50)
    assert processing.resize(img, 1000, 1000) is img


def test_tall_image_limited_by_height():
    assert processing.resize(make_image(300, 3000), 500, 600).shape[:2] == (600, 60)


def test_png_alpha_channel_preserved():
    out = processing.run("resize", {"max_width": 50, "max_height": 50}, encoded(make_image(200, 200, 4), ".png"), ".png")
    assert processing.decode(out).shape == (50, 50, 4)


def test_deterministic_output():
    data = encoded(make_image(800, 600), ".jpg")
    params = {"max_width": 300, "max_height": 300}
    assert processing.run("resize", params, data, ".jpg") == processing.run("resize", params, data, ".jpg")


def test_corrupt_input_is_permanent_error():
    with pytest.raises(PermanentError):
        processing.run("resize", {}, b"not an image", ".png")


def test_unknown_operation_is_permanent_error():
    with pytest.raises(PermanentError):
        processing.run("sharpen", {}, encoded(make_image(10, 10), ".png"), ".png")
