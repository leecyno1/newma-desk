import os
import sys

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.sync_service import _build_chatlog_media_url, _extract_contents_dict


def test_build_image_url_with_md5_and_path():
    url = _build_chatlog_media_url(
        3,
        {
            "md5": "af6e7cf6bb471511a1db9a1bbed3d5a8",
            "path": "msg/attach/ddcc8/2025-05/Img/18d74a9124e1d6250645f977d67b7040",
        },
        host="http://127.0.0.1:5030",
    )
    assert url == (
        "http://127.0.0.1:5030/image/"
        "af6e7cf6bb471511a1db9a1bbed3d5a8,msg/attach/ddcc8/2025-05/Img/18d74a9124e1d6250645f977d67b7040"
    )


def test_build_voice_url():
    url = _build_chatlog_media_url(
        34,
        {"voice": "8897458773382642568"},
        host="http://127.0.0.1:5030",
    )
    assert url == "http://127.0.0.1:5030/voice/8897458773382642568"


def test_build_file_url_for_type49_with_md5():
    url = _build_chatlog_media_url(
        49,
        {"md5": "5653fb3a7fe163841c2d14f50747ad5e", "title": "x.pdf"},
        host="http://127.0.0.1:5030",
    )
    assert url == "http://127.0.0.1:5030/file/5653fb3a7fe163841c2d14f50747ad5e"


def test_type49_link_keeps_direct_url():
    direct = "http://mp.weixin.qq.com/s?abc=1"
    url = _build_chatlog_media_url(49, {"url": direct})
    assert url == direct


def test_type49_link_prefers_article_url_over_thumbnail():
    article_url = "https://mp.weixin.qq.com/s/article"
    thumbnail_url = "https://mmbiz.qpic.cn/article-thumb.jpg"

    url = _build_chatlog_media_url(
        49,
        {
            "url": article_url,
            "cdnthumburl": thumbnail_url,
        },
    )

    assert url == article_url


def test_image_type_still_prefers_thumbnail_url():
    thumbnail_url = "https://mmbiz.qpic.cn/image-thumb.jpg"

    url = _build_chatlog_media_url(
        3,
        {
            "url": "https://example.com/not-the-image.jpg",
            "cdnthumburl": thumbnail_url,
        },
    )

    assert url == thumbnail_url


def test_extract_contents_dict_supports_json_string():
    parsed = _extract_contents_dict('{"md5":"m1","path":"msg/attach/a"}')
    assert parsed["md5"] == "m1"
    assert parsed["path"] == "msg/attach/a"
