<div align="center">

<img src="assets/icon.svg" alt="" width="112" height="112">

# linkgraph

### See who you know where, and your warmest path into any company, from your own LinkedIn export.

[![Python](https://img.shields.io/badge/Python-414754?style=flat-square&logo=python&logoColor=white)](https://www.python.org) [![FastAPI](https://img.shields.io/badge/FastAPI-414754?style=flat-square&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com) [![uv](https://img.shields.io/badge/uv-414754?style=flat-square&logo=uv&logoColor=white)](https://docs.astral.sh/uv/) [![JavaScript](https://img.shields.io/badge/JavaScript-414754?style=flat-square&logo=javascript&logoColor=white)](https://developer.mozilla.org/docs/Web/JavaScript) [![force-graph](https://img.shields.io/badge/force--graph-414754?style=flat-square)](https://github.com/vasturiano/force-graph)<br>
[![CI](https://img.shields.io/github/actions/workflow/status/mortennordbye/linkgraph/ci.yml?branch=main&style=flat-square&labelColor=414754&label=CI)](https://github.com/mortennordbye/linkgraph/actions/workflows/ci.yml) [![OpenSSF Scorecard](https://img.shields.io/ossf-scorecard/github.com/mortennordbye/linkgraph?style=flat-square&labelColor=414754&label=openssf%20scorecard)](https://scorecard.dev/viewer/?uri=github.com/mortennordbye/linkgraph) [![License](https://img.shields.io/github/license/mortennordbye/linkgraph?style=flat-square&labelColor=414754&color=e2e8f0)](LICENSE) [![Last commit](https://img.shields.io/github/last-commit/mortennordbye/linkgraph?style=flat-square&labelColor=414754&color=e2e8f0)](https://github.com/mortennordbye/linkgraph/commits/main) [![Stars](https://img.shields.io/github/stars/mortennordbye/linkgraph?style=flat-square&labelColor=414754&color=e2e8f0)](https://github.com/mortennordbye/linkgraph/stargazers)

</div>

A small local web app that reads the data export LinkedIn gives you and turns it into a lead
map: which companies your network covers, who the decision-makers are, and which people you
actually talk to. Type a target company or a role and it ranks your best ways in.

Everything runs on `127.0.0.1`. The app makes no external requests: the graph library is
vendored in `static/vendor/`, and a Content-Security-Policy blocks every other origin. Your
export and your notes never leave the machine. The one exception is the opt-in
[company logos](#company-logos) button, which asks first and sends company names only.

---

## Overview

| View | What it shows |
| ---- | ------------- |
| Companies | Every company in your network, ranked by connection count. Sort by any column, filter by lead status, or switch to cards. Click one to see each person, their seniority, warmth and message thread. |
| Graph | A force-directed graph of Me → companies → people. Filter by minimum connections, title keyword and connection recency, and cluster by company or by role seniority. Your own employers are hidden by default, because they often hold most of your network. |
| Warm Paths | Type a company or a role (`Equinor`, `CTO`, `Head of Data`) and get your best paths in, ranked by seniority, warmth and lead status. Acronyms expand: `CTO` also finds "Chief Technology Officer". |

Lead status (`Target`, `Reached Out`, `Warm Intro`, `Ignore`), notes and company merges are
saved to `linkgraph-notes.json` in the project folder. Each write goes to a temporary file
first and then replaces the original. Git ignores the file.

### Scores

| Score | How it is computed |
| ----- | ------------------ |
| Seniority tier | From the job title, in English and Norwegian. 4: C-level, Owner, Partner, Daglig leder. 3: VP, Director, Head of. 2: Manager, Lead, Senior. 1: other. Tiers 3 and 4 count as decision-makers. |
| Warmth (0-100) | Message count, two-way conversation, how recent the last message is, an invitation with a note, endorsements, recommendations, and how long you have been connected. Hover the meter to see the parts. |
| Path rank | tier × 20 + warmth × 0.8, plus 15 for `Warm Intro`. People with the status `Ignore` are hidden. |

### Company grouping

Company names group without case, punctuation, legal suffixes (`AS`, `ASA`, `AB`, `Inc`,
`Ltd`, …) and trailing region words (`Norge`, `Norway`, `Nordics`, …). For names that no rule
can catch ("Initech is now Globex"), open the company and use **Merge into…**. Merges are saved
and you can undo them.

### Company logos

Every company gets a monogram tile: its initials on a color that is fixed per company. This
needs no network and makes long lists easy to scan.

For real logos, press **Fetch logos** in the header. It asks before it sends anything. Then the
server, not the browser, does this once per company:

| Step | Service | What is sent |
| ---- | ------- | ------------ |
| Find the website | [Brønnøysund register](https://data.brreg.no/enhetsregisteret/api/docs/index.html) (Norwegian companies), then [Wikidata](https://www.wikidata.org) | Company name |
| Get the icon | DuckDuckGo icon service | Company domain |

People are never sent. The register and Wikidata only count a hit whose name matches the company
exactly, so "Equinor" never picks "Equinor Pensjon". Logos are saved in `logo-cache/` (git
ignores it) and load from `127.0.0.1`, so the browser still talks to nothing else. Companies
already done are skipped on the next run.

When no website is found, or the wrong one, type the domain in the company panel and press
**Set logo**. Some sites have no icon that the service knows; those keep their monogram.

### Files it reads

| File | Use |
| ---- | --- |
| `Connections.csv` | People, company, position, connected date. LinkGraph skips the notes above the header. |
| `messages.csv` | Message history and counts per person, two-way conversations, last contact |
| `Invitations.csv` | Who invited whom, and whether the invitation had a note |
| `Endorsement_Given_Info.csv`, `Endorsement_Received_Info.csv` | Endorsements both ways |
| `Recommendations_Given.csv`, `Recommendations_Received.csv` | Used if present |
| `Profile.csv`, `Positions.csv` | Your name, and your past employers (marked "employer") |

---

## Getting Started

You need [uv](https://docs.astral.sh/uv/) (`brew install uv`) and a LinkedIn data export
(LinkedIn: Settings > Data privacy > Get a copy of your data).

1. **Clone**: `git clone https://github.com/mortennordbye/linkgraph.git && cd linkgraph`
2. **Download your export** into `~/Downloads`. A zip (`Basic_LinkedInDataExport_*.zip`,
   `Complete_…zip`) or an unzipped folder both work. Zips are read in memory and never extracted.
3. **Run**: `./start.sh`

`start.sh` installs the dependencies, loads the newest export it finds, and opens
http://127.0.0.1:8765/. Use the **Export** menu in the header to switch between exports, or
**…** to enter another path.

| Option | Example |
| ------ | ------- |
| Use a specific export | `./start.sh --source ~/Downloads/Basic_LinkedInDataExport_01-01-2026.zip` |
| Other port, no browser | `./start.sh --port 9000 --no-browser` |
| Search another folder | `LINKGRAPH_DOWNLOADS=/some/other/dir ./start.sh` |

| Task | Command |
| ---- | ------- |
| Run | `make run` |
| Test | `make test` |
| Lint | `make lint` |

The tests use synthetic fixtures only. Never commit real export data: `.gitignore` blocks
`*LinkedInDataExport*` and the notes file.

---

## Repository structure

```text
linkgraph/
├── start.sh            # one command: install, parse, open the browser
├── linkgraph/
│   ├── sources.py      # find exports in ~/Downloads, read a folder or zip the same way
│   ├── parser.py       # CSV parsing, joins people across files, groups companies
│   ├── normalize.py    # company keys, profile slugs, seniority tiers
│   ├── scoring.py      # warmth score and path rank
│   ├── notes.py        # lead status, notes, merges and logo domains in linkgraph-notes.json
│   ├── logos.py        # opt-in logo lookup and the local logo cache
│   └── server.py       # FastAPI app, bound to 127.0.0.1
├── static/
│   ├── app.js          # state, API calls, router, side panel
│   ├── views/          # companies, graph and warm-paths views
│   └── vendor/         # force-graph, vendored so nothing loads from a CDN
├── tests/              # pytest suite on synthetic fixtures
└── .github/
    └── workflows/      # CI and security pipelines
```

---

## Workflows

| Workflow | Trigger | Purpose |
| -------- | ------- | ------- |
| CI | push, PR | ruff lint and pytest |
| Dependency Review | PR | block known-vulnerable dependency changes |
| Scorecard | push, weekly | OpenSSF supply-chain grade |
| Dependabot auto-merge | PR | merge Dependabot updates once the required checks pass |
| Dependabot CI failed | CI completed | flag Dependabot PRs whose checks failed |

---

<div align="center">

### ⭐ Star this repo if you find it useful ⭐

<a href="https://www.star-history.com/#mortennordbye/linkgraph&Date">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://api.star-history.com/svg?repos=mortennordbye/linkgraph&type=Date&theme=dark" />
    <source media="(prefers-color-scheme: light)" srcset="https://api.star-history.com/svg?repos=mortennordbye/linkgraph&type=Date" />
    <img alt="Star History Chart" src="https://api.star-history.com/svg?repos=mortennordbye/linkgraph&type=Date" width="600" />
  </picture>
</a>

Made by [Morten Victor Nordbye](https://nordbye.it/)

</div>
