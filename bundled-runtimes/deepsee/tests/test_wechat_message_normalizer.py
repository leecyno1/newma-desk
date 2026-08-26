from __future__ import annotations

import json
import os
import sys

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from app.services.wechat_message_normalizer import (
    build_wechat_message_identity,
    build_chatlog_media_url,
    extract_app_message_fields,
    extract_image_fields,
    extract_wechat_xml_payload,
    is_file_app_message,
    normalize_message_type,
    normalize_wechat_message,
    parse_contents_dict,
    wechat_message_identities_match,
)


APPMSG_XML = """<?xml version="1.0"?>
<msg>
  <appmsg>
    <title>产业链跟踪</title>
    <des>本周重点变化</des>
    <url>https://mp.weixin.qq.com/s/example</url>
    <type>5</type>
    <sourceusername>gh_research</sourceusername>
    <sourcedisplayname>研究观察</sourcedisplayname>
    <thumburl>https://mmbiz.qpic.cn/research-thumb.jpg</thumburl>
  </appmsg>
</msg>
"""

FILE_APPMSG_XML = """<msg>
  <appmsg>
    <title>行业报告.pdf</title>
    <type>6</type>
    <appattach>
      <attachid>attach-1</attachid>
      <cdnattachurl>cdn-file-1</cdnattachurl>
      <aeskey>file-aes-key</aeskey>
      <fileext>pdf</fileext>
      <totallen>2048</totallen>
    </appattach>
  </appmsg>
</msg>"""

RECORD_APPMSG_XML = """<msg>
  <appmsg>
    <title>聊天记录</title>
    <type>24</type>
    <recorditem><![CDATA[
      <recordinfo><datalist><dataitem>
        <cdn_dataurl>record-file-1</cdn_dataurl>
        <cdn_datakey>record-key-1</cdn_datakey>
        <datatitle>转发研报.pdf</datatitle>
        <datadesc>一份转发文件</datadesc>
        <datafmt>pdf</datafmt>
        <datasize>4096</datasize>
      </dataitem></datalist></recordinfo>
    ]]></recorditem>
  </appmsg>
</msg>"""

IMAGE_XML = (
    '<msg><img cdnthumburl="https://mmbiz.qpic.cn/image-thumb.jpg" '
    'cdnmidimgurl="image-mid-1" cdnthumbaeskey="image-key-1" '
    'md5="abc123" length="1024" /></msg>'
)


def _appmsg_identity_xml(url: str) -> str:
    return f"""<msg><appmsg>
      <title>相同标题</title><type>5</type><url>{url}</url>
    </appmsg></msg>"""


@pytest.mark.parametrize(
    "raw",
    [
        {"md5": "abc123", "path": "image/a b.jpg"},
        json.dumps({"md5": "abc123", "path": "image/a b.jpg"}),
    ],
)
def test_parse_contents_dict_accepts_dict_and_json_string(raw):
    assert parse_contents_dict(raw) == {"md5": "abc123", "path": "image/a b.jpg"}


@pytest.mark.parametrize("raw", [None, "", "not-json", "[]", 123])
def test_parse_contents_dict_returns_empty_dict_for_invalid_input(raw):
    assert parse_contents_dict(raw) == {}


@pytest.mark.parametrize(
    ("raw_type", "expected"),
    [
        (0, "text"),
        (1, "text"),
        ("1", "text"),
        (3, "image"),
        ("img", "image"),
        (34, "voice"),
        ("audio", "voice"),
        (43, "video"),
        (49, "link"),
        ("app", "link"),
        ("document", "file"),
        (10000, "system"),
        ("unknown-kind", "unknown-kind"),
    ],
)
def test_normalize_message_type_unifies_numeric_and_text_aliases(raw_type, expected):
    assert normalize_message_type(raw_type) == expected


@pytest.mark.parametrize("raw_type", [None, ""])
def test_normalize_message_type_keeps_empty_values_as_other(raw_type):
    assert normalize_message_type(raw_type) == "other"


def test_file_app_message_upgrades_type_49_to_file():
    fields = extract_app_message_fields(FILE_APPMSG_XML)

    assert is_file_app_message(fields) is True
    assert normalize_message_type(49, app_message=fields) == "file"


