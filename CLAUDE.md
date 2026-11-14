# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Working approach

These guidelines bias toward caution over speed. For trivial tasks, use judgment.

### Think before coding

Don't assume. Don't hide confusion. Surface tradeoffs.

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them — don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### Simplicity first

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### Surgical changes

Touch only what you must. Clean up only your own mess.

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it — don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: every changed line should trace directly to the user's request.

### Goal-driven execution

Define success criteria. Loop until verified.

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

### Track unfinished work in BACKLOG.md

If you leave anything unfinished, partially implemented, or explicitly defer it, add an entry to `BACKLOG.md` in the repo root before reporting the task done. Don't bury deferrals in chat — they vanish next session.

Each entry needs four things: **what** the work is, **why** it was deferred, **what would unblock it**, and **where** the relevant code lives (file paths). Read existing entries for the format.

Don't put work-in-progress on `BACKLOG.md` — WIP belongs on a branch. The backlog is for *known gaps the team has agreed to leave for later*. If you finish an item, delete it.

What counts as "unfinished":
- Tier 1 / Tier 2 splits where you only shipped Tier 1.
- Out-of-scope items you noticed but didn't fix.
- Features behind a feature flag that still need ramping or cleanup.
- Tests skipped, mocks left in, debug logging not yet stripped.
- TODO comments you wrote (write the entry instead — TODOs rot in code).

What does NOT belong:
- Forward-looking ideas the user didn't agree to defer ("we could also..."). Either do them or drop them.
- Codebase-wide debts that pre-existed your work and the user didn't ask you to track.

### No AI attribution in commits

Commits and PRs read as the human author's. No AI fingerprint, ever.

- No `Co-Authored-By` trailer naming Claude or any AI.
- No session links or IDs (e.g. a `Claude-Session:` trailer).
- No "Generated with Claude Code", 🤖 emoji, or similar tool signatures in commit messages, PR descriptions, or issue bodies.
- Describe the change, not the tool that produced it.

These guidelines are working if: fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.


## Development

Python 3.12 via uv. No Docker: the app reads `~/Downloads` and opens a browser on the host,
so it runs on the host by design.

```bash
# run:    make run     # or ./start.sh; serves http://127.0.0.1:8765/ and opens the browser
# test:   make test    # pytest suite   (single test: uv run pytest -q -k <name>)
# lint:   make lint    # ruff
```

Point the app at a throwaway folder instead of your real Downloads with
`LINKGRAPH_DOWNLOADS=<dir> ./start.sh --no-browser`.

## Before reporting a task complete

```bash
make lint && make test
```

Run it even when the change "looks obviously correct". Skip only for doc-only changes.

Additionally, when the change touches `static/`: load the app in a browser, open each of the
three views, and check the console for errors. The pytest suite never runs the frontend.

## Security baseline

LinkGraph is a single-user tool on `127.0.0.1` with no login. The data it serves is personal:
names, job titles, and private message content from a LinkedIn export. The rules that apply:

- **Localhost only.** Uvicorn binds `127.0.0.1`. Never change that to `0.0.0.0`; there is no
  auth to stand in for it.
- **Host-header allowlist** (`ALLOWED_HOSTS` in `linkgraph/server.py`) stops DNS rebinding.
  Keep it; it is the only thing between a hostile web page and `/api/data`.
- **JSON bodies only on writes.** FastAPI rejects non-JSON bodies, so a cross-site form cannot
  change notes. Do not add endpoints that take form or text bodies.
- **No external requests from the page.** No CDN scripts, fonts, analytics or telemetry.
  Vendor any new frontend library into `static/vendor/`. The CSP in `static/index.html`
  enforces this; do not loosen it.
- **The server calls out in one place only: `linkgraph/logos.py`**, and only after the user
  confirms "Fetch logos" or saves a domain. It sends company names and domains, never people, to
  three hosts fixed in code. Keep it that way: no new hosts, no URLs built from export data, no
  fetching a company's own website (that would open SSRF into the user's network), and nothing
  that runs on startup or on page load. Images must pass `sniff_image()`; never accept SVG.
