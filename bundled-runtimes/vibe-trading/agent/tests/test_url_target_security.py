"""Regression tests for the SSRF URL guard and QQ outbound-media fetch.

Covers two previously-untested gaps:

- ``validate_url_target`` / ``_is_private`` must block non-globally-routable
  ranges, including RFC 6598 ``100.64.0.0/10`` (CGNAT / the default Tailscale
  mesh range). ``ipaddress.is_private`` is ``False`` for 100.64/10, so the old
  ``is_loopback | is_link_local | is_private`` check let those hosts through.
- QQ's outbound media download must reject HTTP redirects. ``media_ref`` is
  agent-controlled (it comes from ``msg.media``), so a public URL that 302s to
  an internal address would otherwise bypass the pre-flight
  ``validate_url_target`` check and exfiltrate internal content as an
  attachment. This mirrors napcat.py's inbound image download.
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging

import pytest

from src.channels import qq as qq_module
from src.channels.utils import _is_private, validate_url_target

# ─── central SSRF guard ───


@pytest.mark.parametrize(
    "ip",
    [
        # RFC 6598 shared address space — the default Tailscale/mesh range.
        # is_private is False for these, so they slipped through before the fix.
        "100.64.0.1",
        "100.100.100.100",
        "100.127.255.254",
        # classic private / internal ranges must stay blocked too
        "10.0.0.1",
        "172.16.0.1",
        "192.168.1.1",
        "127.0.0.1",
        "169.254.169.254",  # cloud metadata
        "0.0.0.0",
        "224.0.0.1",  # multicast
        # IPv6 non-global
        "::1",
        "fe80::1",
        "fc00::1",
    ],
)
def test_is_private_blocks_non_global_ranges(ip: str) -> None:
    assert _is_private(ipaddress.ip_address(ip)) is True


@pytest.mark.parametrize("ip", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_is_private_allows_global_ranges(ip: str) -> None:
    assert _is_private(ipaddress.ip_address(ip)) is False


@pytest.mark.parametrize("ip", ["100.64.0.1", "100.100.100.100"])
def test_validate_url_target_blocks_cgnat_ip_literal(ip: str) -> None:
    # IP-literal host → getaddrinfo is a local parse, so this needs no network.
    ok, err = validate_url_target(f"http://{ip}/x")
    assert ok is False
    assert "private" in err or "internal" in err


def test_validate_url_target_allows_public_ip_literal() -> None:
    ok, _err = validate_url_target("http://8.8.8.8/x")
    assert ok is True


def test_validate_url_target_loopback_only_with_opt_in() -> None:
    # Default: loopback is blocked even though it is a literal IP.
    assert validate_url_target("http://127.0.0.1/x")[0] is False
    # The narrow opt-in still allows literal loopback.
    assert validate_url_target("http://127.0.0.1/x", allow_loopback=True)[0] is True


# ─── QQ outbound-media redirect rejection ───


class _FakeResp:
    def __init__(self, status: int) -> None:
        self.status = status

    async def __aenter__(self) -> "_FakeResp":
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False

    async def read(self) -> bytes:
        return b"internal-content"


class _FakeHttp:
    """Records the ``allow_redirects`` flag and returns a canned response."""

    def __init__(self, status: int) -> None:
        self.status = status
        self.allow_redirects: object = "not-called"

    def get(self, url: str, *, allow_redirects: bool = True) -> _FakeResp:
        self.allow_redirects = allow_redirects
        return _FakeResp(self.status)


def _make_qq_channel(http: _FakeHttp) -> qq_module.QQChannel:
    # Build a minimal instance without running __init__ (which validates config
    # and creates a media dir on disk). _read_media_bytes only touches
    # self._http and self.logger.
    ch = object.__new__(qq_module.QQChannel)
    ch._http = http  # type: ignore[attr-defined]
    # CRITICAL level keeps the (intentionally loguru-style) warning quiet under
    # a stdlib logger without affecting return-value behavior.
    log = logging.getLogger("qq-test")
    log.setLevel(logging.CRITICAL)
    ch.logger = log  # type: ignore[attr-defined]
    return ch


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_qq_outbound_media_rejects_redirects(status: int) -> None:
    http = _FakeHttp(status=status)
    ch = _make_qq_channel(http)
    # Public IP-literal host → validate_url_target passes without a network call.
    data, name = asyncio.run(ch._read_media_bytes("http://8.8.8.8/x.png"))
    assert data is None
    assert name is None
    # The fix must not auto-follow redirects.
    assert http.allow_redirects is False


def test_qq_outbound_media_allows_2xx_and_does_not_follow_redirects() -> None:
    http = _FakeHttp(status=200)
    ch = _make_qq_channel(http)
    data, name = asyncio.run(ch._read_media_bytes("http://8.8.8.8/x.png"))
    assert data == b"internal-content"
    assert name == "x.png"
    assert http.allow_redirects is False


@pytest.mark.parametrize("status", [400, 404, 500])
def test_qq_outbound_media_rejects_error_status(status: int) -> None:
    http = _FakeHttp(status=status)
    ch = _make_qq_channel(http)
    data, name = asyncio.run(ch._read_media_bytes("http://8.8.8.8/x.png"))
    assert data is None
    assert name is None
