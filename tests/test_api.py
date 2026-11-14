import json

from fastapi.testclient import TestClient

from linkgraph.server import create_app


def _no_network(url):
    raise AssertionError(f"unexpected network call: {url}")


def _client(tmp_path, export_folder):
    notes = tmp_path / "linkgraph-notes.json"
    app = create_app(notes_path=notes, downloads=export_folder.parent, logo_dir=tmp_path / "logos",
                     logo_http=_no_network)
    return TestClient(app), notes


def test_data_and_notes_roundtrip(tmp_path, export_folder, export_zip):
    client, notes = _client(tmp_path, export_folder)
    src = client.get("/api/sources").json()
    assert len(src["candidates"]) == 2

    d = client.get("/api/data").json()
    assert d["stats"]["connections"] == 6
    assert "messages_by_person" not in d

    m = client.get("/api/people/ada-l/messages").json()
    assert len(m["messages"]) == 3

    r = client.put("/api/notes/person/ada-l", json={"status": "Warm Intro", "note": "met at conf", "label": "Ada"})
    assert r.status_code == 200
    r = client.put("/api/notes/company/acme", json={"status": "Target"})
    assert r.status_code == 200
    saved = json.loads(notes.read_text())
    assert saved["person"]["ada-l"]["status"] == "Warm Intro"
    assert saved["company"]["acme"]["status"] == "Target"
    assert client.get("/api/data").json()["notes"]["person"]["ada-l"]["note"] == "met at conf"

    # Clearing status and note removes the entry.
    client.put("/api/notes/company/acme", json={"status": None, "note": ""})
    assert "acme" not in json.loads(notes.read_text())["company"]

    assert client.put("/api/notes/person/x", json={"status": "Bogus"}).status_code == 400
    assert client.put("/api/notes/robot/x", json={"status": "Target"}).status_code == 400
    assert not list(tmp_path.glob(".linkgraph-notes-*"))  # no temp files left behind


def test_switch_source(tmp_path, export_folder, export_zip):
    client, _ = _client(tmp_path, export_folder)
    r = client.post("/api/source", json={"path": str(export_zip)})
    assert r.status_code == 200 and r.json()["source"]["kind"] == "zip"
    assert client.post("/api/source", json={"path": str(tmp_path / "nope")}).status_code == 404


def test_static_served(tmp_path, export_folder):
    client, _ = _client(tmp_path, export_folder)
    assert "LinkGraph" in client.get("/").text
    assert client.get("/static/vendor/force-graph.min.js").status_code == 200


def test_merge_aliases(tmp_path, export_folder):
    client, notes = _client(tmp_path, export_folder)
    keys = {c["key"]: c for c in client.get("/api/data").json()["companies"]}
    assert keys["globex"]["count"] == 1 and keys["acme"]["count"] == 3

    assert client.put("/api/aliases/globex", json={"to": "acme"}).status_code == 200
    d = client.get("/api/data").json()
    keys = {c["key"]: c for c in d["companies"]}
    assert "globex" not in keys
    assert keys["acme"]["count"] == 4 and keys["acme"]["merged_keys"] == ["globex"]
    assert keys["acme"]["is_employer"] is True  # Globex was an employer
    assert keys["acme"]["name"] != "Globex Inc."
    dag = next(p for p in d["people"] if p["id"] == "dag-h")
    assert dag["company_key"] == "acme" and dag["raw_company_key"] == "globex"

    # Cycles and self-merges are rejected.
    assert client.put("/api/aliases/acme", json={"to": "globex"}).status_code == 400
    assert client.put("/api/aliases/acme", json={"to": "acme"}).status_code == 400

    client.put("/api/aliases/globex", json={"to": None})
    assert "globex" in {c["key"] for c in client.get("/api/data").json()["companies"]}


def test_merge_moves_company_note(tmp_path, export_folder):
    client, notes = _client(tmp_path, export_folder)
    client.put("/api/notes/company/globex", json={"status": "Target", "note": "intro via Dag"})
    client.put("/api/aliases/globex", json={"to": "acme"})
    saved = json.loads(notes.read_text())
    assert "globex" not in saved["company"]
    assert saved["company"]["acme"]["note"] == "intro via Dag"


def test_rejects_foreign_host_header(tmp_path, export_folder):
    # DNS rebinding: a page on evil.example resolves its name to 127.0.0.1 and calls the API.
    client, _ = _client(tmp_path, export_folder)
    assert client.get("/api/data", headers={"Host": "evil.example"}).status_code == 400
    assert client.get("/api/data", headers={"Host": "127.0.0.1:8765"}).status_code == 200
    assert client.get("/api/data", headers={"Host": "localhost:8765"}).status_code == 200


def test_put_rejects_non_json_body(tmp_path, export_folder):
    # A cross-site form can only send text/plain or form bodies without a CORS preflight.
    client, notes = _client(tmp_path, export_folder)
    r = client.put("/api/notes/person/ada-l", content='{"status": "Ignore"}',
                   headers={"Content-Type": "text/plain"})
    assert r.status_code == 422
    assert not notes.exists()
