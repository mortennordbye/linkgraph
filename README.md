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

By default everything runs on `127.0.0.1`. The app makes no external requests: the graph library is
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
| If it has none | The company's own website (`https` only) | One anonymous request for its icon |

People are never sent. The register and Wikidata only count a hit whose name matches the company
exactly, so "Equinor" never picks "Equinor Pensjon". Logos are saved in `logo-cache/` (git
ignores it) and load from `127.0.0.1`, so the browser still talks to nothing else. Companies
already done are skipped on the next run.

The request to a company's own website is guarded: https on port 443 only, the server resolves
the host itself and refuses any private, loopback or link-local address, it connects to the exact
address it checked, and it checks every redirect the same way. So a domain from the register can
never make LinkGraph call into your own network.

When no website is found, or the wrong one, type the domain in the company panel and press
**Set logo**.

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

## Get your LinkedIn data

LinkGraph reads the data export that LinkedIn gives every member. You request it once; it takes
about 10 minutes for the first part.

1. Open [linkedin.com/mypreferences/d/download-my-data](https://www.linkedin.com/mypreferences/d/download-my-data)
   (or **Me** > **Settings & Privacy** > **Data privacy** > **Get a copy of your data**).
2. Choose **Want something in particular?** and tick these files:

   | File | What LinkGraph uses it for | Needed? |
   | ---- | -------------------------- | ------- |
   | Connections | People, companies, titles, connected date | Yes |
   | Messages | Message history and warmth | Strongly recommended |
   | Invitations | Who invited whom, with or without a note | Recommended |
   | Endorsements, Recommendations | Warmth | Optional |
   | Profile, Positions | Your name and your past employers | Optional |

   The other choice, **Download larger data archive**, also works. It has all of the above, but
   LinkedIn needs up to 24 hours to prepare it.
3. Press **Request archive** and confirm with your password.
4. LinkedIn emails you when the file is ready, usually after about 10 minutes. Return to the
   same page and press **Download archive**. The link works for 72 hours.
5. Leave the file in `~/Downloads`. It is named like `Basic_LinkedInDataExport_11-14-2026.zip`
   (the full archive starts with `Complete_`). You do not need to unzip it.

When LinkGraph runs on a server ([Run in Kubernetes](#run-in-kubernetes)), press **Import zip**
in the header and pick the file instead. You can do all the steps on a phone: open the link in
the phone's browser, not in the LinkedIn app. On an iPhone the zip goes to **Files** >
**Downloads**, and **Import zip** opens the same place.

Some connections hide their email address from exports, so most email fields are empty. That is
normal. The export holds data about other people: keep it on your machine, and delete old exports
when you have a new one.

---

## Getting Started

You need [uv](https://docs.astral.sh/uv/) (`brew install uv`) and your LinkedIn export (see
[Get your LinkedIn data](#get-your-linkedin-data)).

1. **Clone**: `git clone https://github.com/mortennordbye/linkgraph.git && cd linkgraph`
2. **Put your export** in `~/Downloads`. A zip (`Basic_LinkedInDataExport_*.zip`,
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

## Run in Kubernetes

The CI publishes an image to `ghcr.io/mortennordbye/linkgraph` on every push to `main` (tags
`latest`, `sha-<commit>` and `0.0.<run>`). The image holds the code only. Mount a volume at
`/data`: it holds the imported exports, `linkgraph-notes.json` and `logo-cache/`. The image runs
as uid 1000, so give the pod `fsGroup: 1000`.

| Variable | Image default | Use |
| -------- | ------------- | --- |
| `LINKGRAPH_HOST` | `0.0.0.0` | Bind address (`127.0.0.1` outside the image) |
| `LINKGRAPH_ALLOWED_HOSTS` | none | The hostname your proxy serves, e.g. `linkgraph.example.lan` |
| `LINKGRAPH_DATA_DIR` | `/data` | Notes and logo cache |
| `LINKGRAPH_DOWNLOADS` | `/data/exports` | Where **Import zip** saves exports |

The app has no login. Serve it only on a private network or behind your own auth, never on
the internet: everyone who can open the page can read your messages. Fetch logos needs egress
to the internet on port 443.

On a phone, open the page and choose **Share** > **Add to Home Screen** (iOS) or **Install app**
(Android). It then opens full screen with its own icon.

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
│   ├── siteicons.py    # SSRF-guarded icon fetch from a company's own website
│   └── server.py       # FastAPI app, bound to 127.0.0.1 by default
├── static/
│   ├── app.js          # state, API calls, router, side panel
│   ├── views/          # companies, graph and warm-paths views
│   └── vendor/         # force-graph, vendored so nothing loads from a CDN
├── tests/              # pytest suite on synthetic fixtures
├── Dockerfile          # the cluster image (code only; data lives on a volume)
└── .github/
    └── workflows/      # CI and security pipelines
```

---

## Workflows

| Workflow | Trigger | Purpose |
| -------- | ------- | ------- |
| CI | push, PR | ruff lint and pytest, then build the image (pushed to GHCR from `main` only) |
| Container Scan | push, weekly | Trivy scan of the image, results under Security |
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
