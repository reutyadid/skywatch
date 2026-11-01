.PHONY: help test lint

help:
	@echo "make help   list targets"
	@echo "make test   pytest for the backend"
	@echo "make lint   ruff"

test:
	cd apps/backend && ../../.venv/bin/python -m pytest

lint:
	cd apps/backend && ../../.venv/bin/ruff check .
