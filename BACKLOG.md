# Backlog

Known gaps deliberately left for later. WIP belongs on a branch, not here.

## No screenshots in the README
- **What:** The README describes the three views in words only.
- **Why deferred:** Screenshots of the real app show real names and messages, so they need a
  synthetic export to render from, and none exists yet beyond the small pytest fixtures.
- **Unblock:** Generate a fake export (a few hundred people across a few dozen companies) with a
  script under `tests/`, run the app against it with `--source`, and capture the three views.
- **Where:** `README.md` (Overview), `tests/conftest.py` (fixture shape to copy).

## Company merges are not offered automatically
- **What:** Names such as "Initech is now Globex" or "Globex Business Services" stay separate
  until the user merges them by hand in the company panel.
- **Why deferred:** Fuzzy matching merges unrelated companies too often to run silently. A
  suggestions list ("these 3 look alike, merge?") would be safe, but it is new UI.
- **Unblock:** Rank company-key pairs by token overlap, show the top pairs in the Companies
  view, and reuse `PUT /api/aliases/{key}` for the merge.
- **Where:** `linkgraph/normalize.py`, `static/views/companies.js`.
