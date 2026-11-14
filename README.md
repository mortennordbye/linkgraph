# LinkGraph

A local-first explorer for your LinkedIn data export. Use it to find consulting leads, see who works where, and find warm paths into target companies.

Everything runs on `127.0.0.1`. The app makes no external requests: the graph library is in `static/vendor/`, and a Content-Security-Policy blocks all other origins.

## Start

```sh
./start.sh
```

The script needs [uv](https://docs.astral.sh/uv/) (`brew install uv`). It installs the dependencies, finds the newest LinkedIn export in `~/Downloads`, and opens http://127.0.0.1:8765/.

Options:

```sh
./start.sh --source ~/Downloads/Basic_LinkedInDataExport_01-01-2026.zip   # use a specific export
./start.sh --port 9000 --no-browser
LINKGRAPH_DOWNLOADS=/some/other/dir ./start.sh                            # search another folder
```

## Exports it finds

Any entry in `~/Downloads` whose name contains `linkedin` and that holds a `Connections.csv`:

- a zip (`Basic_LinkedInDataExport_*.zip`, `Complete_…zip.zip`), read in memory, never extracted
- an unzipped folder, also when the folder name ends in `.zip`

The newest one loads first. Use the **Export** menu in the header to switch, or **…** to enter another path.

## Files it reads

| File | Use |
|---|---|
| `Connections.csv` | people, company, position, connected date (it skips the notes above the header) |
| `messages.csv` | message history and counts per person, two-way conversations, last contact |
| `Invitations.csv` | who invited whom, and whether the invitation had a note |
| `Endorsement_Given_Info.csv`, `Endorsement_Received_Info.csv` | endorsements both ways |
| `Recommendations_Given.csv`, `Recommendations_Received.csv` | used if present |
| `Profile.csv`, `Positions.csv` | your name and your past employers (marked "employer") |

## Views

- **Companies**: all companies, ranked by connection count. Sort by any column, filter by status, or switch to cards. Click a company to see each person, their seniority, warmth, and message thread.
- **Graph**: Me → companies → people. Filter by minimum connections, title keyword, and connection recency. You can cluster by company or by role seniority. Your own employers are hidden by default, because they often hold most of your network.
- **Warm Paths**: type a company or a role (for example `CTO` or `Head of Data`). It lists your best paths in, ranked by seniority, warmth and lead status. Acronyms expand: `CTO` also finds "Chief Technology Officer".

## Scores

- **Seniority tier** (English and Norwegian titles): 4 C-level/Owner/Partner/Daglig leder, 3 VP/Director/Head, 2 Manager/Lead/Senior, 1 other. Tiers 3 and 4 are decision-makers.
- **Warmth** (0-100): message count, two-way conversation, how recent the last message is, an invitation with a note, endorsements, recommendations, and how long you have been connected. Hover the meter to see the parts.
- **Path rank** = tier × 20 + warmth × 0.8, plus 15 for `Warm Intro`. People with the status `Ignore` are hidden.

## Company grouping

Company names group without case, punctuation, legal suffixes (`AS`, `ASA`, `AB`, `Inc`, `Ltd`, …) and trailing region words (`Norge`, `Norway`, `Nordics`, …). For names that a rule cannot catch ("Initech is now Globex"), open the company and use **Merge into…**. Merges are saved and you can undo them.

## Your notes

Lead status (`Target`, `Reached Out`, `Warm Intro`, `Ignore`), notes and company merges are saved to `linkgraph-notes.json` in this folder. Each write goes to a temporary file first and then replaces the original. Git ignores this file.

## Development

```sh
uv run pytest
```

The tests use synthetic fixtures only. Do not commit real export data. `.gitignore` blocks `*LinkedInDataExport*` and the notes file.
