"""Find LinkedIn exports and read files from a folder or a zip the same way."""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from pathlib import Path

DEFAULT_DIR = Path(os.environ.get("LINKGRAPH_DOWNLOADS", Path.home() / "Downloads"))
MARKER = "connections.csv"


@dataclass
class Candidate:
    path: str
    kind: str  # "folder" | "zip"
    name: str
    mtime: float
    size: int

    def to_dict(self) -> dict:
        return {"path": self.path, "kind": self.kind, "name": self.name,
                "mtime": self.mtime, "size": self.size}


def _folder_has_marker(p: Path) -> bool:
    try:
        return any(c.name.casefold() == MARKER for c in p.iterdir() if c.is_file())
    except OSError:
        return False


def _zip_has_marker(p: Path) -> bool:
    try:
        with zipfile.ZipFile(p) as zf:
            return any(Path(n).name.casefold() == MARKER for n in zf.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def confine(path: str, roots: list[Path]) -> str | None:
    """Resolve a user-supplied path and return it only if it lies inside one of the roots."""
    real = os.path.realpath(os.path.expanduser(path))
    for root in roots:
        base = os.path.realpath(root)
        if real == base or real.startswith(base.rstrip(os.sep) + os.sep):
            return real
    return None


def inspect(path: str | Path) -> Candidate | None:
    """Return a Candidate if the path is a usable export. A directory wins over a .zip name."""
    p = Path(path).expanduser()
    if not p.exists():
        return None
    st = p.stat()
    if p.is_dir():
        if _folder_has_marker(p):
            return Candidate(str(p), "folder", p.name, st.st_mtime, 0)
        # One level down: e.g. an unzipped folder holding a single export folder.
        for c in sorted(p.iterdir()):
            if c.is_dir() and _folder_has_marker(c):
                return Candidate(str(c), "folder", c.name, c.stat().st_mtime, 0)
        return None
    if p.is_file() and zipfile.is_zipfile(p) and _zip_has_marker(p):
        return Candidate(str(p), "zip", p.name, st.st_mtime, st.st_size)
    return None


def discover(base: Path = DEFAULT_DIR) -> list[Candidate]:
    """Find LinkedIn exports in base, newest first."""
    out: list[Candidate] = []
    if not base.is_dir():
        return out
    for entry in base.iterdir():
        if "linkedin" not in entry.name.casefold():
            continue
        c = inspect(entry)
        if c:
            out.append(c)
    out.sort(key=lambda c: c.mtime, reverse=True)
    return out


class ExportReader:
    """Read CSV text from a folder or zip. Zips are read in memory, never extracted."""

    def __init__(self, path: str):
        cand = inspect(path)
        if cand is None:
            raise FileNotFoundError(f"No LinkedIn export (Connections.csv) found at {path}")
        self.candidate = cand
        self._files: dict[str, str] = {}  # casefolded basename -> member path
        if cand.kind == "folder":
            root = Path(cand.path)
            for f in root.rglob("*.csv"):
                self._files.setdefault(f.name.casefold(), str(f))
        else:
            with zipfile.ZipFile(cand.path) as zf:
                for n in zf.namelist():
                    if n.casefold().endswith(".csv"):
                        self._files.setdefault(Path(n).name.casefold(), n)

    def has(self, name: str) -> bool:
        return name.casefold() in self._files

    def read_text(self, name: str) -> str | None:
        member = self._files.get(name.casefold())
        if member is None:
            return None
        if self.candidate.kind == "folder":
            raw = Path(member).read_bytes()
        else:
            with zipfile.ZipFile(self.candidate.path) as zf:
                raw = zf.read(member)
        return raw.decode("utf-8-sig", errors="replace")