- **Export data is hostile input.** Escape everything with `esc()` before it goes into HTML;
  message content can contain markup. Zips are read in memory and never extracted.
- **Never commit real data.** Fixtures in `tests/` are synthetic. `.gitignore` blocks
  `*LinkedInDataExport*` and `linkgraph-notes.json`; screenshots of the real app show real names.

## Architecture

FastAPI backend (`linkgraph/`) and a vanilla-JS single-page frontend (`static/`) with no build
step. The backend parses the export once into memory; the frontend fetches the whole dataset
(about 700 people is small) and does filtering, sorting and ranking in the browser.

### Data flow rules

`sources.discover()` → `ExportReader` (folder or zip, same interface) → `parser.build_dataset()`
→ held in `State` → `GET /api/data` regroups companies with the saved merge aliases on every call.

- People join across files by LinkedIn slug (`normalize.slug_from_url`), with a normalized-name
  fallback. URL forms differ per file (with and without `https://`), so always go through the slug.
- `parser.group_companies()` must not mutate its input: the parsed dataset stays alias-free, and
  merges are applied per request from `linkgraph-notes.json`.
- Message bodies are only served by `GET /api/people/{id}/messages`, never in `/api/data`.

### Safety rules for AI-assisted changes

- **`linkgraph-notes.json` is the user's work.** Keep the format backward compatible, and keep
  writes atomic (`notes.save`: temp file then `os.replace`).
- **Company keys are persisted.** Statuses and merges are keyed by `normalize.company_key()`.
  Changing that function silently orphans saved notes; if you must, migrate the keys.
- **LinkedIn changes its export format without notice.** Look up columns case-insensitively
  through `_get()` and treat every optional file as possibly missing.

### Environment variables

No `.env` file; there is nothing secret to configure.

| Variable | Default | Use |
| -------- | ------- | --- |
| `LINKGRAPH_DOWNLOADS` | `~/Downloads` | Folder to search for exports |
| `LINKGRAPH_PORT` | `8765` | Port, same as `--port` |

### Directory layout

```
linkgraph/
├── sources.py     find exports, read folder or zip the same way
├── parser.py      CSV parsing, cross-file joins, company grouping
├── normalize.py   company keys, slugs, seniority tiers
├── scoring.py     warmth score, base rank
├── notes.py       statuses, notes, merge aliases, logo domains (atomic JSON)
├── logos.py       opt-in logo lookup (brreg, Wikidata, DuckDuckGo icons) + logo-cache/
└── server.py      FastAPI app, Host allowlist, static files
static/
├── app.js         state, API, router, shared side panel
├── views/         companies.js, graph.js, paths.js
└── vendor/        force-graph (vendored, with its license)
tests/             pytest on synthetic fixtures (conftest.py builds a folder and a zip)
```

### Key patterns

- **`effectiveRank()`** in `static/app.js` is the one place that adds lead-status boosts on top
  of the backend's `base_rank`. Keep ranking logic there, not in the views.
- **`matchWords()`** does word-prefix title matching with acronym expansion. Use it for every
  title search; plain substring matching finds "cto" in "Director".
- **`companyLogo()`** in `static/app.js` renders a company's logo or its monogram tile. Use it
  wherever a company name appears, so logos and colors stay the same everywhere.
- **Views return a cleanup function** from `render*()`; the router calls it on navigation.
  Unsubscribe listeners and stop the graph there.

### Code quality

- **Reuse before adding** — check shared utilities and components before writing new ones.
- **Prefer established frameworks over reinventing** — reach for a well-maintained, widely-used library before hand-rolling HTTP, dates, parsing, and the like. Only build your own when no good option fits, and say why.
- **Use current, supported versions** — pick libraries that are actively maintained and pull a recent, supported release. An unmaintained library is a security and upgrade liability.
- **No dead code** — if a control has no effect, implement or remove it.
- **No premature abstractions** — only extract a helper when it's used in 2+ places.
