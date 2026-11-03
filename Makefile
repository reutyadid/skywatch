.PHONY: help vms cluster verify up down test lint

HADOLINT_IMAGE := hadolint/hadolint:v2.15.1

help:
	@echo "make help   list targets"
	@echo "make vms      create the 3 VMs"
	@echo "make cluster  install K3s and ArgoCD with Ansible, save ./kubeconfig"
	@echo "make verify   check the requirements against the running cluster"
	@echo "make up       vms + cluster + verify"
	@echo "make down     destroy the 3 VMs"
	@echo "make test     pytest for both services"
	@echo "make lint     ruff, helm lint, ansible-lint, hadolint (needs Docker)"

vms:
	infra/scripts/create-vms.sh

cluster:
	cd infra/ansible && ../../.venv-ansible/bin/ansible-playbook playbooks/site.yml

verify:
	cd infra/ansible && ../../.venv-ansible/bin/ansible-playbook playbooks/verify.yml

# Make runs the prerequisites in order and stops at the first failure.
up: vms cluster verify

down:
	infra/scripts/destroy-vms.sh

test:
	cd apps/backend && ../../.venv/bin/python -m pytest
	cd apps/frontend && ../../.venv/bin/python -m pytest

lint:
	cd apps/backend && ../../.venv/bin/ruff check .
	cd apps/frontend && ../../.venv/bin/ruff check .
	helm lint --strict charts/skywatch
	cd infra/ansible && PATH="$(CURDIR)/.venv-ansible/bin:$$PATH" ansible-lint
	docker run --rm -i $(HADOLINT_IMAGE) < apps/backend/Dockerfile
	docker run --rm -i $(HADOLINT_IMAGE) < apps/frontend/Dockerfile
