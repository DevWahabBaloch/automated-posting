.PHONY: setup install run test lint typecheck check

setup:
	python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt

install:
	pip install -r requirements-dev.txt

run:
	uvicorn app.main:app --host 0.0.0.0 --port 4000 --reload

test:
	pytest

lint:
	ruff check app tests
	ruff format --check app tests

typecheck:
	mypy app

check: lint typecheck test