def test_extractors_handle_prefixed_payload_appmsg_recorditem_and_image_xml():
    assert extract_wechat_xml_payload({"string": f"wxid_sender:\n{APPMSG_XML}"}).startswith("<?xml")

    appmsg = extract_app_message_fields(f"wxid_sender:\n{APPMSG_XML}")
    assert appmsg["title"] == "产业链跟踪"
    assert appmsg["url"] == "https://mp.weixin.qq.com/s/example"
    assert appmsg["sourceusername"] == "gh_research"

    record = extract_app_message_fields(RECORD_APPMSG_XML)
    assert record["cdn_dataurl"] == "record-file-1"
    assert record["cdndatakey"] == "record-key-1"
    assert record["datatitle"] == "转发研报.pdf"
    assert is_file_app_message(record) is True

    image = extract_image_fields({"Content": f"wxid_sender:\n{IMAGE_XML}"})
    assert image["cdnthumburl"] == "https://mmbiz.qpic.cn/image-thumb.jpg"
    assert image["cdnmidimgurl"] == "image-mid-1"
    assert image["md5"] == "abc123"


def test_chatlog_and_callback_image_inputs_produce_same_canonical_media_fields():
    chatlog = normalize_wechat_message(
        msg_type=3,
        content="[图片]",
        contents={
            "cdnthumburl": "https://mmbiz.qpic.cn/image-thumb.jpg",
            "cdnmidimgurl": "image-mid-1",
            "cdnthumbaeskey": "image-key-1",
            "md5": "abc123",
            "length": "1024",
        },
    )
    callback = normalize_wechat_message(msg_type=3, content=f"wxid_sender:\n{IMAGE_XML}")

    assert callback.message_type == chatlog.message_type == "image"
    assert callback.media_url == chatlog.media_url == "https://mmbiz.qpic.cn/image-thumb.jpg"
    assert callback.contents == chatlog.contents


def test_chatlog_and_callback_mp_links_produce_same_canonical_fields():
    chatlog = normalize_wechat_message(
        msg_type=49,
        content="产业链跟踪",
        contents={
            "appmsg_type": "5",
            "title": "产业链跟踪",
            "desc": "本周重点变化",
            "url": "https://mp.weixin.qq.com/s/example",
            "sourceusername": "gh_research",
            "sourcedisplayname": "研究观察",
            "thumburl": "https://mmbiz.qpic.cn/research-thumb.jpg",
        },
    )
    callback = normalize_wechat_message(msg_type=49, content=APPMSG_XML)

    assert callback.message_type == chatlog.message_type == "link"
    assert callback.content_text == chatlog.content_text == "产业链跟踪"
    assert callback.display_title == chatlog.display_title == "产业链跟踪"
    assert callback.source_username == chatlog.source_username == "gh_research"
    assert callback.contents == chatlog.contents
    assert callback.media_url == chatlog.media_url == "https://mp.weixin.qq.com/s/example"


def test_normalizer_fills_xml_fields_without_overwriting_explicit_contents():
    normalized = normalize_wechat_message(
        msg_type="app",
        content=APPMSG_XML,
        contents={"title": "显式标题", "sourceusername": "gh_explicit"},
    )

    assert normalized.display_title == "显式标题"
    assert normalized.source_username == "gh_explicit"
    assert normalized.contents["url"] == "https://mp.weixin.qq.com/s/example"
    assert normalized.contents["title"] == "显式标题"


def test_build_chatlog_media_url_preserves_encoding_and_explicit_host():
    assert build_chatlog_media_url(
        "image",
        {"md5": "a/b", "path": "folder/图 片.jpg"},
        host="127.0.0.1:5030/",
    ) == "http://127.0.0.1:5030/image/a%2Fb,folder/%E5%9B%BE%20%E7%89%87.jpg"


