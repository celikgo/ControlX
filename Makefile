.PHONY: install dev fmt lint type test check demo clean

install:
	python3 -m venv .venv && .venv/bin/pip install -e ".[dev,mcp]"

dev: install

fmt:
	.venv/bin/ruff format src tests
	.venv/bin/ruff check --fix src tests

lint:
	.venv/bin/ruff check src tests

type:
	.venv/bin/mypy

test:
	.venv/bin/pytest -q

check: lint type test

demo:
	.venv/bin/python -m controlx demo

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache build dist *.egg-info
