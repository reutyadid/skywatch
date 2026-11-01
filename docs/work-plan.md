# Work plan

Each stage ends with something working end to end. Tick requirement IDs in
`docs/requirements-checklist.md` as each one is proven.

## Repository layout (target)
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
│       │   ├── hosts.yml            # *.mshome.net names (static or generated: decided by the spike)
│       │   └── group_vars/
│       │       └── all.yml          # pinned versions: K3s, ArgoCD chart
│       ├── playbooks/
│       │   ├── site.yml             # full bring-up
│       │   └── verify.yml           # checks requirements against the cluster
│       └── roles/
│           ├── common/              # only what the spike proved necessary
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
    ├── architecture.md
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

| # | Stage | Done when | Requirements |
|---|-------|-----------|--------------|
| 1 | Repo setup (`dev`) | Public repo, layout, CLAUDE.md, settings.json, docs, `constraints.txt` | S1 |
| 2 | Backend | Runs locally: city → JSON; `/healthz`, `/metrics`; JSON logs; tests pass | R1.3, R1.4, R1.6 |
| 3 | Frontend | Runs locally against the backend via env URL; metrics; logs | R1.2, R1.6 |
| 4 | Docker | Both images build; containers talk to each other | R3.1 |
| 5 | CI | PR `dev` → `main` shows PR checks; push to `main` → GHCR (public) with SHA → values bumped → exactly one run | R3.2–R3.7 |
| 6 | Cluster (Ansible) | Start-of-stage checks pass; 3 nodes Ready; no app pods on the server; second run `changed=0`; kubectl from WSL | R2.1–R2.7 |
| 7 | Helm | One manual install works (last manual helm for the app, ever) | R4.1–R4.7 |
| 8 | ArgoCD | `bootstrap_secrets` + `argocd` roles; manual release removed; push reaches cluster | R5.1–R5.4, R4.8, B2 |
| 9 | Observability | Targets UP, dashboard, alerts | B1–B1.3 |
| 10 | Bring-up + verify | `make down && make up` works twice in a row; `make verify` green | R2.5, all |
| 11 | Docs + proof | README complete; screenshots; GitOps recording | S2–S6 |
| 12 | Stranger test | Fresh clone, fresh VMs, README only | S2 |
| 13 | If time | Ingress/Gateway API via Traefik → ESO + Vault → Loki | B3, D-031 |

## Host setup (before stage 1)
- [x] RAM: 24 GB installed (16 + 8), 21.9 GB usable
- [ ] `.wslconfig`: `networkingMode=mirrored`, `memory=6GB`, `processors=4`, then `wsl --shutdown`
- [x] Project lives in the WSL filesystem (`~/projects/skywatch`), not under `/mnt/c`

## Stage 6: checks before writing any role
Done right after `create-vms.sh` and `cloud-init/base.yaml` work.
- [ ] `.wslconfig` lowered to `memory=4GB`; Docker Desktop off
- [ ] SSH from WSL to each VM **by name** (`<vm>.mshome.net`)
- [ ] `ansible all -m ping` from WSL succeeds by name
- [ ] Reboot the host → names still resolve, SSH and Ansible ping still work
      (decides static vs generated inventory, D-004)
- [ ] `ip -br addr` and `swapon --show` on one VM → decide what goes into the `common` role (D-006)
- [ ] Results recorded in `docs/troubleshooting.md`
- If SSH by name or the reboot check fails and the fixes don't help → fallback to Path B (D-001).

## Rules while working
- Git: stages 1–4 on `dev`. Stage 5 starts with one PR `dev` → `main`. After that, commit directly to `main`.
- Every problem → entry in `docs/troubleshooting.md` as soon as it is solved (symptom, cause, fix).
- Small commits, one logical change each, conventional messages. The author commits, never the AI.
- From stage 8 on: no manual `kubectl apply` / `helm` for the app or monitoring.

## Review-session drills (before submitting)
- Change frontend text → watch it flow through CI and ArgoCD.
- Re-run the Ansible playbook on a healthy cluster → `changed=0`, and explain why.
- Break an image tag → debug `ImagePullBackOff`.
- Break the readiness probe → see the pod drop out of the Service endpoints.
- Delete a Deployment by hand → watch self-heal restore it.
- Make Open-Meteo slow/unreachable → see it in the upstream panels; pods stay alive.
- Stop a worker VM → watch pods reschedule; explain what happened to the 2 backend replicas.
- Reboot the host → bring everything back with `make up`.
