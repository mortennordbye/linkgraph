.DEFAULT_GOAL := help
.PHONY: help run test lint

help: ## Show available commands
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-6s\033[0m %s\n", $$1, $$2}'

run: ## Run the app on http://127.0.0.1:8765/ (opens the browser)
	./start.sh

test: ## Run the test suite
	uv run pytest -q

lint: ## Lint the Python code (ruff)
	uv run ruff check .
