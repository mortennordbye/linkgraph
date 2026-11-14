# AGENTS.md

Guidance for coding agents (Claude Code and others) working in this repository.
See `CLAUDE.md` for the fuller working approach; this file is the quick command reference.

## Commands

| Task | Command |
| ---- | ------- |
| Install | `uv sync` |
| Run | `make run` (or `./start.sh`) |
| Test | `make test` |
| Single test | `uv run pytest -q -k <name>` |
| Lint | `make lint` |

## Layout

- `linkgraph/` — FastAPI backend: export discovery, CSV parsing, scoring, notes
- `static/` — vanilla-JS frontend, no build step; `static/vendor/` holds force-graph
- `tests/` — pytest suite on synthetic fixtures

## Conventions

- Commits follow Conventional Commits (`type(scope): summary`).
- Never commit secrets, real LinkedIn export data, or `linkgraph-notes.json`.
- Keep changes surgical — touch only what the task requires.
