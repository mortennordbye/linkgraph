"""Local FastAPI server. Binds to 127.0.0.1 only."""

from __future__ import annotations

import argparse
import io
import os
import re
import tempfile
import threading
import time
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import notes as notes_mod
from . import parser, sources
from .logos import HttpGet, LogoStore, clean_domain, http_get

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
# Notes and the logo cache. The repo folder on a laptop, a volume in a container.
DATA_DIR = Path(os.environ.get("LINKGRAPH_DATA_DIR", ROOT))
IMPORT_LIMIT = 200 * 1024 * 1024
IMPORT_NAME_RE = re.compile(r"^[\w.\- ]+\.zip$")


class State:
    def __init__(self, notes_path: Path, downloads: Path):
        self.notes_path = notes_path
        self.downloads = downloads
        self.dataset: dict | None = None
        self.error: str | None = None
        self.lock = threading.Lock()

    def load(self, path: str) -> dict:
        with self.lock:
            self.dataset = parser.load(path)
            self.error = None
            return self.dataset


class SourceIn(BaseModel):
    path: str


class DomainIn(BaseModel):
    domain: str | None = None


class LogoFetchIn(BaseModel):
    retry_missing: bool = False


class AliasIn(BaseModel):
    to: str | None = None


class NoteIn(BaseModel):
    status: str | None = None
    note: str | None = None
    label: str | None = None


# The API has no login: it trusts that only this machine can reach 127.0.0.1. A Host-header
# allowlist stops DNS rebinding, where a web page points its own hostname at 127.0.0.1 to read
# your data from the browser. "testserver" is the Host header FastAPI's TestClient sends.
# LINKGRAPH_ALLOWED_HOSTS adds the hostname a reverse proxy serves the app on (comma separated).
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"] + [
    h.strip() for h in os.environ.get("LINKGRAPH_ALLOWED_HOSTS", "").split(",") if h.strip()]


