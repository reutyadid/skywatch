# Requirements checklist

Every requirement from the assignment, where it is implemented, and how it is proven.
Status: `[ ]` not started · `[~]` in progress · `[x]` done and proven · `[-]` skipped (optional).

## 1. Application

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| R1.1 | Two small services in Python (or Go) | `apps/frontend`, `apps/backend` | Repo layout | [x] |
| R1.2 | Flask frontend: city input, shows current temperature and conditions | `apps/frontend/app.py`, `templates/` | Screenshot of a result in the browser, served from the cluster (`docs/images/gitops-code-after.png`) | [x] |
| R1.3 | Backend HTTP API: takes a city, calls Open-Meteo (geocoding + forecast), returns the result | `apps/backend/app.py` | `curl` to the backend endpoint returns JSON | [x] |
| R1.4 | Backend health endpoint | `apps/backend/app.py` (`/healthz`) | `curl /healthz` returns 200 | [x] |
| R1.5 | Minimal code | Both services | Review: backend 226 lines, frontend 157, in clear sections | [x] |
| R1.6 | Configuration from environment variables (incl. backend URL) | `app.py` config section, ConfigMaps | `grep os.getenv`, ConfigMap contents | [x] |

## 2. Cluster provisioning (Path A)

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| R2.1 | 3 Ubuntu VMs (Multipass) | `infra/scripts/create-vms.sh`, `infra/cloud-init/base.yaml` | `multipass.exe list` shows 3 running VMs | [x] |
| R2.2 | Ansible roles install K3s on the control plane | `roles/k3s_server` | Role code, server node Ready | [x] |
| R2.3 | Ansible roles join the workers | `roles/k3s_agent` | `kubectl get nodes` shows 3 nodes Ready | [x] |
| R2.4 | K3s version pinned | `inventory/group_vars/all.yml` | `kubectl get nodes` shows the pinned version | [x] |
| R2.5 | Playbook is idempotent: re-run on a healthy cluster changes nothing | All roles, handlers | Second `make cluster` ends with `changed=0`; `make down && make up` passed twice in a row (stage 10) | [x] |
| R2.6 | `kubectl` works from the host | `roles/kubeconfig` | `kubectl get nodes` from the WSL shell | [x] |
| R2.7 | No application workloads on the control plane | `roles/k3s_server` taint | Proven manually: `kubectl get pods -n skywatch -o wide` shows only workers. Checked on every `make up` by `verify.yml` | [x] |

## 3. Containerization and CI

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| R3.1 | Small, production-minded Dockerfile per service | `apps/*/Dockerfile` | slim base, non-root, `.dockerignore`, image size | [x] |
| R3.2 | Pipeline runs on every push to `main` | `.github/workflows/ci.yaml` | Actions run history | [x] |
| R3.3 | Lints the code | `ci.yaml` lint job | Job log | [x] |
| R3.4 | Builds both images | `ci.yaml` build job | Job log | [x] |
| R3.5 | Pushes to GHCR tagged with the commit SHA | `ci.yaml` | GHCR package tags match commit SHAs | [x] |
| R3.6 | Updates image tags in the Helm values in Git | `ci.yaml` bump job | Bot commit changing `values.yaml` | [x] |
| R3.7 | Tag-update commit does not retrigger the pipeline | `GITHUB_TOKEN`, `paths-ignore`, `[skip ci]` | One run per push in Actions history | [x] |

## 4. Helm chart

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| R4.1 | One chart for the whole app | `charts/skywatch` | Repo layout | [x] |
| R4.2 | Frontend Deployment + Service reachable from the host | `frontend-*.yaml`, NodePort | Browser on `<worker>.mshome.net:<nodePort>` | [x] |
| R4.3 | Backend Deployment with 2 replicas | `backend-deployment.yaml`, `values.yaml` | `kubectl get deploy` shows 2/2 | [x] |
| R4.4 | Backend internal Service | `backend-service.yaml` (ClusterIP) | `kubectl get svc` | [x] |
| R4.5 | Configuration via values and ConfigMaps, not hardcoded in images | `values.yaml`, `*-configmap.yaml` | Change a value, see it applied without a rebuild (`LOG_LEVEL` INFO → DEBUG: `docs/images/the-debug-commit.png`, `no-ci-for-values-change.png`, `argo-cd-sync-values-change.png`, `history-for-values-change.png`, `proof-from-terminal.png`) | [x] |
| R4.6 | Readiness and liveness probes on every container | Deployments | Proven manually: rendered Deployments, pods Ready. Checked on every `make up` by `verify.yml` | [x] |
| R4.7 | Resource requests and limits on every container | Deployments | Proven manually: rendered Deployments, `kubectl top`. Checked on every `make up` by `verify.yml` | [x] |
| R4.8 | No plaintext secrets in Git | K3s token read at run time (`roles/k3s_agent`); Grafana Secret from `roles/bootstrap_secrets` (stage 9) | `git grep` finds no secret values | [x] |
| R4.9 | Secret handling approach explained ("Explain your approach") | README "Secret handling", details in D-008, D-023 | README | [x] |

