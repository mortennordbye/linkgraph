"""Opt-in company logos.

Nothing here runs unless the user presses "Fetch logos" (or saves a domain by hand). Then the
server, never the browser, does this per company:

1. Find a website domain: a manual override from the notes file, else the Norwegian business
   register (data.brreg.no), else Wikidata. Both are open APIs with no key.
2. Download the favicon for that domain from DuckDuckGo's icon service.
3. Cache the image in logo-cache/ so the page loads it from 127.0.0.1.

Only company names and domains leave the machine. People never do. The only hosts contacted
are the three fixed ones below, so no data from the export can steer a request elsewhere.
"""

from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from . import normalize as N
from .notes import save as save_json

BRREG_URL = "https://data.brreg.no/enhetsregisteret/api/enheter?navn={q}&size=10"
WIKIDATA_SEARCH = ("https://www.wikidata.org/w/api.php?action=wbsearchentities&search={q}"
                   "&language=en&type=item&limit=5&format=json")
WIKIDATA_ENTITIES = "https://www.wikidata.org/w/api.php?action=wbgetentities&ids={ids}&props=claims&format=json"
ICON_URL = "https://icons.duckduckgo.com/ip3/{domain}.ico"

USER_AGENT = "LinkGraph/0.1 (local LinkedIn export viewer)"
TIMEOUT = 8
MAX_BYTES = 256 * 1024
WORKERS = 4

# Websites in registries that are not the company's own site.
SOCIAL_HOSTS = ("facebook.com", "linkedin.com", "instagram.com", "twitter.com", "x.com",
                "youtube.com", "tiktok.com", "google.com", "sites.google.com", "wix.com")

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")

# (status, content_type, body). Injected in tests so they never touch the network.
HttpGet = Callable[[str], tuple[int, str, bytes]]


def http_get(url: str) -> tuple[int, str, bytes]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:  # noqa: S310 - fixed https hosts only
            body = r.read(MAX_BYTES + 1)
            return r.status, r.headers.get("Content-Type", ""), body
    except urllib.error.HTTPError as e:
        return e.code, "", b""
    except (urllib.error.URLError, TimeoutError, OSError):
        return 0, "", b""


def clean_domain(value: str | None) -> str | None:
    """'https://www.Acme.no/about' -> 'acme.no'. Returns None for anything not a public hostname."""
    if not value:
        return None
    v = value.strip().lower()
    if "://" not in v:
        v = "https://" + v
    host = urllib.parse.urlsplit(v).hostname or ""
    host = host.removeprefix("www.")
    if not _HOST_RE.match(host):
        return None
    if any(host == s or host.endswith("." + s) for s in SOCIAL_HOSTS):
        return None
    return host


_SNIFF = (
    (b"\x89PNG\r\n\x1a\n", "png", "image/png"),
    (b"\x00\x00\x01\x00", "ico", "image/x-icon"),
    (b"GIF8", "gif", "image/gif"),
    (b"\xff\xd8\xff", "jpg", "image/jpeg"),
)


MIN_SIDE = 16


def _too_small(ext: str, body: bytes) -> bool:
    """Icon services answer a miss with a 1x1 placeholder. Read the size from the header."""
    if ext == "png" and len(body) >= 24:
        w, h = int.from_bytes(body[16:20], "big"), int.from_bytes(body[20:24], "big")
    elif ext == "gif" and len(body) >= 10:
        w, h = int.from_bytes(body[6:8], "little"), int.from_bytes(body[8:10], "little")
    elif ext == "ico" and len(body) >= 8:
        w, h = body[6] or 256, body[7] or 256  # 0 means 256 in the ICO directory
    else:
        return False
    return min(w, h) < MIN_SIDE


def sniff_image(body: bytes) -> tuple[str, str] | None:
    """Accept raster formats only, by magic bytes. SVG is refused: it can carry script."""
    if not body or len(body) > MAX_BYTES:
        return None
    for magic, ext, mime in _SNIFF:
        if body.startswith(magic):
            return None if _too_small(ext, body) else (ext, mime)
    if body[:4] == b"RIFF" and body[8:12] == b"WEBP":
        return "webp", "image/webp"
    return None


def _json(get: HttpGet, url: str) -> dict | None:
    status, _, body = get(url)
    if status != 200 or not body:
        return None
    try:
        return json.loads(body)
    except ValueError:
        return None


def domain_from_brreg(get: HttpGet, key: str, name: str) -> str | None:
    """Norwegian business register. Only an entity whose name has the same company key counts,
    so 'Equinor' never picks 'Equinor Pensjon'."""
    data = _json(get, BRREG_URL.format(q=urllib.parse.quote(name)))
    for e in ((data or {}).get("_embedded") or {}).get("enheter", []):
        if N.company_key(e.get("navn", "")) == key:
            d = clean_domain(e.get("hjemmeside"))
            if d:
                return d
    return None


