# Work plan

Each stage ended with something working end to end, and its requirement IDs were ticked in
`docs/requirements-checklist.md` as each one was proven.

## Repository layout
```
skywatch/
├── CLAUDE.md
├── .claude/settings.json            # denies git commit / git push for the AI
├── README.md
├── Makefile
├── .dockerignore
├── .github/workflows/ci.yaml
├── requirements/constraints.txt     # single source of truth for Python versions
├── apps/                            # what we build
│   ├── backend/
│   │   ├── app.py
│   │   ├── gunicorn.conf.py
│   │   ├── requirements.txt
│   │   ├── requirements-test.txt
│   │   ├── Dockerfile
│   │   └── tests/
│   └── frontend/
│       ├── app.py
│       ├── gunicorn.conf.py
│       ├── templates/
│       ├── requirements.txt
│       ├── requirements-test.txt
│       ├── Dockerfile
│       └── tests/
├── infra/                           # how the cluster is built
│   ├── cloud-init/
│   │   └── base.yaml                # injects the SSH key at first boot
│   ├── scripts/
│   │   ├── create-vms.sh            # multipass.exe launch x3
│   │   └── destroy-vms.sh           # multipass.exe delete + purge
│   └── ansible/
│       ├── ansible.cfg
│       ├── requirements.txt         # pip: ansible-core, kubernetes (pinned)
│       ├── requirements.yml         # galaxy: kubernetes.core (pinned)
│       ├── inventory/
│       │   ├── hosts.yml            # *.mshome.net names, static (D-004)
│       │   └── group_vars/
│       │       └── all.yml          # pinned versions: K3s, ArgoCD chart
│       ├── playbooks/
│       │   ├── site.yml             # full bring-up
│       │   └── verify.yml           # checks requirements against the cluster
│       └── roles/
│           ├── k3s_server/          # install pinned K3s, taint, tls-san
│           ├── k3s_agent/           # join workers with token read from the server
│           ├── kubeconfig/          # fetch to WSL, replace 127.0.0.1
│           ├── bootstrap_secrets/   # Grafana Secret, only if missing
│           └── argocd/              # helm install argo/argo-cd + apply root-app
├── charts/skywatch/                 # what runs on it
│   ├── Chart.yaml
│   ├── values.yaml                  # image tags owned by CI
│   └── templates/
│       ├── _helpers.tpl
│       ├── backend-deployment.yaml
│       ├── backend-service.yaml
│       ├── backend-configmap.yaml
│       ├── frontend-deployment.yaml
│       ├── frontend-service.yaml
│       ├── frontend-configmap.yaml
│       ├── servicemonitor.yaml
│       ├── prometheusrule.yaml
│       └── grafana-dashboard.yaml
├── argocd/                          # how it gets there
│   ├── values.yaml                  # Helm values for argo/argo-cd
│   ├── root-app.yaml                # app-of-apps
│   └── apps/
│       ├── skywatch.yaml            # Application -> charts/skywatch
│       └── monitoring.yaml          # Application -> kube-prometheus-stack
└── docs/                            # why
    ├── requirements-checklist.md
    ├── decisions.md
    ├── work-plan.md
    ├── troubleshooting.md
    └── images/
```

## `make` targets
```
make help      list targets
make vms       infra/scripts/create-vms.sh
make cluster   ansible-playbook playbooks/site.yml
make verify    ansible-playbook playbooks/verify.yml
make up        vms + cluster + verify
make down      infra/scripts/destroy-vms.sh
make lint      ruff, hadolint, helm lint, ansible-lint
make test      pytest for both services
```

## Stages

| # | Stage | Done when | Requirements | Status |
|---|-------|-----------|--------------|--------|
| 1 | Repo setup (`dev`) | Public repo, layout, CLAUDE.md, settings.json, docs, `constraints.txt` | S1 | Done |
| 2 | Backend | Runs locally: city → JSON; `/healthz`, `/metrics`; JSON logs; tests pass | R1.3, R1.4, R1.6 | Done |
| 3 | Frontend | Runs locally against the backend via env URL; metrics; logs | R1.2, R1.6 | Done |
| 4 | Docker | Both images build; containers talk to each other | R3.1 | Done |
| 5 | CI | PR `dev` → `main` shows PR checks; push to `main` → GHCR (public) with SHA → values bumped → exactly one run | R3.2–R3.7 | Done |
| 6 | Cluster (Ansible) | Start-of-stage checks pass; 3 nodes Ready; no app pods on the server; second run `changed=0`; kubectl from WSL | R2.1–R2.7 | Done |
| 7 | Helm | One manual install works (last manual helm for the app, ever) | R4.1–R4.7 | Done |
| 8 | ArgoCD | `argocd` role; manual release removed; push reaches cluster | R5.1–R5.4, R4.8, B2 | Done |
| 9 | Observability | `bootstrap_secrets` role; targets UP, dashboard, alerts | B1–B1.3 | Done |
| 10 | Bring-up + verify | `make down && make up` works twice in a row; `make verify` green | R2.5, all | Done |
| 11 | Docs + proof | README complete; screenshots; GitOps recording | S2–S6 | Done (screenshots instead of a recording) |
| 12 | Stranger test | Fresh clone, fresh VMs, README only | S2 | Not done: `make down && make up` from the README instead |
| 13 | If time | Ingress/Gateway API via Traefik → ESO + Vault → Loki | B3, D-031 | Not done: in the README's "What I'd improve" |

