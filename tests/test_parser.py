from linkgraph import parser, sources
from linkgraph.parser import parse_date

from .conftest import NOW


def test_parse_date_formats():
    assert parse_date("13 Nov 2026").date().isoformat() == "2026-11-13"
    assert parse_date("2026-11-12 09:21:06 UTC").hour == 9
    assert parse_date("11/13/26, 4:10 AM").date().isoformat() == "2026-11-13"
    assert parse_date("2026/01/12 18:56:01 UTC").date().isoformat() == "2026-01-12"
    assert parse_date("") is None
    assert parse_date("garbage") is None


def _check(ds):
    people = {p["id"]: p for p in ds["people"]}
    assert len(people) == 6 and ds["stats"]["hidden_connections"] == 1
    assert ds["me"]["name"] == "Me Myself" and ds["me"]["slug"] == "me-slug"

    acme = next(c for c in ds["companies"] if c["key"] == "acme")
    assert acme["count"] == 3 and set(acme["variants"]) == {"Acme", "Acme AS", "ACME Norge AS"}
    assert acme["decision_makers"] == 2
    assert acme["people"][0] == "ada-l"  # CTO with messages ranks first

    ada = people["ada-l"]
    assert ada["msg_total"] == 3 and ada["msg_from_me"] == 1 and ada["msg_from_them"] == 1
    assert ada["conversations"] == 2
    assert ada["invitation"] == {"direction": "OUTGOING", "date": "2026-11-13T04:10:00Z", "has_message": True}
    assert "two_way" in ada["warmth_parts"] and ada["warmth"] > people["bob-b"]["warmth"]

    assert people["bob-b"]["endorse_given"] == 1
    assert people["dag-h"]["endorse_received"] == 0  # rejected endorsement ignored
    assert people["dag-h"]["invitation"]["direction"] == "INCOMING"
    assert "coraé" in people  # URL-decoded slug

    globex = next(c for c in ds["companies"] if c["key"] == "globex")
    assert globex["is_employer"] is True
    assert next(c for c in ds["companies"] if c["key"] == "self employed")["is_generic"] is True
    assert people["finn-b"]["company_key"] == ""

    msgs = ds["messages_by_person"]["ada-l"]
    assert [m["date"] for m in msgs] == sorted(m["date"] for m in msgs)
    assert msgs[1]["content"] == "Hi Ada,\nlong time!"  # multi-line message survives
    assert msgs[0]["group"] is True


def test_folder_named_zip(export_folder):
    cand = sources.inspect(export_folder)
    assert cand.kind == "folder"
    _check(parser.load(str(export_folder), now=NOW))


def test_zip(export_zip):
    cand = sources.inspect(export_zip)
    assert cand.kind == "zip"
    _check(parser.load(str(export_zip), now=NOW))


def test_discover_newest_first(export_folder, export_zip):
    import os
    os.utime(export_folder, (1, 1))
    found = sources.discover(export_zip.parent)
    assert [c.kind for c in found] == ["zip", "folder"]


def test_missing_optional_files(tmp_path):
    d = tmp_path / "LinkedIn_min"
    d.mkdir()
    (d / "Connections.csv").write_text(
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "A,B,https://www.linkedin.com/in/ab,,X,CEO,01 Jan 2020\n")
    ds = parser.load(str(d), now=NOW)
    assert ds["stats"]["connections"] == 1 and ds["stats"]["messages"] == 0
    assert ds["people"][0]["warmth"] == 5  # tenure only


def test_not_an_export(tmp_path):
    assert sources.inspect(tmp_path) is None
    assert sources.inspect(tmp_path / "nope") is None