def domain_from_wikidata(get: HttpGet, key: str, name: str) -> str | None:
    """Wikidata 'official website' (P856). Only items whose label has the same company key
    count; text search alone matches 'DNB' to a German library."""
    data = _json(get, WIKIDATA_SEARCH.format(q=urllib.parse.quote(name)))
    ids = [h["id"] for h in (data or {}).get("search", [])
           if N.company_key(h.get("label", "")) == key and re.fullmatch(r"Q\d+", h.get("id", ""))]
    if not ids:
        return None
    ents = (_json(get, WIKIDATA_ENTITIES.format(ids="|".join(ids))) or {}).get("entities", {})
    for qid in ids:
        for claim in ents.get(qid, {}).get("claims", {}).get("P856", []):
            value = claim.get("mainsnak", {}).get("datavalue", {}).get("value")
            d = clean_domain(value if isinstance(value, str) else None)
            if d:
                return d
    return None


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class LogoStore:
    """Logo cache on disk plus the background fetch job."""

    FILE_RE = re.compile(r"^[0-9a-f]{40}\.(png|ico|gif|jpg|webp)$")
    MIME = {"png": "image/png", "ico": "image/x-icon", "gif": "image/gif", "jpg": "image/jpeg",
            "webp": "image/webp"}

    def __init__(self, cache_dir: Path, get: HttpGet = http_get):
        self.dir = cache_dir
        self.index_path = cache_dir / "index.json"
        self.get = get
        self._lock = threading.Lock()
        self._job_lock = threading.Lock()
        self.job = {"running": False, "done": 0, "total": 0, "found": 0, "started_at": None,
                    "finished_at": None}
        try:
            self.index: dict[str, dict] = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.index = {}

    # ---- reading ---------------------------------------------------------------
    def urls(self) -> dict[str, str]:
        """company key -> local URL, for every cached logo."""
        with self._lock:
            return {k: f"/logos/{v['file']}?v={v['updated']}" for k, v in self.index.items()
                    if v.get("file") and (self.dir / v["file"]).is_file()}

    def info(self) -> dict[str, dict]:
        with self._lock:
            return {k: {"domain": v.get("domain"), "source": v.get("source"), "status": v.get("status")}
                    for k, v in self.index.items()}

    def file_for(self, name: str) -> tuple[Path, str] | None:
        if not self.FILE_RE.match(name):
            return None
        p = self.dir / name
        return (p, self.MIME[name.rsplit(".", 1)[1]]) if p.is_file() else None

    # ---- fetching --------------------------------------------------------------
    def fetch_one(self, key: str, name: str, override: str | None = None) -> dict:
        """Resolve a domain and download its icon. Records misses so the next run skips them."""
        source, domain = None, None
        if override:
            source, domain = "manual", clean_domain(override)
        if not domain:
            domain = domain_from_brreg(self.get, key, name)
            source = "brreg" if domain else None
        if not domain:
            domain = domain_from_wikidata(self.get, key, name)
            source = "wikidata" if domain else None
        entry = {"domain": domain, "source": source, "updated": _now(), "file": None,
                 "status": "no_domain"}
        if domain:
            status, _, body = self.get(ICON_URL.format(domain=domain))
            kind = sniff_image(body) if status == 200 else None
            if kind:
                fname = hashlib.sha1(key.encode("utf-8")).hexdigest() + "." + kind[0]
                self.dir.mkdir(parents=True, exist_ok=True)
                (self.dir / fname).write_bytes(body)
                entry.update(file=fname, status="ok")
            else:
                entry["status"] = "no_icon"
        with self._lock:
            old = self.index.get(key, {}).get("file")
            if old and old != entry["file"]:
                (self.dir / old).unlink(missing_ok=True)
            self.index[key] = entry
            self.dir.mkdir(parents=True, exist_ok=True)
            save_json(self.index_path, self.index)
        return entry

    def start(self, companies: list[tuple[str, str]], overrides: dict[str, str],
              retry_missing: bool = False) -> bool:
        """Fetch logos for (key, name) pairs in a background thread. False if a job is running."""
        with self._job_lock:
            if self.job["running"]:
                return False
            with self._lock:
                todo = [(k, n) for k, n in companies if self._needs_fetch(k, overrides, retry_missing)]
            self.job = {"running": True, "done": 0, "total": len(todo), "found": 0,
                        "started_at": _now(), "finished_at": None}

        def run() -> None:
            def one(item: tuple[str, str]) -> None:
                k, n = item
                try:
                    e = self.fetch_one(k, n, overrides.get(k))
                    found = e["status"] == "ok"
                except Exception:  # one bad company must not stop the job
                    found = False
                with self._job_lock:
                    self.job["done"] += 1
                    self.job["found"] += int(found)

            with ThreadPoolExecutor(max_workers=WORKERS) as pool:
                list(pool.map(one, todo))
            with self._job_lock:
                self.job.update(running=False, finished_at=_now())

        threading.Thread(target=run, name="logo-fetch", daemon=True).start()
        return True

    def _needs_fetch(self, key: str, overrides: dict[str, str], retry_missing: bool) -> bool:
        entry = self.index.get(key)
        if entry is None:
            return True
        if key in overrides and entry.get("domain") != clean_domain(overrides[key]):
            return True  # the user changed the domain since the last fetch
        return retry_missing and entry.get("status") != "ok"

    def status(self) -> dict:
        with self._job_lock:
            return dict(self.job)
