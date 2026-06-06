.PHONY: all lint test clean

install: .venv requirements.txt requirements-dev.txt
	uv pip install -r requirements-dev.txt

all: install lint test

.venv:
	uv venv

requirements.txt: requirements.in
	uv pip compile requirements.in -o requirements.txt

requirements-dev.txt: requirements-dev.in requirements.in
	uv pip compile requirements-dev.in -o requirements-dev.txt

lint:
	uv run ruff check --fix src/ tests/
	uv run ruff format src/ tests/
	uv run mypy src/

test:
	uv run pytest tests/

clean:
	rm -rf .venv .mypy_cache .ruff_cache .pytest_cache __pycache__ requirements.txt requirements-dev.txt
