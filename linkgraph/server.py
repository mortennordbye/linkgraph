"""Local FastAPI server. Binds to 127.0.0.1 only."""

from __future__ import annotations

import argparse
import os
import threading
import webbrowser
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.trustedhost import TrustedHostMiddleware

from . import notes as notes_mod
from . import parser, sources

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"


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


class AliasIn(BaseModel):
    to: str | None = None


class NoteIn(BaseModel):
    status: str | None = None
    note: str | None = None
    label: str | None = None


# The API has no login: it trusts that only this machine can reach 127.0.0.1. A Host-header
# allowlist stops DNS rebinding, where a web page points its own hostname at 127.0.0.1 to read
# your data from the browser. "testserver" is the Host header FastAPI's TestClient sends.
ALLOWED_HOSTS = ["127.0.0.1", "localhost", "testserver"]


def create_app(notes_path: Path | None = None, downloads: Path | None = None,
               initial_source: str | None = None) -> FastAPI:
    state = State(notes_path or ROOT / "linkgraph-notes.json",
                  downloads or sources.DEFAULT_DIR)
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
        try:
            ds = state.load(body.path)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
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
        }

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
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