## Host setup (before stage 1)
- [x] RAM: 24 GB installed (16 + 8), 21.9 GB usable
- [x] `.wslconfig`: `networkingMode=nat`, `processors=4` (D-003)
- [x] Raised to `memory=6GB` at stage 4 (Docker builds)
- After every host reboot: enable forwarding between WSL and the Default Switch (D-003, README)
- [x] `make` installed in WSL
- [x] `python3.12-venv` installed in WSL
- [x] Project lives in the WSL filesystem (`~/projects/skywatch`), not under `/mnt/c`

## Stage 6: checks before writing any role
Done right after `create-vms.sh` and `cloud-init/base.yaml` work.
- [x] `.wslconfig` lowered to `memory=4GB`; Docker Desktop off
- [x] SSH from WSL to each VM **by name** (`<vm>.mshome.net`)
- [x] `ansible all -m ping` from WSL succeeds by name
- [x] Each VM resolves and pings the others by name (agents will reach the server by name)
- [x] Reboot the host → names still resolve, SSH and Ansible ping still work
      (decides static vs generated inventory, D-004). Result: the whole Default Switch network
      moved (172.31.x.x → 192.168.16x.x), names followed, VMs started on their own. After
      re-enabling forwarding, SSH, Ansible ping and VM-to-VM names all worked. Static inventory.
- [x] `ip -br addr` and `swapon --show` on one VM → decide whether a `common` role is needed (D-006).
      Result on a test VM (Ubuntu 24.04): one NIC (`eth0`), no swap. So no swap task and no
      `--node-ip` / `--flannel-iface`, and no `common` role.
- [x] Results recorded in `docs/troubleshooting.md` (networking) and above (checks)
- If SSH by name or the reboot check fails and the fixes don't help → fallback to Path B (D-001).

## Stage 10: bring-up results
- [x] `make verify` on the running cluster: `ok=12 changed=0 failed=0` (before the node IP checks). Checked that it fails when
      the cluster differs from the requirements (wrong K3s version, wrong replica count via `-e`).
- [x] `site.yml` with the new `wait_for_connection` play on a healthy cluster: still `changed=0`.
- [x] `make down && make up`, run 1: about 17 minutes, `failed=0`, `make verify` green. Every VM
      answered SSH on the first try. ArgoCD needed about 4.5 minutes to make `monitoring` Healthy
      (29 retries in total; the limit is 60 per app).
- [x] `make down && make up`, run 2: `failed=0`, `make verify` green (32 retries in total).
- Stopped VMs after a host reboot: not a risk. The VMs come back on their own, so `create-vms.sh`
  needs no `multipass start`. They are restored, not rebooted (`AutomaticStopAction = Save`).
- [x] Full host reboot with the cluster installed: the VMs came back with new IPs,
      but K3s kept the old ones, so traffic between VMs and DNS for external names failed.
      Fixed by restarting K3s and CoreDNS (README step 2, `docs/troubleshooting.md`).
      `verify.yml` now checks node IPs and the NodePort through every node (D-033).

## Rules followed while working
- Git: stages 1–4 on `dev`. Stage 5 starts with one PR `dev` → `main`. After that, commit directly to `main`.
- Every problem → entry in `docs/troubleshooting.md` as soon as it is solved (symptom, cause, fix).
- Small commits, one logical change each, in Git's standard style. The author commits, never the AI.
- From stage 8 on: no manual `kubectl apply` / `helm` for the app or monitoring.

## Review-session drills (before the review session)
- Change frontend text → watch it flow through CI and ArgoCD.
- Re-run the Ansible playbook on a healthy cluster → `changed=0`, and explain why.
- Break an image tag → debug `ImagePullBackOff`.
- Break the readiness probe → see the pod drop out of the Service endpoints.
- Delete a Deployment by hand → watch self-heal restore it.
- Make Open-Meteo slow/unreachable → see it in the upstream panels; pods stay alive.
- Stop a worker VM → watch pods reschedule; explain what happened to the 2 backend replicas.
- Reboot the host → enable forwarding, run `make verify`, fix with the README step 2 restarts.
