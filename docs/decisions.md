# Design decisions

Each decision: what was chosen, why, what else was considered, and when I would choose differently.

**Guiding principle (D-000):** the assignment text comes first. Where it names a technology or
a fact, that is the default. All other choices follow from one idea: the two services are parts
of one product, built by one pipeline, tagged with one SHA and always released together.

---

# Cluster and infrastructure

## D-001 · Path A: 3 Multipass VMs + K3s via Ansible
- **Decision:** Path A, the path the task marks as full and recommended. 1 control plane + 2 workers.
- **Why:** The host has 24 GB installed (16 GB + 8 GB, DDR4-2400), 21.9 GB usable after the
  integrated GPU's share. That meets the task's 16 GB+ requirement, so per D-000 the recommended
  path is the default. The evaluation criteria also call out idempotent Ansible on Path A.
- **Risk:** Windows networking between WSL and Hyper-V VMs. Checked at the start of stage 6, before
  any role is written. Stages 1–5 (app, Docker, CI) do not depend on the cluster, so they are not delayed.
- **Fallback:** if those checks fail, Path B (kind) with the failed checks documented as the reason.

## D-002 · Provisioning vs configuration
- **Decision:** Small bash scripts create and destroy the VMs (`multipass.exe` called from WSL).
  cloud-init injects the SSH key at first boot. Ansible configures the machines once they exist.
- **Why:** Creating machines (provisioning) and configuring them (configuration management) are
  different jobs. Ansible has no official Multipass module, and creating VMs is not its natural role.
  In a cloud setup the provisioning part would be Terraform.

## D-003 · Host networking and project location
- **Decision:** WSL in `networkingMode=nat`, with IP forwarding enabled on Windows between the
  `vEthernet (WSL*)` and `vEthernet (Default Switch)` adapters. The project lives inside the WSL
  filesystem, not under `/mnt/c`.
