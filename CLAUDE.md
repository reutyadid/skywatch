# SkyWatch: instructions for Claude

## What this project is
A home assignment for a DevOps Engineer role: a weather app (Flask frontend + Flask backend
calling Open-Meteo) on K3s running on 3 Multipass VMs, provisioned with Ansible (Path A),
delivered with GitHub Actions CI, a single Helm chart and ArgoCD GitOps.
Bonus focus: observability (Prometheus + Grafana).

- Requirements and proof of each: `docs/requirements-checklist.md`
- Every design decision and its reasoning: `docs/decisions.md`
- Work order, layout and current stage: `docs/work-plan.md`

## Principles (in priority order)
1. **The assignment text comes first.** If the task names a technology or a fact, follow it.
2. **Every line must be explainable.** The author will walk through it live and must
   understand all of it. Prefer obvious code over clever code.
3. **Minimal.** Only what the task requires, plus the chosen bonus. No speculative features.
4. **Clear documentation.** Someone else must be able to bring the system up from the README alone.

## Decisions already made (do not change without asking)
- Path A: 3 Multipass VMs (1 server + 2 agents), K3s pinned, installed by our own Ansible roles.
  `k3s-io/k3s-ansible` is a reference only; never copy from it.
- VMs are created by `infra/scripts` (calling `multipass.exe` from WSL); Ansible only configures them.
- Machines are addressed by `<vm>.mshome.net` names, in the inventory and in K3s.
- K3s server is tainted explicitly (K3s does not taint by default). Traefik and other built-ins stay on.
- K3s join token is read from the server at run time. No `ansible-vault`, no secrets in Git.
- Ansible owns the bootstrap only: cluster, ArgoCD (official Helm chart via `kubernetes.core.helm`),
  bootstrap Secret, root app. Everything after that comes from Git through ArgoCD.
- Flask for both services, gunicorn with **1 worker + N threads** per pod.
- Backend replicas = 2, frontend replicas = 1 (both in values).
- Shared `requirements/constraints.txt`; Docker build context is the repo root.
- **One** Helm chart (`charts/skywatch`), one file per resource, shared `_helpers.tpl`. No subcharts.
- Grafana Secret created by Ansible only if missing; chart uses `existingSecret`.
- Logs: JSON to stdout only. No log files, no PVCs for logs.
- Frontend exposure: NodePort. No ingress-nginx.
- Make is a thin menu; logic lives in scripts and playbooks.

## Conventions
- Pin every version: base images, K3s, Helm charts, Ansible collections, Python packages. Never `latest`.
- All runtime configuration from environment variables (ConfigMaps), never baked into images.
- Containers run as non-root.
- One health endpoint, `/healthz`, used by both probes with different parameters.
  No probe may call Open-Meteo (or, for the frontend, the backend).
- Timeouts: Open-Meteo 5s < frontend->backend 10s < gunicorn 30s.
- Test/lint dependencies live in `requirements-test.txt` and never enter an image.
- Ansible: declarative modules over `command`/`shell`; when `command` is unavoidable, set
  `creates`/`changed_when`. Config files from templates; restarts only through handlers.
  Every task in `common` must be justified by the checks at the start of stage 6.
- The project lives inside the WSL filesystem, never under `/mnt/c`.

## Commands
```
make help      # list targets
make vms       # create the 3 VMs
make cluster   # run the Ansible bring-up
make verify    # check requirements against the running cluster
make up        # vms + cluster + verify
make down      # destroy the VMs
make lint      # ruff, hadolint, helm lint, ansible-lint
make test      # pytest for both services
```

## How to work with me
- Before writing code: explain the plan and wait for approval.
- After writing code: explain what every line or block does and why.
- Never add a dependency, tool or file outside the planned structure without asking.
- Never edit image tags in `charts/skywatch/values.yaml`; CI owns them.
- From the ArgoCD stage on: no `kubectl apply` / `helm install` for the app or monitoring. Changes go through Git.
- When a problem is solved: add an entry to `docs/troubleshooting.md` (symptom, cause, fix).
- When a decision changes: update `docs/decisions.md` in the same change.
- Git: stages 1–4 on `dev`; merged to `main` by one PR at the CI stage; after that, directly on `main`.
- **Never run `git commit` or `git push` yourself.** When a change is ready, stop, list the files
  changed and propose a commit message. The author reviews and commits.
- Proposed commits are small, one logical change each, conventional messages (`feat:`, `fix:`, `docs:`, `ci:`).