def test_wechatapi_media_policy_keeps_opaque_image_id_out_of_media_url():
    opaque_thumb_id = "3057020100044b30490201000204f1e2d3c402032f4c0204aabbccdd0204"
    normalized = normalize_wechat_message(
        msg_type=3,
        content=f'<msg><img cdnthumburl="{opaque_thumb_id}" md5="opaque-image-md5" /></msg>',
        media_policy="wechatapi",
    )

    assert normalized.message_type == "image"
    assert normalized.contents["cdnthumburl"] == opaque_thumb_id
    assert normalized.contents["md5"] == "opaque-image-md5"
    assert normalized.media_url is None


def test_wechatapi_media_policy_does_not_build_chatlog_file_url_from_md5():
    opaque_file_id = "3052020100044b30490201000204a1b2c3d402032f4c0204ddeeff000204"
    file_xml = f"""<msg><appmsg>
      <title>opaque-report.pdf</title><type>6</type><md5>opaque-file-md5</md5>
      <appattach>
        <cdnattachurl>{opaque_file_id}</cdnattachurl>
        <aeskey>opaque-file-key</aeskey><fileext>pdf</fileext><totallen>1024</totallen>
      </appattach>
    </appmsg></msg>"""
    normalized = normalize_wechat_message(
        msg_type=49,
        content=file_xml,
        media_policy="wechatapi",
    )

    assert normalized.message_type == "file"
    assert normalized.contents["cdnattachurl"] == opaque_file_id
    assert normalized.contents["md5"] == "opaque-file-md5"
    assert normalized.media_url is None


def test_message_identity_distinguishes_same_title_with_different_urls():
    identity_a = build_wechat_message_identity(
        msg_type=49,
        content=_appmsg_identity_xml("https://mp.weixin.qq.com/s/identity-a"),
    )
    identity_b = build_wechat_message_identity(
        msg_type=49,
        content=_appmsg_identity_xml("https://mp.weixin.qq.com/s/identity-b"),
    )

    assert identity_a.has_strong_fields is True
    assert identity_b.has_strong_fields is True
    assert wechat_message_identities_match(identity_a, identity_b) is False


def test_message_identity_matches_raw_xml_to_empty_content_with_same_strong_contents():
    raw_identity = build_wechat_message_identity(
        msg_type=49,
        content=_appmsg_identity_xml("https://mp.weixin.qq.com/s/identity-same"),
    )
    historical_identity = build_wechat_message_identity(
        msg_type="49",
        content="",
        contents={
            "title": "相同标题",
            "url": "https://mp.weixin.qq.com/s/identity-same",
        },
    )

    assert wechat_message_identities_match(raw_identity, historical_identity) is True


def test_message_identity_does_not_merge_strong_with_weak_or_empty_candidates():
    strong_identity = build_wechat_message_identity(
        msg_type=49,
        content=_appmsg_identity_xml("https://mp.weixin.qq.com/s/identity-strong"),
    )
    weak_identity = build_wechat_message_identity(
        msg_type=49,
        content="相同标题",
    )
    empty_a = build_wechat_message_identity(msg_type="text", content="")
    empty_b = build_wechat_message_identity(msg_type="text", content="")

    assert wechat_message_identities_match(strong_identity, weak_identity) is False
    assert wechat_message_identities_match(empty_a, empty_b) is False


def test_message_identity_matches_when_historical_strong_fields_are_a_subset():
    current_identity = build_wechat_message_identity(
        msg_type=49,
        content="相同标题",
        contents={
            "url": "https://mp.weixin.qq.com/s/identity-subset",
            "md5": "identity-extra-md5",
        },
    )
    historical_identity = build_wechat_message_identity(
        msg_type=49,
        content="相同标题",
        contents={"url": "https://mp.weixin.qq.com/s/identity-subset"},
    )

    assert wechat_message_identities_match(current_identity, historical_identity) is True


def test_message_identity_rejects_conflicting_shared_strong_fields():
    identity_a = build_wechat_message_identity(
        msg_type=49,
        content="相同标题",
        contents={
            "url": "https://mp.weixin.qq.com/s/identity-conflict",
            "md5": "md5-a",
        },
    )
    identity_b = build_wechat_message_identity(
        msg_type=49,
        content="相同标题",
        contents={
            "url": "https://mp.weixin.qq.com/s/identity-conflict",
            "md5": "md5-b",
        },
    )

    assert wechat_message_identities_match(identity_a, identity_b) is False