def create_app(notes_path: Path | None = None, downloads: Path | None = None,
               initial_source: str | None = None, logo_dir: Path | None = None,
               logo_http: HttpGet = http_get, logo_site=None) -> FastAPI:
    state = State(notes_path or DATA_DIR / "linkgraph-notes.json",
                  downloads or sources.DEFAULT_DIR)
    logo_store = LogoStore(logo_dir or DATA_DIR / "logo-cache", logo_http, logo_site)
    app = FastAPI(title="LinkGraph", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS)

    @app.middleware("http")
    async def no_cache(request, call_next):
        # Always revalidate, so the browser never runs stale app code or data.
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache"
        return response

    def _ensure_loaded() -> dict:
        if state.dataset is None:
            cands = sources.discover(state.downloads)
            target = initial_source or (cands[0].path if cands else None)
            if not target:
                raise HTTPException(404, f"No LinkedIn export found in {state.downloads}. "
                                         "Pick a folder or zip in the source menu.")
            try:
                state.load(target)
            except FileNotFoundError as e:
                raise HTTPException(404, str(e)) from e
        return state.dataset

    @app.get("/api/sources")
    def get_sources():
        cands = [c.to_dict() for c in sources.discover(state.downloads)]
        active = state.dataset["source"]["path"] if state.dataset else None
        if active is None and cands:
            active = initial_source or cands[0]["path"]
        return {"downloads": str(state.downloads), "candidates": cands, "active": active}

    @app.post("/api/source")
    def set_source(body: SourceIn):
        # Exports live under your home folder; refuse anything else (e.g. /etc, other users).
        path = sources.confine(body.path, [Path.home(), state.downloads])
        if path is None:
            raise HTTPException(400, "Pick an export inside your home folder.")
        try:
            ds = state.load(path)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        return {"ok": True, "source": ds["source"], "stats": ds["stats"]}

    @app.post("/api/import")
    async def import_export(request: Request, name: str = ""):
        # A raw zip body, not a form: a cross-site form cannot send application/zip without a
        # CORS preflight, and the server answers none, so a hostile page cannot upload.
        if request.headers.get("content-type") != "application/zip":
            raise HTTPException(415, "Send the export as application/zip.")
        body = bytearray()
        async for chunk in request.stream():
            body += chunk
            if len(body) > IMPORT_LIMIT:
                raise HTTPException(413, "The zip is larger than 200 MB.")
        if not sources.zip_has_marker(io.BytesIO(body)):
            raise HTTPException(400, "This is not a LinkedIn export: no Connections.csv inside.")
        # discover() lists only names with "linkedin" in them; keep the user's name when it fits.
        base = Path(name).name
        if not (IMPORT_NAME_RE.match(base) and "linkedin" in base.casefold()):
            base = time.strftime("LinkedInDataExport_import-%Y%m%d-%H%M%S.zip")
        state.downloads.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(prefix=".import-", suffix=".zip", dir=state.downloads)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(body)
            target = state.downloads / base
            os.replace(tmp, target)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        ds = state.load(str(target))
        return {"ok": True, "source": ds["source"], "stats": ds["stats"]}

    @app.get("/api/data")
    def get_data():
        ds = _ensure_loaded()
        notes = notes_mod.load(state.notes_path)
        people, companies = parser.group_companies(ds["people"], ds["me"]["employer_keys"],
                                                    notes["aliases"])
        stats = dict(ds["stats"], companies=len(companies))
        return {
            "source": ds["source"], "me": ds["me"], "stats": stats,
            "people": people, "companies": companies,
            "notes": notes, "statuses": notes_mod.STATUSES,
            "logos": logo_store.urls(), "logo_info": logo_store.info(),
        }

    def _companies() -> list[dict]:
        ds = _ensure_loaded()
        aliases = notes_mod.load(state.notes_path)["aliases"]
        return parser.group_companies(ds["people"], ds["me"]["employer_keys"], aliases)[1]

    # ---- logos: the only code path that calls the internet, and only on request ----
    @app.post("/api/logos/fetch")
    def fetch_logos(body: LogoFetchIn):
        companies = [(c["key"], c["name"]) for c in _companies() if not c["is_generic"]]
        domains = notes_mod.load(state.notes_path)["domains"]
        started = logo_store.start(companies, domains, retry_missing=body.retry_missing)
        return {"started": started, **logo_store.status()}

    @app.get("/api/logos/status")
    def logos_status():
        return logo_store.status()

    @app.put("/api/domains/{key:path}")
    def put_domain(key: str, body: DomainIn):
        company = next((c for c in _companies() if c["key"] == key), None)
        if company is None:
            raise HTTPException(404, "unknown company")
        domain = clean_domain(body.domain) if body.domain else None
        if body.domain and not domain:
            raise HTTPException(400, "not a valid public domain, e.g. acme.no")
        notes_mod.set_domain(state.notes_path, key, domain)
        entry = logo_store.fetch_one(key, company["name"], domain) if domain else None
        return {"key": key, "domain": domain, "entry": entry, "url": logo_store.urls().get(key)}

    @app.get("/logos/{name}")
    def logo_file(name: str):
        found = logo_store.file_for(name)
        if not found:
            raise HTTPException(404, "no such logo")
        path, mime = found
        return FileResponse(path, media_type=mime, headers={"X-Content-Type-Options": "nosniff"})

    @app.get("/api/people/{pid}/messages")
    def get_messages(pid: str):
        ds = _ensure_loaded()
        return {"id": pid, "messages": ds["messages_by_person"].get(pid, [])}

    @app.get("/api/notes")
    def get_notes():
        return notes_mod.load(state.notes_path)

    @app.put("/api/notes/{kind}/{key:path}")
    def put_note(kind: str, key: str, body: NoteIn):
        try:
            entry = notes_mod.set_entry(state.notes_path, kind, key, body.status, body.note,
                                        body.label)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"kind": kind, "key": key, "entry": entry}

    @app.put("/api/aliases/{from_key:path}")
    def put_alias(from_key: str, body: AliasIn):
        try:
            aliases = notes_mod.set_alias(state.notes_path, from_key, body.to)
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        return {"aliases": aliases}

    @app.get("/")
    def index():
        return FileResponse(STATIC / "index.html")

    app.mount("/static", StaticFiles(directory=STATIC), name="static")
    return app


def main() -> None:
    ap = argparse.ArgumentParser(description="LinkGraph: local LinkedIn network explorer")
    ap.add_argument("--port", type=int, default=int(os.environ.get("LINKGRAPH_PORT", 8765)))
    ap.add_argument("--source", help="Path to an export folder or zip (default: newest in ~/Downloads)")
    ap.add_argument("--host", default=os.environ.get("LINKGRAPH_HOST", "127.0.0.1"),
                    help="Bind address. Keep 127.0.0.1 unless a private proxy is in front.")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    import uvicorn

    app = create_app(initial_source=args.source)
    cands = sources.discover()
    print(f"LinkGraph: found {len(cands)} export(s) in {sources.DEFAULT_DIR}")
    for c in cands:
        print(f"  - {c.name} ({c.kind})")
    url = f"http://127.0.0.1:{args.port}/"
    if not args.no_browser:
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    print(f"LinkGraph: open {url}  (Ctrl+C to stop)")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
