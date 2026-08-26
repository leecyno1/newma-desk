import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.routers.messages import _build_image_candidates


def test_image_candidates_prioritize_medium_then_fallback():
    out = _build_image_candidates(
        host="http://127.0.0.1:5030",
        md5="abc123",
        path="msg/attach/u/2025-08/Img/xyz",
        direct_url="",
    )
    assert out[0] == "http://127.0.0.1:5030/image/abc123,msg/attach/u/2025-08/Img/xyz"
    assert "http://127.0.0.1:5030/data/msg/attach/u/2025-08/Img/xyz_M.dat" in out
    assert "http://127.0.0.1:5030/data/msg/attach/u/2025-08/Img/xyz_t.dat" in out
    assert out[-1] == "http://127.0.0.1:5030/data/msg/attach/u/2025-08/Img/xyz"


def test_image_candidates_keep_direct_url_first_when_given():
    out = _build_image_candidates(
        host="http://127.0.0.1:5030",
        md5="abc123",
        path="msg/attach/u/2025-08/Img/xyz",
        direct_url="http://127.0.0.1:5030/image/abc123,msg/attach/u/2025-08/Img/xyz",
    )
    assert out[0] == "http://127.0.0.1:5030/image/abc123,msg/attach/u/2025-08/Img/xyz"
