import socket

import pytest

from linkgraph import logos, siteicons

from .test_logos import PNG, FakeWeb, png


def fake_dns(answers):
    def getaddrinfo(host, port, type=0):
        if host not in answers:
            raise socket.gaierror("nope")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, port)) for ip in answers[host]]
    return getaddrinfo


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.1.2.3", "192.168.1.10", "172.16.0.5", "169.254.169.254",
                                "100.64.0.1", "0.0.0.0", "224.0.0.1", "::1", "fe80::1", "fd00::1"])
def test_non_public_addresses_are_blocked(monkeypatch, ip):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo", fake_dns({"evil.example": [ip]}))
    with pytest.raises(siteicons.Blocked):
        siteicons.public_ips("evil.example")


def test_mixed_answer_is_blocked(monkeypatch):
    # One public and one private address: the connection could land on either, so refuse.
    monkeypatch.setattr(siteicons.socket, "getaddrinfo", fake_dns({"mixed.example": ["93.184.215.14", "10.0.0.1"]}))
    with pytest.raises(siteicons.Blocked):
        siteicons.public_ips("mixed.example")


def test_public_address_passes(monkeypatch):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo", fake_dns({"ok.example": ["93.184.215.14"]}))
    assert siteicons.public_ips("ok.example") == ["93.184.215.14"]


@pytest.mark.parametrize("url", ["http://acme.no/", "https://acme.no:8443/", "ftp://acme.no/",
                                 "https://user:pw@acme.no/", "file:///etc/passwd", "https:///nohost"])
def test_check_url_refuses(url):
    with pytest.raises(siteicons.Blocked):
        siteicons.check_url(url)


def test_safe_get_never_connects_to_private_host(monkeypatch):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo", fake_dns({"intranet.acme.no": ["10.0.0.7"]}))

    def boom(*a, **k):
        raise AssertionError("must not connect")
    monkeypatch.setattr(siteicons.socket, "create_connection", boom)
    assert siteicons.safe_get("https://intranet.acme.no/", 1000, "ua") == (0, "", b"")


class FakeResponse:
    def __init__(self, status, headers=None, body=b""):
        self.status, self._h, self._b = status, headers or {}, body

    def getheader(self, k, default=None):
        return self._h.get(k, default)

    def read(self, n):
        return self._b[:n]


def test_safe_get_checks_every_redirect(monkeypatch):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo",
                        fake_dns({"acme.no": ["93.184.215.14"], "metadata.internal": ["169.254.169.254"]}))
    connected = []

    class FakeConn:
        def __init__(self, host, ip, timeout):
            connected.append((host, ip))

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return FakeResponse(302, {"Location": "https://metadata.internal/latest/"})

        def close(self):
            pass

    monkeypatch.setattr(siteicons, "_PinnedHTTPSConnection", FakeConn)
    assert siteicons.safe_get("https://acme.no/", 1000, "ua") == (0, "", b"")
    assert connected == [("acme.no", "93.184.215.14")]  # the redirect target was never contacted


def test_safe_get_pins_the_checked_ip_and_caps_size(monkeypatch):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo", fake_dns({"acme.no": ["93.184.215.14"]}))
    seen = []

    class FakeConn:
        def __init__(self, host, ip, timeout):
            seen.append(ip)

        def request(self, *a, **k):
            pass

        def getresponse(self):
            return FakeResponse(200, {"Content-Type": "image/png"}, b"x" * 50)

        def close(self):
            pass

    monkeypatch.setattr(siteicons, "_PinnedHTTPSConnection", FakeConn)
    assert siteicons.safe_get("https://acme.no/i.png", 100, "ua")[0] == 200
    assert siteicons.safe_get("https://acme.no/i.png", 10, "ua") == (0, "", b"")
    assert seen == ["93.184.215.14", "93.184.215.14"]


def test_icon_candidates_best_first_and_no_svg():
    html = """<html><head>
      <link rel="icon" href="/favicon-16.png" sizes="16x16">
      <link rel="icon" href="/favicon-96.png" sizes="96x96">
      <link rel="icon" type="image/svg+xml" href="/logo.svg">
      <link rel="apple-touch-icon" href="https://cdn.acme.no/touch.png">
      <link rel="stylesheet" href="/x.css">
      <link rel="icon" href="http://acme.no/insecure.png">
    </head></html>"""
    assert siteicons.icon_candidates(html, "https://acme.no/") == [
        "https://cdn.acme.no/touch.png", "https://acme.no/favicon-96.png", "https://acme.no/favicon-16.png"]


def test_store_falls_back_to_site_icon(tmp_path):
    big = png(180, 180)
    web = FakeWeb(brreg={"Telenor": [{"navn": "TELENOR ASA", "hjemmeside": "www.telenor.no"}]},
                  sites={"https://telenor.no/": ("text/html; charset=utf-8",
                                                 b'<link rel="apple-touch-icon" href="/t.png">'),
                         "https://telenor.no/t.png": ("image/png", big)})
    store = logos.LogoStore(tmp_path, web, web.site)
    e = store.fetch_one("telenor", "Telenor")
    assert e["status"] == "ok" and e["icon_from"] == "site"
    assert any("icons.duckduckgo.com" in c for c in web.calls)  # the icon service is asked first


def test_icon_service_hit_skips_the_site(tmp_path):
    web = FakeWeb(brreg={"Acme": [{"navn": "ACME AS", "hjemmeside": "acme.no"}]}, icons={"acme.no": PNG})
    store = logos.LogoStore(tmp_path, web, web.site)
    assert store.fetch_one("acme", "Acme")["icon_from"] == "duckduckgo"
    assert not any(c.startswith("https://acme.no") for c in web.calls)


def test_ipv4_is_tried_first(monkeypatch):
    monkeypatch.setattr(siteicons.socket, "getaddrinfo",
                        fake_dns({"dual.example": ["2606:2800:21f:cb07:6820:80da:af6b:8b2c", "93.184.215.14"]}))
    assert siteicons.public_ips("dual.example")[0] == "93.184.215.14"


def test_tls_context_verifies_hostnames():
    ctx = siteicons.tls_context()
    assert ctx.verify_mode == siteicons.ssl.CERT_REQUIRED and ctx.check_hostname
