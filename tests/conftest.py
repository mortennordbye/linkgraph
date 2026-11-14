"""Synthetic LinkedIn export fixtures. No real data."""

import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

NOW = datetime(2026, 11, 14, tzinfo=timezone.utc)

FILES = {
    "Connections.csv": (
        "Notes:\n"
        '"When exporting your connection data, you may notice that some of the email addresses are missing.\n'
        'This is a second line inside the quoted note."\n'
        "\n"
        "First Name,Last Name,URL,Email Address,Company,Position,Connected On\n"
        "Ada,Lovelace,https://www.linkedin.com/in/ada-l,,Acme,Chief Technology Officer,13 Nov 2026\n"
        "Bob,Builder,https://www.linkedin.com/in/bob-b,bob@example.com,Acme AS,Software Engineer,01 Jan 2024\n"
        "Cora,Nilsen,https://www.linkedin.com/in/cora%C3%A9,,ACME Norge AS,Head of Product,15 Mar 2025\n"
        "Dag,Hansen,https://www.linkedin.com/in/dag-h,,Globex Inc.,Daglig leder,02 Feb 2022\n"
        "Eve,Ng,https://www.linkedin.com/in/eve-n,,Self-employed,Consultant,02 Feb 2020\n"
        "Finn,Berg,https://www.linkedin.com/in/finn-b,,,Student,02 Feb 2021\n"
        ",,,,,,10 Oct 2026\n"
    ),
    "messages.csv": (
        '"CONVERSATION ID","CONVERSATION TITLE","FROM","SENDER PROFILE URL","TO","RECIPIENT PROFILE URLS","DATE","SUBJECT","CONTENT","FOLDER","ATTACHMENTS"\n'
        '"c1","","Me Myself","https://www.linkedin.com/in/me-slug","Ada Lovelace","https://www.linkedin.com/in/ada-l","2026-11-10 09:00:00 UTC","","Hi Ada,\nlong time!","INBOX",""\n'
        '"c1","","Ada Lovelace","https://www.linkedin.com/in/ada-l","Me Myself","https://www.linkedin.com/in/me-slug","2026-11-11 09:00:00 UTC","","Hello back","INBOX",""\n'
        '"c2","","Me Myself","https://www.linkedin.com/in/me-slug","Dag Hansen","https://www.linkedin.com/in/dag-h","2024-05-01 10:00:00 UTC","","Coffee?","INBOX",""\n'
        '"c3","Team","Bob Builder","https://www.linkedin.com/in/bob-b","Me Myself,Ada Lovelace","https://www.linkedin.com/in/me-slug,https://www.linkedin.com/in/ada-l","2025-01-01 10:00:00 UTC","","group hi","INBOX",""\n'
    ),
    "Invitations.csv": (
        "From,To,Sent At,Message,Direction,inviterProfileUrl,inviteeProfileUrl\n"
        'Me Myself,Ada Lovelace,"11/13/26, 4:10 AM",Great talk!,OUTGOING,https://www.linkedin.com/in/me-slug,https://www.linkedin.com/in/ada-l\n'
        'Dag Hansen,Me Myself,"2/2/22, 9:15 PM",,INCOMING,https://www.linkedin.com/in/dag-h,https://www.linkedin.com/in/me-slug\n'
    ),
    "Endorsement_Given_Info.csv": (
        "Endorsement Date,Skill Name,Endorsee First Name,Endorsee Last Name,Endorsee Public Url,Endorsement Status\n"
        "2026/01/12 18:56:01 UTC,Python,Bob,Builder,www.linkedin.com/in/bob-b,ACCEPTED\n"
    ),
    "Endorsement_Received_Info.csv": (
        "Endorsement Date,Skill Name,Endorser First Name,Endorser Last Name,Endorser Public Url,Endorsement Status\n"
        "2026/01/12 18:56:01 UTC,Python,Dag,Hansen,www.linkedin.com/in/dag-h,REJECTED\n"
    ),
    "Profile.csv": (
        "First Name,Last Name,Maiden Name,Address,Birth Date,Headline,Summary,Industry,Zip Code,Geo Location,Twitter Handles,Websites,Instant Messengers\n"
        "Me,Myself,,,,Consultant,,,,,,,\n"
    ),
    "Positions.csv": (
        "Company Name,Title,Description,Location,Started On,Finished On\n"
        "Globex,Consultant,,,Jan 2020,\n"
    ),
}


def _write_folder(base: Path) -> Path:
    base.mkdir(parents=True)
    for name, text in FILES.items():
        (base / name).write_text(text, encoding="utf-8")
    return base


@pytest.fixture
def export_folder(tmp_path):
    # Name ends in .zip on purpose: an unzipped folder must still count as a folder.
    return _write_folder(tmp_path / "downloads" / "Basic_LinkedInDataExport_01-01-2026.zip")


@pytest.fixture
def export_zip(tmp_path):
    p = tmp_path / "downloads" / "Complete_LinkedInDataExport_01-02-2026.zip.zip"
    p.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(p, "w") as zf:
        for name, text in FILES.items():
            zf.writestr(name, text)
    return p
