.PHONY: help test lint

HADOLINT_IMAGE := hadolint/hadolint:v2.15.1

help:
	@echo "make help   list targets"
	@echo "make test   pytest for both services"
	@echo "make lint   ruff, hadolint, docker build --check (needs Docker)"

test:
	cd apps/backend && ../../.venv/bin/python -m pytest
	cd apps/frontend && ../../.venv/bin/python -m pytest

lint:
	cd apps/backend && ../../.venv/bin/ruff check .
	cd apps/frontend && ../../.venv/bin/ruff check .
	docker run --rm -i $(HADOLINT_IMAGE) < apps/backend/Dockerfile
	docker run --rm -i $(HADOLINT_IMAGE) < apps/frontend/Dockerfile
	docker build --check -f apps/backend/Dockerfile .
	docker build --check -f apps/frontend/Dockerfile .
