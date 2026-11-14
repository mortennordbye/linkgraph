import json
import time
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient

from linkgraph import logos
from linkgraph.server import create_app


def png(w, h):
    return b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\x0dIHDR" + w.to_bytes(4, "big") + h.to_bytes(4, "big") + b"\x00" * 40


PNG = png(32, 32)
ICO = b"\x00\x00\x01\x00\x01\x00" + bytes([32, 32]) + b"\x00" * 64


class FakeWeb:
    """Answers for the three allowed hosts only. Any other host fails the test."""

    def __init__(self, brreg=None, wikidata=None, icons=None):
        self.brreg = brreg or {}        # query -> list of {navn, hjemmeside}
        self.wikidata = wikidata or {}  # query -> list of (qid, label, website)
        self.icons = icons or {}        # domain -> bytes
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        u = urlsplit(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        if u.hostname == "data.brreg.no":
            ents = self.brreg.get(q["navn"], [])
            return 200, "application/json", json.dumps({"_embedded": {"enheter": ents}}).encode()
        if u.hostname == "www.wikidata.org" and q["action"] == "wbsearchentities":
            hits = [{"id": i, "label": label} for i, label, _ in self.wikidata.get(q["search"], [])]
            return 200, "application/json", json.dumps({"search": hits}).encode()
        if u.hostname == "www.wikidata.org" and q["action"] == "wbgetentities":
            sites = {i: w for hits in self.wikidata.values() for i, _, w in hits}
            ents = {i: {"claims": {"P856": [{"mainsnak": {"datavalue": {"value": sites[i]}}}]}}
                    for i in q["ids"].split("|")}
            return 200, "application/json", json.dumps({"entities": ents}).encode()
        if u.hostname == "icons.duckduckgo.com":
            domain = u.path.removeprefix("/ip3/").removesuffix(".ico")
            body = self.icons.get(domain)
            return (200, "image/x-icon", body) if body else (404, "", b"")
        raise AssertionError(f"request to a host outside the allowlist: {url}")


@pytest.mark.parametrize("raw,clean", [
    ("www.Equinor.com", "equinor.com"), ("https://www.dnb.no/en/about", "dnb.no"),
    ("acme.no", "acme.no"), ("nb-no.facebook.com/acme", None), ("linkedin.com/company/x", None),
    ("localhost", None), ("10.0.0.1", None), ("not a domain", None), ("", None), (None, None),
])
def test_clean_domain(raw, clean):
    assert logos.clean_domain(raw) == clean


def test_sniff_rejects_svg_html_and_oversize():
    assert logos.sniff_image(PNG) == ("png", "image/png")
    assert logos.sniff_image(ICO) == ("ico", "image/x-icon")
    assert logos.sniff_image(b"<svg onload=alert(1)>") is None
    assert logos.sniff_image(b"<!doctype html>") is None
    assert logos.sniff_image(PNG + b"\x00" * logos.MAX_BYTES) is None


def test_sniff_rejects_placeholder_pixels():
    one_px_gif = b"GIF89a\x01\x00\x01\x00" + b"\x00" * 30
    assert logos.sniff_image(one_px_gif) is None
    assert logos.sniff_image(png(1, 1)) is None
    assert logos.sniff_image(b"\x00\x00\x01\x00\x01\x00\x08\x08" + b"\x00" * 30) is None
    assert logos.sniff_image(b"\x00\x00\x01\x00\x01\x00\x00\x00" + b"\x00" * 30) == ("ico", "image/x-icon")
    # DuckDuckGo sends its miss placeholder as data-URI text.
    assert logos.sniff_image(b"data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7") is None


def test_brreg_needs_same_company_key():
    web = FakeWeb(brreg={"Equinor": [
        {"navn": "EQUINOR PENSJON", "hjemmeside": "www.equinorpensjon.no"},
        {"navn": "EQUINOR ASA", "hjemmeside": "www.equinor.com"}]})
    assert logos.domain_from_brreg(web, "equinor", "Equinor") == "equinor.com"
    web = FakeWeb(brreg={"Acme": [{"navn": "ACME PENSJON", "hjemmeside": "acmepensjon.no"}]})
    assert logos.domain_from_brreg(web, "acme", "Acme") is None


def test_wikidata_needs_same_label():
    web = FakeWeb(wikidata={"DNB": [("Q1", "German National Library", "https://www.dnb.de")]})
    assert logos.domain_from_wikidata(web, "dnb", "DNB") is None
    web = FakeWeb(wikidata={"Globex": [("Q2", "Globex", "https://www.globex.com/")]})
    assert logos.domain_from_wikidata(web, "globex", "Globex") == "globex.com"


def test_store_fetch_cache_and_misses(tmp_path):
    web = FakeWeb(brreg={"Acme AS": [{"navn": "Acme AS", "hjemmeside": "www.acme.no"}]},
                  icons={"acme.no": PNG})
    store = logos.LogoStore(tmp_path, web)
    assert store.fetch_one("acme", "Acme AS")["status"] == "ok"
    assert store.fetch_one("nobody", "Nobody")["status"] == "no_domain"
    url = store.urls()["acme"]
    name = url.split("/")[-1].split("?")[0]
    path, mime = store.file_for(name)
    assert path.read_bytes() == PNG and mime == "image/png"
    assert store.file_for("../index.json") is None
    assert store.file_for("index.json") is None
    # A well-formed name that the store never wrote is not served, even if the file exists.
    stray = "0" * 40 + ".png"
    (tmp_path / stray).write_bytes(PNG)
    assert store.file_for(stray) is None
    # A new store reads the same cache back.
    assert "acme" in logos.LogoStore(tmp_path, web).urls()


def _wait(store):
    for _ in range(200):
        if not store.status()["running"]:
            return store.status()
        time.sleep(0.01)
    raise AssertionError("logo job did not finish")


def test_job_skips_cached_and_retries_on_request(tmp_path):
    web = FakeWeb(brreg={"Acme AS": [{"navn": "Acme AS", "hjemmeside": "acme.no"}]},
                  icons={"acme.no": PNG})
    store = logos.LogoStore(tmp_path, web)
    companies = [("acme", "Acme AS"), ("nobody", "Nobody")]
    assert store.start(companies, {})
    assert _wait(store)["found"] == 1
    n = len(web.calls)
    store.start(companies, {})
    assert _wait(store)["total"] == 0 and len(web.calls) == n   # nothing new to fetch
    store.start(companies, {}, retry_missing=True)
    assert _wait(store)["total"] == 1                             # only the miss
    store.start(companies, {"nobody": "nobody.no"})
    assert _wait(store)["total"] == 1                             # override changed


def test_api_logo_flow(tmp_path, export_folder):
    web = FakeWeb(brreg={"Acme": [{"navn": "ACME AS", "hjemmeside": "www.acme.no"}]},
                  icons={"acme.no": PNG, "globex.example": ICO})
    app = create_app(notes_path=tmp_path / "notes.json", downloads=export_folder.parent,
                     logo_dir=tmp_path / "logos", logo_http=web)
    client = TestClient(app)

    # Loading data never touches the network.
    d = client.get("/api/data").json()
    assert d["logos"] == {} and web.calls == []

    r = client.post("/api/logos/fetch", json={})
    assert r.status_code == 200 and r.json()["started"] is True
    for _ in range(200):
        if not client.get("/api/logos/status").json()["running"]:
            break
        time.sleep(0.01)
    d = client.get("/api/data").json()
    assert set(d["logos"]) == {"acme"}
    assert d["logo_info"]["acme"]["source"] == "brreg"
    assert not any("self" in c.lower() for c in web.calls)  # "Self-employed" is never looked up

    img = client.get(d["logos"]["acme"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"
    assert img.headers["x-content-type-options"] == "nosniff"

    # Manual domain override fetches that one company right away.
    r = client.put("/api/domains/globex", json={"domain": "https://www.globex.example/"})
    assert r.status_code == 200 and r.json()["domain"] == "globex.example"
    assert r.json()["entry"]["source"] == "manual" and r.json()["url"]
    assert json.loads((tmp_path / "notes.json").read_text())["domains"] == {"globex": "globex.example"}

    assert client.put("/api/domains/globex", json={"domain": "localhost"}).status_code == 400
    assert client.put("/api/domains/nope", json={"domain": "acme.no"}).status_code == 404
    assert client.get("/logos/..%2Fnotes.json").status_code == 404
