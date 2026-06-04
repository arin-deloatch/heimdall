.PHONY: lint format typecheck test complexity ci run

lint:
	uv run ruff check src/ tests/

format:
	uv run ruff format src/ tests/

typecheck:
	uv run pyright src/

complexity:
	uv run radon cc src/ -n C -s
	uv run radon mi src/ -n B

test:
	uv run pytest -v --cov=quality_enforcer_mcp --cov-report=term-missing

ci: lint typecheck complexity test

run:
	uv run quality-enforcer-mcp

run-http:
	uv run quality-enforcer-mcp --transport streamable-http --port 8000
