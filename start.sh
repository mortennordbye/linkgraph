#!/usr/bin/env bash
# LinkGraph: install dependencies, parse the newest LinkedIn export in ~/Downloads,
# and open the app in your browser. Everything stays on 127.0.0.1.
set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is not installed. Install it with: brew install uv" >&2
  echo "(or: curl -LsSf https://astral.sh/uv/install.sh | sh)" >&2
  exit 1
fi

uv sync --quiet
exec uv run python -m linkgraph.server "$@"
