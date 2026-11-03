# Troubleshooting

Problems met while building the project, added as soon as each one is solved.

Format for each entry:

```
## Short title
- **Symptom:** what was seen, with the exact error if short.
- **Cause:** why it happened.
- **Fix:** what solved it.
```

## Creating a virtual environment fails in WSL
- **Symptom:** `python3 -m venv .venv` stops with `ensurepip is not available`.
- **Cause:** Ubuntu ships the part of venv that installs pip as a separate package, and it was not installed.
- **Fix:** `sudo apt install -y python3.12-venv`, then create the venv again.

## `sudo` fails from the Claude Code `!` prefix
- **Symptom:** `sudo: a terminal is required to read the password`.
- **Cause:** the `!` prefix runs the command without a terminal, so `sudo` cannot ask for the password.
- **Fix:** run `sudo` commands in a separate WSL terminal.

## ruff reports unsorted imports in the tests
- **Symptom:** `I001 Import block is un-sorted` on `from app import app` when running
  `ruff check apps` from the repo root.
- **Cause:** from the root, ruff cannot tell that `app` is our own module, so it sorts it as a third-party package.
- **Fix:** run ruff from the service folder, as `make lint` does.

## WSL cannot reach the Multipass VMs
- **Symptom:** from WSL, `<vm>.mshome.net` resolves, but ping and SSH fail with `No route to host`.
  From Windows, the same VM answers.
- **Cause:** WSL was in `networkingMode=mirrored`, which mirrors only the physical adapters. WSL had
  no route to the Default Switch network (`172.31.208.0/20`). The WSL team confirms mirrored mode
  does not support reaching other VMs on the host (microsoft/WSL#11494).
- **Fix:** `networkingMode=nat` in `.wslconfig`, `wsl --shutdown`, then in an admin PowerShell:
  ```
  Get-NetIPInterface | Where-Object { $_.InterfaceAlias -like 'vEthernet (WSL*' -or $_.InterfaceAlias -eq 'vEthernet (Default Switch)' } | Set-NetIPInterface -Forwarding Enabled
  ```
  Forwarding resets on every host reboot, so run it again after each reboot.

## One VM still times out after the NAT fix
- **Symptom:** after the fix, a VM that runs Docker still times out, while a fresh VM works.
- **Cause:** WSL's NAT address (`172.17.245.215`) is inside the VM's Docker bridge (`172.17.0.0/16`),
  so the VM sends its replies into Docker instead of back to Windows.
- **Fix:** none needed for the cluster: its VMs run no Docker. For such a VM, change Docker's address range.

## A stopped backend shows "took too long" locally
- **Symptom:** with the backend stopped, the frontend waits the full 10s and returns 504, not an
  immediate 502 "unavailable".
- **Cause:** on this WSL setup (`networkingMode=mirrored`), a connection to any closed `127.0.0.1`
  port hangs instead of being refused, so `requests` reports a timeout. `[::1]` refuses immediately.
- **Fix:** none needed; the frontend handles both cases. To test the 502 locally, run it with
  `BACKEND_URL=http://[::1]:8000` while the backend is stopped.

## ansible-lint fails on registered variable names
- **Symptom:** `var-naming[no-role-prefix]` for `register: k3s_node_token` and `register: k3s_kubeconfig`.
- **Cause:** variables registered inside a role must start with the role's name, so roles can't
  overwrite each other's variables.
- **Fix:** renamed them `k3s_agent_node_token` and `kubeconfig_admin`.

## The kubeconfig role was left out of Git
- **Symptom:** `git add infra/` staged every role except `roles/kubeconfig/`.
- **Cause:** the `.gitignore` line `kubeconfig` matches any file or folder with that name, at any depth.
- **Fix:** `/kubeconfig`, which only matches the file `make cluster` writes in the repo root.

## Real cities show "The weather service is unavailable"
- **Symptom:** on the cluster (and earlier in Docker and locally), searches often fail with
  "unavailable", while an unknown city still gets "City not found". The backend logs
  `Open-Meteo forecast failed` or `timed out`.
- **Cause:** Open-Meteo itself. Called straight from WSL, outside Docker and Kubernetes, the forecast
  API answered `503 {"reason":"The service is overloaded"}` or did not answer within 8s, and
  geocoding hung on about every second call.
- **Fix:** none in our code: the app turns upstream errors into a clear 502 page and stays healthy,
  which is the intended behaviour (D-014, D-017). For a demo or screenshot, retry when Open-Meteo recovers.

## Metric label `endpoint` would clash with Prometheus Operator
- **Symptom:** found in the stage 9 plan review, before any dashboard was built. Queries grouped
  `by (endpoint)` would show a single value, `http`, for every route.
- **Cause:** Prometheus Operator adds an `endpoint` target label (the Service port name) to every
  series it scrapes. With the default `honorLabels: false`, the app's own `endpoint` label is renamed
  to `exported_endpoint`.
- **Fix:** renamed the app label to `handler`, the name the official Prometheus client libraries use.
  The ServiceMonitor keeps the default `honorLabels: false`.

## ArgoCD sync fails: no matches for kind "ServiceMonitor"
- **Symptom:** the `skywatch` app failed to sync with `resource mapping not found for name: "skywatch"
  ... no matches for kind "ServiceMonitor" in version "monitoring.coreos.com/v1" ... ensure CRDs are
  installed first`.
- **Cause:** the `skywatch` and `monitoring` apps sync in parallel, and the ServiceMonitor CRD comes
  with kube-prometheus-stack. ArgoCD dry-runs every resource before applying any, so one unknown kind
  failed the whole sync, Deployments included.
- **Fix:** `SkipDryRunOnMissingResource=true` on the ServiceMonitor and PrometheusRule, so the app
  deploys anyway, and a short `retry` in `argocd/apps/skywatch.yaml` that applies the two once the
  CRDs exist. The monitoring bonus can never block the app. See D-022.

## K3s API times out after installing monitoring
- **Symptom:** after ArgoCD installed kube-prometheus-stack, `kubectl` on the server timed out and
  ArgoCD stopped syncing. On `sw-server`, `free -m` showed 56 MB free and the load average was 11.
- **Cause:** the 2 GB control plane was too small. The K3s server process grew to ~1.5 GB holding the
  new CRDs, objects and watches and answering Prometheus scrapes. The VM has no swap, so it thrashed.
- **Fix:** raised `sw-server` to 3 GB (`multipass stop`, `multipass set local.sw-server.memory=3G`,
  `multipass start`) and matched `create-vms.sh`. About 1.4 GB is now available. See D-010.
