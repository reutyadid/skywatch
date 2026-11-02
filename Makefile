.PHONY: help vms down test lint

HADOLINT_IMAGE := hadolint/hadolint:v2.15.1

help:
	@echo "make help   list targets"
	@echo "make vms    create the 3 VMs"
	@echo "make down   destroy the 3 VMs"
	@echo "make test   pytest for both services"
	@echo "make lint   ruff, hadolint (needs Docker)"

vms:
	infra/scripts/create-vms.sh

down:
	infra/scripts/destroy-vms.sh

test:
	cd apps/backend && ../../.venv/bin/python -m pytest
	cd apps/frontend && ../../.venv/bin/python -m pytest

lint:
	cd apps/backend && ../../.venv/bin/ruff check .
	cd apps/frontend && ../../.venv/bin/ruff check .
	docker run --rm -i $(HADOLINT_IMAGE) < apps/backend/Dockerfile
	docker run --rm -i $(HADOLINT_IMAGE) < apps/frontend/Dockerfile
