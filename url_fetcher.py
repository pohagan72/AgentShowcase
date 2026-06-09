# url_fetcher.py
# SSRF-guarded HTTPS fetcher for the MCP tool surface.
#
# Why this exists:
# The MCP tools accept `content_url` instead of `content_base64`. The server
# fetches the bytes on behalf of the caller. That means a malicious caller
# could otherwise reach internal services (Postgres on the Railway internal
# network, cloud metadata IPs, localhost) by handing us a crafted URL.
#
# Guards (defense in depth):
# 1. Scheme: HTTPS only. http://, file://, ftp://, gopher:// all rejected.
# 2. Host resolution: getaddrinfo() the hostname, walk every resolved IP,
#    reject if any is private / loopback / link-local / multicast / reserved /
#    cloud-metadata. Pin the connection to the resolved-and-validated IPs so
#    a DNS-rebinding attack can't switch targets between the check and the
#    connect.
# 3. Redirect chain: each Location is re-validated through the same path.
#    Capped at MAX_REDIRECTS.
# 4. Size: Content-Length checked upfront; stream-aborted past `max_bytes`
#    so a lying server can't sneak through.
# 5. Time: connect timeout + total wall-clock cap (stays well under the
#    MCP_TOOL_TIMEOUT_SECONDS=60 envelope).
# 6. No auth headers forwarded, no cookies kept.

from __future__ import annotations

import ipaddress
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager


MAX_REDIRECTS = 3
CONNECT_TIMEOUT_SECONDS = 5.0
TOTAL_TIMEOUT_SECONDS = 30.0
READ_CHUNK_BYTES = 64 * 1024


class UrlFetchError(Exception):
    """Raised for any caller-induced failure (bad URL, SSRF, too big, etc.).

    Tool handlers catch this and re-raise as ToolError so the MCP route
    surfaces the message as isError=true with the quota refunded.
    """


def fetch_url_bytes(url: str, *, max_bytes: int) -> tuple[bytes, str]:
    """Fetch `url` via HTTPS with SSRF/size/time guards.

    Returns (raw_bytes, content_type). Raises UrlFetchError on any failure.
    """
    if not isinstance(url, str) or not url:
        raise UrlFetchError("URL is required")

    deadline = time.monotonic() + TOTAL_TIMEOUT_SECONDS

    current_url = url
    for hop in range(MAX_REDIRECTS + 1):
        if time.monotonic() > deadline:
            raise UrlFetchError("Fetch timed out")

        parsed = _validate_url(current_url)
        resolved_ips = _resolve_and_screen(parsed.hostname)

        session = requests.Session()
        session.trust_env = False  # ignore HTTP(S)_PROXY env vars
        session.mount("https://", _PinnedHTTPSAdapter(resolved_ips))

        try:
            resp = session.get(
                current_url,
                stream=True,
                timeout=(CONNECT_TIMEOUT_SECONDS, _remaining(deadline)),
                allow_redirects=False,
                headers={
                    "User-Agent": "Synzo-MCP/1.0 (+https://www.synzo.ai)",
                    "Accept": "*/*",
                },
            )
        except requests.RequestException as e:
            raise UrlFetchError(f"Fetch failed: {e}") from e

        with resp:
            if 300 <= resp.status_code < 400:
                location = resp.headers.get("Location")
                if not location:
                    raise UrlFetchError(
                        f"Redirect {resp.status_code} without Location header"
                    )
                # Re-validate the next hop through the loop.
                current_url = requests.compat.urljoin(current_url, location)
                continue

            if resp.status_code >= 400:
                raise UrlFetchError(
                    f"Fetch failed: HTTP {resp.status_code}"
                )

            content_length = resp.headers.get("Content-Length")
            if content_length is not None:
                try:
                    declared = int(content_length)
                except ValueError:
                    declared = None
                if declared is not None and declared > max_bytes:
                    raise UrlFetchError(
                        f"Content-Length {declared} exceeds cap {max_bytes}"
                    )

            buf = bytearray()
            for chunk in resp.iter_content(chunk_size=READ_CHUNK_BYTES):
                if time.monotonic() > deadline:
                    raise UrlFetchError("Fetch timed out")
                if not chunk:
                    continue
                buf.extend(chunk)
                if len(buf) > max_bytes:
                    raise UrlFetchError(
                        f"Response body exceeded cap {max_bytes}"
                    )

            content_type = (resp.headers.get("Content-Type") or "").split(";")[0].strip()
            return bytes(buf), content_type

    raise UrlFetchError(f"Too many redirects (>{MAX_REDIRECTS})")


