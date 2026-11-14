"""Fetch a company's icon from its own website, safely.

Used only as a fallback inside the opt-in logo fetch, when the icon service has no icon. The
domain comes from a public register, Wikidata or the user, so it is untrusted: it could name a
host that resolves to this machine or the local network. Every request therefore:

- uses https on port 443 only,
- resolves the host here and refuses unless every address is public (no private, loopback,
  link-local, reserved or multicast ranges),
- connects to the exact IP that passed the check, so DNS cannot change the answer between check
  and connect (DNS rebinding), while TLS still verifies the certificate for the hostname,
- follows at most MAX_REDIRECTS redirects, each checked the same way,
- caps time and size.
"""

from __future__ import annotations

import http.client
import ipaddress
import socket
import ssl
import urllib.parse
from collections.abc import Callable
from html.parser import HTMLParser

import truststore

TIMEOUT = 8
MAX_REDIRECTS = 3
MAX_HTML = 512 * 1024
MAX_IMAGE = 256 * 1024


def tls_context() -> ssl.SSLContext:
    """Verify certificates with the operating system's trust store, like the browser does. It
    also completes chains that a server sends incomplete, which Python's bundle cannot."""
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


# (status, content_type, body). Injected in tests so they never touch the network.
SiteGet = Callable[[str, int], tuple[int, str, bytes]]


class Blocked(Exception):
    """The URL or the address it resolves to is not allowed."""


def public_ips(host: str) -> list[str]:
    """Resolve host. Raise Blocked unless it resolves, and every address is public."""
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as e:
        raise Blocked(f"cannot resolve {host}") from e
    # IPv4 first: some networks resolve AAAA records but cannot route IPv6.
    ips = sorted({info[4][0] for info in infos}, key=lambda ip: (":" in ip, ip))
    if not ips:
        raise Blocked(f"no address for {host}")
    for ip in ips:
        addr = ipaddress.ip_address(ip.split("%", 1)[0])
        if not addr.is_global or addr.is_multicast or addr.is_reserved:
            raise Blocked(f"{host} resolves to a non-public address")
    return ips


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    """HTTPS to a fixed IP, with SNI and certificate checks for the real hostname."""

    def __init__(self, host: str, ip: str, timeout: float):
        super().__init__(host, 443, timeout=timeout, context=tls_context())
        self._ip = ip

    def connect(self) -> None:
        sock = socket.create_connection((self._ip, 443), timeout=self.timeout)
        self.sock = self._context.wrap_socket(sock, server_hostname=self.host)


def check_url(url: str) -> urllib.parse.SplitResult:
    u = urllib.parse.urlsplit(url)
    if u.scheme != "https" or not u.hostname:
        raise Blocked("https only")
    if u.port not in (None, 443):
        raise Blocked("port 443 only")
    if u.username or u.password:
        raise Blocked("no credentials in URLs")
    return u


def safe_get(url: str, limit: int, user_agent: str) -> tuple[int, str, bytes]:
    """GET a public https URL. Returns (status, content_type, body); status 0 means refused or
    failed. Never raises for network or policy reasons."""
    try:
        for _ in range(MAX_REDIRECTS + 1):
            u = check_url(url)
            ip = public_ips(u.hostname)[0]
            conn = _PinnedHTTPSConnection(u.hostname, ip, TIMEOUT)
            try:
                path = (u.path or "/") + (f"?{u.query}" if u.query else "")
                conn.request("GET", path, headers={"User-Agent": user_agent, "Accept": "*/*",
                                                   "Host": u.hostname})
                r = conn.getresponse()
                if r.status in (301, 302, 303, 307, 308):
                    loc = r.getheader("Location")
                    if not loc:
                        return r.status, "", b""
                    url = urllib.parse.urljoin(url, loc)
                    continue
                body = r.read(limit + 1)
                if len(body) > limit:
                    return 0, "", b""
                return r.status, r.getheader("Content-Type", ""), body
            finally:
                conn.close()
        return 0, "", b""  # too many redirects
    except (Blocked, OSError, http.client.HTTPException, ssl.SSLError, ValueError):
        return 0, "", b""


class _IconLinks(HTMLParser):
    """Collect <link rel="...icon..." href sizes type> from a page head."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.links: list[dict[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag != "link":
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        rel = a.get("rel", "").lower().split()
        if a.get("href") and ("icon" in rel or "apple-touch-icon" in rel
                              or "apple-touch-icon-precomposed" in rel):
            self.links.append(a)


def _size(a: dict[str, str]) -> int:
    best = 0
    for token in a.get("sizes", "").lower().split():
        w, _, h = token.partition("x")
        if w.isdigit() and h.isdigit():
            best = max(best, min(int(w), int(h)))
    return best


def icon_candidates(html: str, base_url: str) -> list[str]:
    """Icon URLs declared by a page, best first: apple-touch-icon, then largest, never SVG."""
    p = _IconLinks()
    try:
        p.feed(html)
    except Exception:  # broken HTML must not break the fetch
        return []
    scored = []
    for a in p.links:
        href = urllib.parse.urljoin(base_url, a["href"].strip())
        if a.get("type", "").lower() == "image/svg+xml" or href.lower().split("?")[0].endswith(".svg"):
            continue
        touch = any(r.startswith("apple-touch-icon") for r in a.get("rel", "").lower().split())
        size = _size(a) or (180 if touch else 0)
        scored.append((touch, size, href))
    scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
    seen, out = set(), []
    for _, _, href in scored:
        if href not in seen and href.startswith("https://"):
            seen.add(href)
            out.append(href)
    return out


def site_icon(domain: str, get: SiteGet, sniff: Callable[[bytes], tuple[str, str] | None]
              ) -> bytes | None:
    """Best raster icon the site offers: icons declared in its HTML, then the two usual paths."""
    base = f"https://{domain}/"
    status, ctype, body = get(base, MAX_HTML)
    candidates = []
    if status == 200 and body and "html" in ctype.lower():
        candidates = icon_candidates(body.decode("utf-8", errors="replace"), base)
    candidates += [base + "apple-touch-icon.png", base + "favicon.ico"]
    for url in candidates[:5]:
        status, _, data = get(url, MAX_IMAGE)
        if status == 200 and sniff(data):
            return data
    return None
