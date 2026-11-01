.PHONY: help test lint

help:
	@echo "make help   list targets"
	@echo "make test   pytest for both services"
	@echo "make lint   ruff"

test:
	cd apps/backend && ../../.venv/bin/python -m pytest
	cd apps/frontend && ../../.venv/bin/python -m pytest

lint:
	cd apps/backend && ../../.venv/bin/ruff check .
	cd apps/frontend && ../../.venv/bin/ruff check .