# --- URL + IP validation -----------------------------------------------------


@dataclass(frozen=True)
class _ParsedTarget:
    scheme: str
    hostname: str
    port: int


def _validate_url(url: str) -> _ParsedTarget:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise UrlFetchError(
            f"Only https:// URLs are allowed (got scheme '{parsed.scheme}')"
        )
    if not parsed.hostname:
        raise UrlFetchError("URL is missing a hostname")
    # Reject userinfo embedded in URL (https://user:pass@host) to keep the
    # fetch clean of credentials we'd otherwise have to forward.
    if parsed.username or parsed.password:
        raise UrlFetchError("URLs with embedded credentials are not allowed")
    port = parsed.port or 443
    return _ParsedTarget(scheme=parsed.scheme, hostname=parsed.hostname, port=port)


def _resolve_and_screen(hostname: str) -> list[str]:
    """Resolve hostname to IPs and reject if any IP is non-public.

    Returns the list of allowed IPs to pin against. We require ALL resolved
    addresses to be public — partial allowlists invite DNS-rebinding where
    the kernel falls back to the private IP between our check and connect.
    """
    try:
        infos = socket.getaddrinfo(
            hostname, None, type=socket.SOCK_STREAM
        )
    except socket.gaierror as e:
        raise UrlFetchError(f"DNS resolution failed: {e}") from e

    if not infos:
        raise UrlFetchError("DNS resolution returned no addresses")

    ips: list[str] = []
    for info in infos:
        ip_str = info[4][0]
        ip_obj = ipaddress.ip_address(ip_str)
        _reject_non_public(ip_obj)
        ips.append(ip_str)
    return ips


def _reject_non_public(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> None:
    """Raise UrlFetchError if `ip` isn't a globally routable public address."""
    # Cloud-metadata IPs first so the error message is specific.
    if str(ip) in {"169.254.169.254", "fd00:ec2::254"}:
        raise UrlFetchError(f"IP {ip} is a cloud metadata endpoint")

    if ip.is_loopback:
        raise UrlFetchError(f"IP {ip} is loopback")
    if ip.is_private:
        raise UrlFetchError(f"IP {ip} is in a private range")
    if ip.is_link_local:
        raise UrlFetchError(f"IP {ip} is link-local")
    if ip.is_multicast:
        raise UrlFetchError(f"IP {ip} is multicast")
    if ip.is_reserved:
        raise UrlFetchError(f"IP {ip} is reserved")
    if ip.is_unspecified:
        raise UrlFetchError(f"IP {ip} is unspecified (0.0.0.0)")


def _remaining(deadline: float) -> float:
    return max(0.5, deadline - time.monotonic())


# --- Pinned-IP HTTPS adapter -------------------------------------------------


class _PinnedHTTPSAdapter(HTTPAdapter):
    """An HTTPAdapter that only allows connections to a fixed IP allowlist.

    requests resolves the hostname again at connect time; without this adapter
    we'd be vulnerable to DNS-rebinding between _resolve_and_screen() and the
    actual connection. We patch urllib3's source_address-style hook by
    wrapping socket.getaddrinfo in the poolmanager.
    """

    def __init__(self, allowed_ips: list[str]):
        self._allowed_ips: set[str] = set(allowed_ips)
        super().__init__()

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        allowed_ips = self._allowed_ips

        # Subclass PoolManager so we can intercept the per-connection getaddrinfo.
        class _PinnedPoolManager(PoolManager):
            pass

        self.poolmanager = _PinnedPoolManager(
            num_pools=connections,
            maxsize=maxsize,
            block=block,
            **pool_kwargs,
        )

        # Monkeypatch socket.getaddrinfo only for the duration of fetches that
        # go through this adapter's pool. Stack-discipline approach: wrap each
        # urlopen call so we don't leak the patch.
        original_urlopen = self.poolmanager.urlopen

        def _guarded_urlopen(method, url, **kwargs):
            real_getaddrinfo = socket.getaddrinfo

            def _filtered_getaddrinfo(host, *args, **kw):
                infos = real_getaddrinfo(host, *args, **kw)
                filtered = [info for info in infos if info[4][0] in allowed_ips]
                if not filtered:
                    raise socket.gaierror(
                        f"All resolved IPs for {host} blocked by SSRF policy "
                        f"(allowed: {sorted(allowed_ips)})"
                    )
                return filtered

            socket.getaddrinfo = _filtered_getaddrinfo
            try:
                return original_urlopen(method, url, **kwargs)
            finally:
                socket.getaddrinfo = real_getaddrinfo

        self.poolmanager.urlopen = _guarded_urlopen