## 5. GitOps with ArgoCD

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| R5.1 | ArgoCD installed in the cluster | `roles/argocd` (Helm), `argocd/values.yaml` | `kubectl get pods -n argocd` | [x] |
| R5.2 | `Application` deploys the chart from the repo | `argocd/apps/skywatch.yaml` | ArgoCD UI shows the app | [x] |
| R5.3 | Automated sync with prune and self-heal | `syncPolicy` | Delete a resource manually, it comes back | [x] |
| R5.4 | A **code** change pushed to `main` ends up running in the cluster, no manual commands | CI + ArgoCD | Subtitle added to the home page (`13307e1`): `docs/images/gitops-code-before.png`, `-commit.png`, `-ci.png`, `-bump.png`, `-argocd.png`, `-after.png`. Config-only change shown in R4.5 | [x] |

## Bonus (chosen)

| ID | Bonus | Where | Proof | Status |
|----|-------|-------|-------|--------|
| B1 | Prometheus + Grafana (kube-prometheus-stack) | `argocd/apps/monitoring.yaml` | Grafana UI, login with the `grafana-admin` Secret (`docs/images/grafana-dashboard.png`) | [x] |
| B1.1 | App metrics: request count and latency | `prometheus_client` in both apps, ServiceMonitor | Prometheus targets UP (2 backend, 1 frontend), `http_requests_total` and `http_request_duration_seconds` return data | [x] |
| B1.2 | Dashboard (as code) | `grafana-dashboard.yaml` | Dashboard screenshot (`docs/images/grafana-dashboard.png`) | [x] |
| B1.3 | Alerts | `prometheusrule.yaml` | 5 SkyWatch rules loaded in Prometheus, health `ok` | [x] |
| B2 | ArgoCD app-of-apps for add-ons | `argocd/root-app.yaml` | ArgoCD UI tree | [x] |
| B3 | Ingress / Gateway API via Traefik instead of NodePort (end, if time) | — | Not done: listed in README "What I'd improve" | [-] |

## Submission

| ID | Requirement | Where | Proof | Status |
|----|-------------|-------|-------|--------|
| S1 | Public GitHub repo with all code, manifests, playbooks, pipelines | GitHub | Repo is public | [x] |
| S2 | README: chosen path + step-by-step bring-up from scratch | `README.md` "Bring it up in 3 steps" | `make down && make up` from the README steps passed twice (stage 10) | [x] |
| S3 | README: architecture overview and key decisions | `README.md` "Architecture", "Key design decisions" | README | [x] |
| S4 | README: problems encountered and solutions | README "Problems and solutions", linking `docs/troubleshooting.md` | README | [x] |
| S5 | README: what to improve with more time | `README.md` "What I'd improve with more time" | README | [x] |
| S6 | README: proof of the GitOps flow | README "Proof of the GitOps flow", `docs/images/` | Screenshots of a code change and a config change | [x] |
| S7 | Able to explain every part live | Whole repo | Review-session drills | [ ] |
| S8 | Submitted within 7 days | — | Submitted within the 7 days | [x] |

## Evaluation criteria → covered by

| Criterion | Covered by |
|-----------|------------|
| GitOps flow | R5.1–R5.4 |
| CI pipeline: stages, SHA tagging, no loops, caching | R3.2–R3.7, D-018, D-019 |
| Helm and Kubernetes: templates, probes, resources, secrets | R4.1–R4.9 |
| Provisioning: reproducible, idempotent Ansible on Path A | R2.1–R2.7, `make down && make up` |
| Code: readable, minimal, env-configured | R1.5, R1.6 |
| Documentation: bring-up from README alone | S2 (`make down && make up` from the README) |
| Review session | S7, drills in `docs/work-plan.md` |
