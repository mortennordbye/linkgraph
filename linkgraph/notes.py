"""Lead status and notes, stored in linkgraph-notes.json."""

from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path

STATUSES = ("Target", "Reached Out", "Warm Intro", "Ignore")
KINDS = ("person", "company")
_lock = threading.Lock()


def empty() -> dict:
    return {"version": 1, "person": {}, "company": {}, "aliases": {}, "domains": {}}


def load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return empty()
    except (OSError, json.JSONDecodeError):
        # Keep a copy of a broken file so nothing is lost, then start fresh.
        if path.exists():
            path.replace(path.with_suffix(".broken.json"))
        return empty()
    base = empty()
    base.update({k: v for k, v in data.items() if k in base})
    return base


def save(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".linkgraph-notes-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def set_entry(path: Path, kind: str, key: str, status: str | None, note: str | None,
              label: str | None = None) -> dict:
    if kind not in KINDS:
        raise ValueError(f"kind must be one of {KINDS}")
    if status and status not in STATUSES:
        raise ValueError(f"status must be one of {STATUSES}")
    with _lock:
        data = load(path)
        bucket = data[kind]
        entry = dict(bucket.get(key, {}))
        entry["status"] = status or None
        if note is not None:
            entry["note"] = note
        if label:
            entry["label"] = label
        entry["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if not entry.get("status") and not entry.get("note"):
            bucket.pop(key, None)
            entry = {}
        else:
            bucket[key] = entry
        save(path, data)
        return entry


def set_alias(path: Path, from_key: str, to_key: str | None) -> dict:
    """Merge company from_key into to_key. to_key None or empty removes the merge."""
    with _lock:
        data = load(path)
        aliases = data["aliases"]
        if not to_key:
            aliases.pop(from_key, None)
        else:
            if from_key == to_key:
                raise ValueError("cannot merge a company into itself")
            # Reject cycles: to_key must not resolve back to from_key.
            k, seen = to_key, set()
            while k in aliases and k not in seen:
                seen.add(k)
                k = aliases[k]
            if k == from_key:
                raise ValueError("merge would create a cycle")
            aliases[from_key] = to_key
            # Carry a status or note over so it does not disappear with the merged key.
            moved = data["company"].pop(from_key, None)
            if moved and to_key not in data["company"]:
                data["company"][to_key] = moved
        save(path, data)
        return aliases


def set_domain(path: Path, key: str, domain: str | None) -> dict:
    """Manual website domain for a company's logo. None removes the override."""
    with _lock:
        data = load(path)
        if domain:
            data["domains"][key] = domain
        else:
            data["domains"].pop(key, None)
        save(path, data)
        return data["domains"]
