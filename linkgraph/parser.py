"""Parse LinkedIn export CSVs into one dataset: me, people, companies, messages."""

from __future__ import annotations

import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone

from . import normalize as N
from . import scoring
from .sources import ExportReader

_DATE_FORMATS = (
    "%d %b %Y",                 # Connections: 13 Nov 2026
    "%Y-%m-%d %H:%M:%S %Z",     # messages: 2026-11-12 09:21:06 UTC
    "%Y-%m-%d %H:%M:%S",
    "%m/%d/%y, %I:%M %p",       # Invitations: 11/13/26, 4:10 AM
    "%Y/%m/%d %H:%M:%S %Z",     # Endorsements: 2026/01/12 18:56:01 UTC
    "%Y/%m/%d %H:%M:%S",
    "%m/%d/%y",
    "%Y-%m-%d",
    "%b %Y",
)


def parse_date(value: str) -> datetime | None:
    v = (value or "").strip()
    if not v:
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(v, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def _iso(d: datetime | None) -> str | None:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ") if d else None


def read_rows(text: str | None, header_first_cell: str | None = None) -> list[dict]:
    """Read CSV rows. If header_first_cell is set, skip everything before that header row."""
    if not text:
        return []
    reader = csv.reader(io.StringIO(text))
    header = None
    rows: list[dict] = []
    for row in reader:
        if header is None:
            if not row or not any(c.strip() for c in row):
                continue
            if header_first_cell and row[0].strip().casefold() != header_first_cell.casefold():
                continue
            header = [c.strip() for c in row]
            continue
        if not any(c.strip() for c in row):
            continue
        rows.append({h: (row[i].strip() if i < len(row) else "") for i, h in enumerate(header)})
    return rows


def _get(row: dict, *names: str) -> str:
    """Case-insensitive column lookup."""
    for n in names:
        if n in row:
            return row[n]
    lower = {k.casefold(): v for k, v in row.items()}
    for n in names:
        v = lower.get(n.casefold())
        if v is not None:
            return v
    return ""


def build_dataset(reader: ExportReader, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)

    # --- Me ---------------------------------------------------------------
    profile = read_rows(reader.read_text("Profile.csv"))
    me_name = ""
    me_headline = ""
    if profile:
        p = profile[0]
        me_name = f"{_get(p, 'First Name')} {_get(p, 'Last Name')}".strip()
        me_headline = _get(p, "Headline")

    my_company_keys: set[str] = set()
    for pos in read_rows(reader.read_text("Positions.csv")):
        k = N.company_key(_get(pos, "Company Name"))
        if k:
            my_company_keys.add(k)

    # --- Connections -------------------------------------------------------
    people: dict[str, dict] = {}
    by_name: dict[str, str] = {}
    hidden = 0
    for r in read_rows(reader.read_text("Connections.csv"), header_first_cell="First Name"):
        first, last = _get(r, "First Name"), _get(r, "Last Name")
        url = _get(r, "URL")
        if not (first or last) and not url:
            hidden += 1
            continue
        pid = N.slug_from_url(url) or N.name_id(first, last)
        company = _get(r, "Company")
        position = _get(r, "Position")
        connected = parse_date(_get(r, "Connected On"))
        people[pid] = {
            "id": pid,
            "name": f"{first} {last}".strip(),
            "url": url,
            "email": _get(r, "Email Address"),
            "company": company,
            "company_key": N.company_key(company),
            "position": position,
            "tier": N.seniority_tier(position),
            "connected_on": _iso(connected),
            "msg_total": 0, "msg_from_me": 0, "msg_from_them": 0,
            "conversations": 0, "last_msg": None, "first_msg": None,
            "invitation": None,
            "endorse_given": 0, "endorse_received": 0,
            "recs_given": 0, "recs_received": 0,
        }
        by_name.setdefault(N.norm_name(people[pid]["name"]), pid)

    # --- Messages ----------------------------------------------------------
    msg_rows = read_rows(reader.read_text("messages.csv"))
    conv_participants: dict[str, set[str]] = defaultdict(set)
    for m in msg_rows:
        cid = _get(m, "CONVERSATION ID")
        s = N.slug_from_url(_get(m, "SENDER PROFILE URL"))
        if s:
            conv_participants[cid].add(s)
        for r in N.slugs_from_urls(_get(m, "RECIPIENT PROFILE URLS")):
            conv_participants[cid].add(r)
    slug_conv_count = Counter(s for parts in conv_participants.values() for s in parts)
    me_slug = slug_conv_count.most_common(1)[0][0] if slug_conv_count else ""
    me_norm = N.norm_name(me_name)

    messages_by_person: dict[str, list[dict]] = defaultdict(list)
    person_convs: dict[str, set[str]] = defaultdict(set)
    for m in msg_rows:
        cid = _get(m, "CONVERSATION ID")
        sender_slug = N.slug_from_url(_get(m, "SENDER PROFILE URL"))
        sender_name = _get(m, "FROM")
        from_me = (sender_slug == me_slug) if sender_slug else (N.norm_name(sender_name) == me_norm)
        others = {s for s in conv_participants.get(cid, set()) if s != me_slug}
        if not others:  # no URLs at all: fall back to names
            for nm in [sender_name] + _get(m, "TO").split(","):
                pid = by_name.get(N.norm_name(nm))
                if pid:
                    others.add(pid)
        date = parse_date(_get(m, "DATE"))
        record = {
            "conversation_id": cid,
            "conversation_title": _get(m, "CONVERSATION TITLE"),
            "from": sender_name,
            "from_me": from_me,
            "date": _iso(date),
            "subject": _get(m, "SUBJECT"),
            "content": _get(m, "CONTENT"),
            "group": len(others) > 1,
        }
        for pid in others:
            if pid not in people:
                continue
            p = people[pid]
            messages_by_person[pid].append(record)
            person_convs[pid].add(cid)
            p["msg_total"] += 1
            if from_me:
                p["msg_from_me"] += 1
            elif sender_slug == pid or N.norm_name(sender_name) == N.norm_name(p["name"]):
                p["msg_from_them"] += 1
            if record["date"]:
                if not p["last_msg"] or record["date"] > p["last_msg"]:
                    p["last_msg"] = record["date"]
                if not p["first_msg"] or record["date"] < p["first_msg"]:
                    p["first_msg"] = record["date"]
    for pid, convs in person_convs.items():
        people[pid]["conversations"] = len(convs)
    for msgs in messages_by_person.values():
        msgs.sort(key=lambda r: r["date"] or "")

    # --- Invitations -------------------------------------------------------
    for r in read_rows(reader.read_text("Invitations.csv")):
        direction = _get(r, "Direction").upper()
        if direction == "OUTGOING":
            slug = N.slug_from_url(_get(r, "inviteeProfileUrl"))
            name = _get(r, "To")
        else:
            slug = N.slug_from_url(_get(r, "inviterProfileUrl"))
            name = _get(r, "From")
        pid = slug if slug in people else by_name.get(N.norm_name(name))
        if not pid or pid not in people:
            continue
        people[pid]["invitation"] = {
            "direction": direction or None,
            "date": _iso(parse_date(_get(r, "Sent At"))),
            "has_message": bool(_get(r, "Message")),
        }

    # --- Endorsements and recommendations -------------------------------------
    def _bump(fname: str, url_col: str, first_col: str, last_col: str, field: str) -> None:
        for r in read_rows(reader.read_text(fname)):
            if _get(r, "Endorsement Status", "Status").upper() in {"REJECTED", "HIDDEN"}:
                continue
            slug = N.slug_from_url(_get(r, url_col))
            pid = slug if slug in people else by_name.get(
                N.norm_name(f"{_get(r, first_col)} {_get(r, last_col)}"))
            if pid and pid in people:
                people[pid][field] += 1

    _bump("Endorsement_Given_Info.csv", "Endorsee Public Url",
          "Endorsee First Name", "Endorsee Last Name", "endorse_given")
    _bump("Endorsement_Received_Info.csv", "Endorser Public Url",
          "Endorser First Name", "Endorser Last Name", "endorse_received")
    _bump("Recommendations_Given.csv", "Profile Url", "First Name", "Last Name", "recs_given")
    _bump("Recommendations_Received.csv", "Profile Url", "First Name", "Last Name", "recs_received")

    # --- Scores --------------------------------------------------------------
    for p in people.values():
        p["warmth"], p["warmth_parts"] = scoring.warmth(p, now)
        p["rank"] = scoring.base_rank(p)

    people_list, companies = group_companies(list(people.values()), my_company_keys)

    stats = {
        "connections": len(people),
        "hidden_connections": hidden,
        "raw_company_strings": len({p["company"] for p in people.values() if p["company"]}),
        "messages": len(msg_rows),
        "people_with_messages": sum(1 for p in people.values() if p["msg_total"]),
        "decision_makers": sum(1 for p in people.values() if p["tier"] >= 3),
        "files": {f: reader.has(f) for f in (
            "Connections.csv", "messages.csv", "Invitations.csv", "Endorsement_Given_Info.csv",
            "Endorsement_Received_Info.csv", "Recommendations_Given.csv",
            "Recommendations_Received.csv", "Profile.csv", "Positions.csv")},
    }

    return {
        "source": reader.candidate.to_dict(),
        "me": {"name": me_name or "Me", "headline": me_headline, "slug": me_slug,
               "employer_keys": sorted(my_company_keys)},
        "stats": stats,
        "people": people_list,
        "companies": companies,
        "messages_by_person": dict(messages_by_person),
    }


def resolve_alias(key: str, aliases: dict[str, str]) -> str:
    """Follow merge aliases (a -> b -> c). Stops on cycles."""
    seen = set()
    while key in aliases and key not in seen:
        seen.add(key)
        key = aliases[key]
    return key


def group_companies(people: list[dict], employer_keys, aliases: dict[str, str] | None = None
                    ) -> tuple[list[dict], list[dict]]:
    """Group people into companies. Returns new person dicts (with merged company keys)
    sorted by rank, and companies sorted by size. Inputs are not changed."""
    aliases = aliases or {}
    employer_keys = set(employer_keys)
    out_people = []
    groups: dict[str, list[dict]] = defaultdict(list)
    for p in people:
        q = dict(p)
        q["raw_company_key"] = p.get("raw_company_key", p["company_key"])
        q["company_key"] = resolve_alias(q["raw_company_key"], aliases) if q["raw_company_key"] else ""
        q["company_name"] = q["company"]
        out_people.append(q)
        if q["company_key"]:
            groups[q["company_key"]].append(q)
    companies = []
    for key, members in groups.items():
        variants = Counter(m["company"] for m in members)
        # Prefer a spelling from the target company itself after a merge.
        own = Counter({v: n for v, n in variants.items() if N.company_key(v) == key})
        name = N.display_name(own or variants)
        for m in members:
            m["company_name"] = name
        raw_keys = {m["raw_company_key"] for m in members}
        companies.append({
            "key": key,
            "name": name,
            "variants": sorted(variants),
            "merged_keys": sorted(raw_keys - {key}),
            "count": len(members),
            "decision_makers": sum(1 for m in members if m["tier"] >= 3),
            "max_warmth": max(m["warmth"] for m in members),
            "messages": sum(m["msg_total"] for m in members),
            "latest_connected": max((m["connected_on"] or "" for m in members), default=None),
            "is_employer": bool(raw_keys & employer_keys),
            "is_generic": N.is_generic(key),
            "people": [m["id"] for m in sorted(members, key=lambda m: -m["rank"])],
        })
    companies.sort(key=lambda c: (-c["count"], c["name"].casefold()))
    out_people.sort(key=lambda p: -p["rank"])
    return out_people, companies


def load(path: str, now: datetime | None = None) -> dict:
    return build_dataset(ExportReader(path), now)