- **Why NAT and not mirrored:** mirrored mode only mirrors the physical adapters, so WSL has no route
  to the Default Switch network where the VMs live (`No route to host`). The WSL team confirms that
  mirrored mode does not support reaching other VMs on the host (microsoft/WSL#11494). In NAT mode,
  Windows is WSL's router; once forwarding is on, it passes traffic to the VMs and back.
  Tested at the start of stage 6: name resolution, ping and SSH by name all work.
- **Cost:** forwarding resets on every host reboot, so the admin PowerShell command must be run again
  (README). A scheduled task could automate it; kept manual so every step stays visible.
- **Known conflict:** a VM that runs Docker can have a bridge network (e.g. `172.17.0.0/16`) that covers
  WSL's NAT address; that VM then sends its replies into Docker and the connection times out. The
  cluster VMs run no Docker, and K3s uses `10.42.0.0/16` and `10.43.0.0/16`.
- **Why the WSL filesystem:** under `/mnt/c`, Ansible ignores `ansible.cfg` (world-writable directory)
  and SSH keys fail on permissions.

## D-004 · Addressing: DNS names + inventory
- **Decision:** Machines are addressed by their Hyper-V Default Switch DNS names
  (`<vm>.mshome.net`), both in the Ansible inventory and in K3s (server URL for agents, `tls-san`).
- **Why:** Default Switch IPs can change after a host reboot, which breaks the inventory, the
  kubeconfig and the agents' connection to the server. Names stay the same.
- **Inventory vs DNS:** DNS tells K3s *where* the server is. The inventory tells Ansible *which*
  machines exist and *what role* each plays. Both are needed.
- **Decided at the start of stage 6: static inventory in Git.** The check confirmed the reason for
  names: after a host reboot every VM got a new address, and the whole Default Switch network moved
  (172.31.x.x → 192.168.16x.x). The names followed, from WSL and between VMs, so nothing that uses
  names had to change.

## D-005 · Own Ansible roles
- **Decision:** Roles written from scratch: `k3s_server`, `k3s_agent`, `kubeconfig`,
  `bootstrap_secrets`, `argocd`. The official `k3s-io/k3s-ansible` collection is used only to compare.
- **K3s install:** the pinned binary is downloaded with `get_url` and checked against the release's
  `sha256sum-amd64.txt`; config and systemd unit come from our templates. Not the `get.k3s.io`
  script: the script itself is not pinned, and every step here stays visible and idempotent.
- **Why:** The task asks to *write* roles, and every line must be explainable. The official
  collection covers HA, external databases, airgap and upgrades, which are out of scope.
- **Idempotency:** declarative modules, config files from templates, and handlers that restart
  K3s only when its config changed. Proof: a second run reports `changed=0`.

## D-006 · No `common` role
- **Decision:** A `common` role would hold only tasks proven necessary on the Multipass Ubuntu image.
  The checks at the start of stage 6 found none, so there is no `common` role.
- **Why:** The image has no swap, so a "disable swap" task would be noise. Each VM has one NIC, so
  no `--node-ip` / `--flannel-iface`. K3s loads the kernel modules it needs.
- **Revisit when:** a check shows something the image lacks; then add the role with only that task.

## D-007 · K3s configuration
- **Decision:** Pinned K3s version in `group_vars/all.yml`. Config through `/etc/rancher/k3s/config.yaml`
  rendered from a template. Explicit taint on the server:
  `node-role.kubernetes.io/control-plane:NoSchedule`.
- **Why the explicit taint:** unlike kind, K3s does **not** taint the server by default, so without
  it app pods would be scheduled on the control plane.
- **Built-ins kept:** Traefik, ServiceLB, local-path, metrics-server stay enabled (K3s defaults;
  disabling them is also a decision that would need a reason). Traefik enables the Ingress bonus later.

## D-008 · K3s join token: not stored anywhere
- **Decision:** The server generates the token on first install. The `k3s_agent` role reads it from
  `/var/lib/rancher/k3s/server/node-token` on the server at run time and passes it to the agents.
- **Why:** No secret in Git and no vault password to hand to a reviewer. With `ansible-vault`, anyone
  without the password could not bring the cluster up. It is also idempotent by nature.

## D-009 · kubeconfig
- **Decision:** The `kubeconfig` role fetches `/etc/rancher/k3s/k3s.yaml` from the server to WSL and
  replaces `127.0.0.1` with the server's DNS name.

## D-010 · Resource sizing
- **Decision:**
  ```
  Usable:              21.9 GB
  Windows + browser:   ~5-6 GB
  VM control plane:     2 GB, 2 vCPU
  VM workers:           2 x 3.5 GB, 2 vCPU each   (ArgoCD + monitoring run here)
  WSL:                  4 GB, 4 processors
  ---------------------------------------------
  Total:               ~18-19 GB  ->  ~3 GB headroom
  ```
- **WSL:** 4 GB during stages 1–3 (Flask and pytest only), 6 GB during stages 4–5 (Docker builds,
  no VMs running), back to 4 GB from stage 6. It then only runs Ansible, kubectl and helm. WSL tends to hold memory as page cache, so a lower cap
  protects the VMs. Docker Desktop runs inside WSL, so it is turned off while the cluster runs.
- **Why:** 24 GB installed, 21.9 GB usable (the integrated Radeon Vega GPU takes ~2 GB).
  The CPU is still a 4-core / 8-thread laptop CPU, so expect slow syncs.
- **If memory gets tight in stage 9:** shorter Prometheus retention, Alertmanager off.

---

# Application

## D-011 · Flask for both services
- **Decision:** Python + Flask for frontend and backend.
- **Why:** The task names a Flask frontend. Using Flask for the backend too keeps one framework,
  one server setup and nearly identical Dockerfiles.
- **Alternatives:** FastAPI + uvicorn (better for async, but not what the task names); Go.

## D-012 · gunicorn with 1 worker + N threads
- **Decision:** `workers = 1` fixed in `gunicorn.conf.py`; threads from env (default 4).
- **Why:** The app is I/O-bound (waits on HTTP). The GIL is released during I/O, so threads give
  enough concurrency. With several workers, each process holds its own Prometheus registry and
  scrapes hit a random worker, so counters jump backwards. One process per pod keeps metrics correct
  without `prometheus_client` multiprocess mode. Scaling is done with Kubernetes replicas.
- **Alternatives:** multiple workers + multiprocess mode; uvicorn (ASGI server, needs a WSGI adapter
  for Flask and adds no benefit).
- **Revisit when:** the workload becomes CPU-bound.

## D-013 · Replicas: backend 2, frontend 1
- **Decision:** Backend 2 (required). Frontend 1, configurable in values.
- **Why:** Follows the task. The frontend is a single point of failure, accepted here; production
  would run at least 2.

## D-014 · Timeout chain
- **Decision:** Open-Meteo 5s < frontend→backend 10s < gunicorn 30s. All from env.
- **Why:** Each layer must wait longer than the one below it, so failures surface as clear errors.
  The real request limits are the two HTTP client timeouts. With threaded workers, gunicorn's
  timeout only checks that the worker process is alive; it does not limit a single request.
- **Known limitation:** The backend makes two Open-Meteo calls, each with its own 5s limit. If both
  are slow, it can take about 10s and hit the frontend's limit, so the frontend shows a timeout
  instead of the backend's error. Accepted: it is rare and still fails cleanly.

## D-015 · Shared constraints file for dependency versions
- **Decision:** `requirements/constraints.txt` pins every version. Each service has its own
  `requirements.txt` (names only) and `requirements-test.txt`. Docker build context is the repo root.
- **Why:** One source of truth, so the two services cannot drift apart. A root build context is
  standard in a monorepo, and `.dockerignore` keeps it small.
- **Alternatives:** per-service pins + a CI script that checks they match (duplication + extra code).
- **Revisit when:** services are owned or released independently.
- **Ansible is separate:** its own venv (`.venv-ansible`) with pins in `infra/ansible/requirements.txt`.
  Both Ansible and Flask use Jinja2, so a shared venv would tie their versions together.

## D-016 · Production-minded images
- **Decision:** Pinned slim Python base (same version via `ARG` in both), non-root user,
  `--no-cache-dir`, `.dockerignore`, gunicorn as entrypoint. GHCR packages are public.
- **Why:** Small, reproducible, least-privilege images. Public packages need no `imagePullSecret`,
  and the repo is public anyway.

## D-017 · One health endpoint, two probes
- **Decision:** A single `/healthz` (process alive, no external calls) used by both probes, with
  different parameters: readiness is sensitive (stop traffic fast), liveness is tolerant (restart only if stuck).
- **Why:** A separate `/readyz` only adds value when there is an internal dependency to check
  (database, cache warm-up). The services have none, so it would return the same as `/healthz`.
  The only dependency is Open-Meteo, and no probe may depend on it: in liveness it would restart
  healthy pods in a loop; in readiness it would remove all backend pods at once, so the frontend
  gets connection errors instead of a clear "upstream unavailable" response.
  The same applies to the frontend: its probes must not check the backend, to avoid cascading failures.
- **Would add `/readyz` when:** a service gets an internal dependency or a warm-up phase.

---

# Delivery

## D-018 · CI pipeline design
- **Decision:** On PR: lint + test + build (no push). On push to `main`: lint + test + build +
  push to GHCR with the commit SHA tag + bump `values.yaml`.
- **Caching:** buildx `type=gha` layer cache, pip cache.
- **Lint:** ruff (Python), hadolint (Dockerfiles, run from its pinned image so nothing is installed
  on the host), `docker build --check` (Docker's own Dockerfile checks), `helm lint --strict`,
  `ansible-lint`. CI runs the same `make lint` as the laptop, with Helm pinned through `azure/setup-helm`.
  `docker build --check` runs only in CI: it needs Docker 27+, and the local Docker Desktop (24.0.6)
  is kept as is for now.

## D-019 · Preventing a CI trigger loop
- **Decision:** Three layers: the bump commit is pushed with `GITHUB_TOKEN` (which does not
  trigger workflows), `paths-ignore` on `values.yaml`, and `[skip ci]` in the message.
  Plus a `concurrency` group so two fast pushes don't race on the bump.
- **Why:** Defense in depth; any one mechanism can be changed by mistake later.
- **Note:** Branch protection that requires PRs would block the bot push (see D-029).
- **Revisit at stage 7:** `paths-ignore` also skips CI when a person changes only `values.yaml`
  (replicas, resources, config), so that change gets no `helm lint`. Plan: run only `helm lint`
  for such changes, without building images.
- **Working on `main`:** the bot adds a commit after every push, so run `git pull` before the next push.

## D-020 · One Helm chart, no subcharts
- **Decision:** `charts/skywatch`, one file per resource, shared `_helpers.tpl`, one values block per service.
- **Why:** The task requires one chart, and both services are released together with the same SHA.
- **Alternatives:** umbrella chart with a subchart per service.
- **Would switch when:** the services are owned by different teams or released independently,
  or to compose third-party charts (e.g. a database) next to the app.

## D-021 · Configuration through values and ConfigMaps
- **Decision:** Every runtime setting (backend URL, timeouts, threads, log level) comes from a ConfigMap
  rendered from values. Images contain no environment-specific config.
- **Backend URL:** built in the chart from the backend Service name, so the two can't drift apart.
- **Config changes roll the pods:** each Deployment carries a `checksum/config` annotation of its
  ConfigMap. A value change changes the checksum, so Kubernetes replaces the pods; no rebuild, no
  manual restart.

## D-022 · ArgoCD: installed by Ansible with Helm, then app-of-apps
- **Decision:** The `argocd` role runs on WSL (against the Kubernetes API, not over SSH) and installs
  the official `argo/argo-cd` chart with `kubernetes.core.helm`, using `argocd/values.yaml` and a version
  pinned in `group_vars`. It then applies `argocd/root-app.yaml`, which manages `apps/skywatch.yaml`
  and `apps/monitoring.yaml`. Automated sync, prune, self-heal.
- **Built in stage 8:** chart `argo-cd` 10.11.6 (ArgoCD v3.5.6) with `kubernetes.core` 6.6.0 (Helm v4
  support since 6.4.0). The play runs on `localhost` with `.venv-ansible`'s Python, where the
  `kubernetes` library lives. Dex and notifications are off. The UI is reached with
  `kubectl port-forward`. The `bootstrap_secrets` role arrives with monitoring in stage 9.
- **Why Ansible for the bootstrap:** installing ArgoCD once with an outside tool, then letting it
  manage everything from Git, is the usual pattern; the tool varies (Terraform in the cloud, Ansible
  when Ansible already builds the cluster). It keeps `make cluster` one idempotent command.
- **Boundary:** Ansible owns the bootstrap only (cluster, ArgoCD, bootstrap Secret, root app).
  Everything after that comes from Git through ArgoCD. Ansible never installs the app or monitoring,
  so two tools never manage the same resources.
- **Why:** ArgoCD cannot install itself the first time. `kubernetes.core.helm` is idempotent and keeps
  the whole bring-up in one tool.
- **Alternatives:** Terraform Helm provider (common in cloud setups; here it would add a tool);
  plain `helm` in a script.
- **Known gotchas:** kube-prometheus-stack CRDs need `ServerSideApply=true`. ArgoCD polls Git every ~3 minutes.
- **Ordering between `skywatch` and `monitoring`:** ArgoCD dry-runs every resource before applying any,
  so a missing ServiceMonitor CRD would fail the whole `skywatch` sync, Deployments included. The
  ServiceMonitor and PrometheusRule carry `SkipDryRunOnMissingResource=true`, so the app deploys
  anyway, and `skywatch.yaml` has a short `retry` (10s doubling, up to 3m) that applies the two once
  the CRDs exist. The bonus can never block the app. If the CRDs are not ready within the retry
  window, the ServiceMonitor and PrometheusRule are applied on the next commit's sync (ArgoCD does
  not retry a failed automated sync for the same commit); in practice the bot's tag commit after
  every push triggers it. While the two objects wait, the `skywatch` app shows a failed sync in the
  ArgoCD UI even though its pods are running and healthy; this is expected and clears after the retry.
- **In a larger setup:** install CRDs first, as their own step, and order Applications with sync waves
  (needs a custom Application health check in `argocd-cm`). Not worth the extra config here.
- **Finalizers:** `skywatch` and `monitoring` carry `resources-finalizer.argocd.argoproj.io`, so
  deleting an Application deletes what it installed instead of leaving orphans. The root app has no
  finalizer on purpose, so deleting it leaves the child Applications running. A finalizer waits for
  ArgoCD to delete the resources, so removing ArgoCD before its Applications would hang the deletion;
  `make down` avoids this by destroying the VMs.
- **With more time:** ArgoCD managing itself.

## D-023 · Secrets
- **Decision:** The `bootstrap_secrets` role generates a random Grafana admin password and creates
  the Secret, **only if it does not already exist** (otherwise every run would change it and break
  idempotency). The monitoring chart references it with `existingSecret`. Nothing secret is in Git.
- **Why:** Works for anyone who clones the repo, and is simple and clear. `existingSecret` also avoids
  an ArgoCD OutOfSync loop: without it, the Grafana chart renders a new random password on every sync.
- **Not Sealed Secrets / SOPS / ansible-vault:** all need a key that belongs to one cluster or one
  person. A reviewer bringing up a fresh cluster would not have it, and the bring-up would break.
- **Production / with more time:** External Secrets Operator backed by Vault (or a cloud secret manager).
  Only a reference lives in Git.

---

# Operations

## D-024 · Logs
- **Decision:** Structured JSON logs to stdout only. The kubelet stores and rotates them on the node,
  and `kubectl logs` reads them from there.
- **Why:** The task does not require log storage. Files or PVCs would add complexity, and
  ReadWriteOnce volumes cannot be shared by 2 backend replicas on different nodes.
- **Limitation:** logs live only as long as the pod.
- **With more time:** Loki + Grafana Alloy (Promtail is end-of-life).

## D-025 · Frontend exposure
- **Decision:** NodePort, fixed at `30080` in values, reached from the host at
  `http://<worker>.mshome.net:30080`. A fixed port keeps the URL the same across reinstalls.
- **Why:** Meets "reachable from the host" with the fewest moving parts.
- **Not ingress-nginx:** the project is retired (no more releases or security fixes since March 2026).
- **With more time:** Ingress or Gateway API through K3s's built-in Traefik (no extra controller).

## D-026 · Observability as the bonus
- **Decision:** kube-prometheus-stack via ArgoCD. App metrics: request count, latency histogram,
  upstream (Open-Meteo) latency and errors. RED dashboard as code. A few PrometheusRule alerts.
- **Why:** The task prefers depth in one bonus. Upstream metrics answer "is it slow here or at Open-Meteo?".
- **Built in stage 9:** chart `kube-prometheus-stack` 92.17.0 in `argocd/apps/monitoring.yaml`, release
  name `monitoring`. This is the usual way to run Prometheus on Kubernetes: the Prometheus Operator, with
  each app describing its own monitoring (ServiceMonitor, PrometheusRule, dashboard ConfigMap) in its chart.
- **Lean settings for 2 small workers:** 2 days retention (1GB cap), no persistent volume, memory limits
  on every component but no CPU limits (they throttle and fire the chart's `CPUThrottlingHigh`).
  Alertmanager on but minimal: 1 replica, the chart's default `null` receiver, so alerts show in its
  UI and go nowhere. Admission webhooks off (they run as hook Jobs on every ArgoCD sync), and operator
  TLS off with them. Scraping off for controller-manager, scheduler, proxy and etcd: K3s doesn't expose
  them, and its datastore is SQLite.
- **What Prometheus scrapes:** only ServiceMonitors labelled `release: monitoring` (the chart's default
  selector), and ours selects only this release's Services, port `http`, path `/metrics`.
- **Alerts:** 5xx ratio > 5%, p95 > 2s, upstream error ratio > 10%, and backend / frontend down
  (`absent(up == 1)`, which also fires when the service is gone entirely).
- **Production / with more time:** persistent storage and 2 Prometheus replicas, long-term storage
  (Thanos or Mimir), an Alertmanager receiver (Slack, on-call), admission webhooks with cert-manager.
- **Label name `handler`:** the route label on `http_requests_total` and `http_request_duration_seconds`
  is `handler` (the name the official Prometheus client libraries use), not `endpoint`, because
  Prometheus Operator adds its own `endpoint` label to every scraped series.
- **Note:** node-exporter is a DaemonSet and also runs on the control plane. That is infrastructure,
  not an application workload, so the "no apps on the control plane" check looks at the `skywatch` namespace.

---

# Repository and workflow

## D-027 · Repository layout
- **Decision:** One monorepo. Each top-level folder answers one question:
  `apps/` what we build · `infra/` how the cluster is built · `charts/` what runs on it ·
  `argocd/` how it gets there · `docs/` why.
- **Why:** Separating app code from infrastructure is a common monorepo convention. `charts/` and
  `argocd/` stay at the root because they are the GitOps layer that CI updates and ArgoCD reads.
  The task asks for one public repo with all code, manifests, playbooks and pipelines (S1).
- **In production:** usually split. A platform repo holds ArgoCD, monitoring and anything shared; each
  app repo holds its code, its chart and its own ServiceMonitor and alerts.

## D-028 · Make as a thin menu
- **Decision:** `Makefile` targets only call scripts and playbooks.
- **Why:** A standard, self-documenting entry point, present on Linux/macOS. Logic stays in
  readable bash and Ansible. On Windows, run inside WSL with `make` installed.

## D-029 · Git workflow
- **Decision:** Stages 1–4 (app code, Dockerfiles) on a `dev` branch. At the CI stage, `dev` is
  merged into `main` through one PR, which also shows the PR checks (lint + test + build, no push).
  From then on, work goes directly to `main` with small commits, because the pipeline and ArgoCD
  both run from `main` and every push must be tested end to end.
- **Commits:** one logical change each, in Git's standard style: no type prefix, capitalized,
  imperative mood, no final period, subject under 50 characters, optional body wrapped at 72.
- **Problems:** documented in `docs/troubleshooting.md` as soon as they are solved. No GitHub Issues:
  for a one-person project they add overhead without value.
- **Why not a single PR at the end:** CI and GitOps would only be tested at the last moment.
- **Gotcha if `dev` is kept after the CI stage:** the CI bot commits tag bumps to `main`, so `dev`
  falls behind and `values.yaml` conflicts. `dev` must be updated from `main` after every merge.
- **Production:** branch protection with required PRs and reviews; the bot would push through a
  dedicated identity allowed to bypass it, or open its own PR.

## D-030 · AI-assisted work
- **Decision:** `CLAUDE.md` sets the principles and working rules. `.claude/settings.json` denies
  `git commit` and `git push`, so every commit is reviewed and made by the author.
- **Why:** The task allows AI but requires understanding every part. The instruction file explains
  what to do; the permission rule enforces it.

## D-032 · Pod security and resources
- **Decision:** Every pod runs as UID 10001 (`runAsNonRoot`), with `allowPrivilegeEscalation: false`,
  all Linux capabilities dropped, the `RuntimeDefault` seccomp profile, a read-only root filesystem,
  and no service account token. gunicorn gets a small in-memory `/tmp` for its worker heartbeat files.
- **Why:** The apps need none of these privileges, so taking them away costs nothing and limits
  what a compromised container could do. This also matches the Kubernetes "restricted" Pod Security level.
- **Resources:** requests 50m CPU / 96Mi, limits 250m CPU / 192Mi per container. Measured at
  about 43Mi of memory per pod at rest (`kubectl top`), so the limits leave room for request bursts.

## D-031 · Deferred (only if time, in this order)
1. Ingress or Gateway API through the built-in Traefik.
2. External Secrets Operator + Vault.
3. Loki + Alloy for log storage.
