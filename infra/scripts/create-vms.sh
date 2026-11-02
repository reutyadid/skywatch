#!/usr/bin/env bash
# Creates the 3 SkyWatch VMs with Multipass (D-002). Safe to run again: existing VMs are skipped.
set -euo pipefail

# multipass.exe when run from WSL; set MULTIPASS=multipass on native Linux or macOS.
MULTIPASS="${MULTIPASS:-multipass.exe}"
IMAGE="24.04"
LAUNCH_TIMEOUT="${LAUNCH_TIMEOUT:-600}"
SSH_PUBLIC_KEY_FILE="${SSH_PUBLIC_KEY_FILE:-$HOME/.ssh/id_ed25519.pub}"

# Resolve symlinks, so the script finds cloud-init/ from any working directory.
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CLOUD_INIT="$SCRIPT_DIR/../cloud-init/base.yaml"
PLACEHOLDER="__SSH_PUBLIC_KEY__"

# name, vCPUs, memory, disk (D-010)
VMS=(
  "sw-server 2 2G 10G"
  "sw-worker1 2 3584M 20G"
  "sw-worker2 2 3584M 20G"
)

fail() {
  echo "Error: $*" >&2
  exit 1
}

# All checks run before the first launch: a VM created without the key would be skipped on
# every later run, so it would never be fixed.

command -v "$MULTIPASS" > /dev/null || fail "Multipass not found: $MULTIPASS"

[[ "$LAUNCH_TIMEOUT" =~ ^[0-9]+$ ]] || fail "LAUNCH_TIMEOUT must be a number of seconds"

[[ -f "$CLOUD_INIT" ]] || fail "cloud-init file not found: $CLOUD_INIT"
template="$(< "$CLOUD_INIT")"
[[ "$template" == *"$PLACEHOLDER"* ]] || fail "$PLACEHOLDER not found in $CLOUD_INIT"

if [[ ! -f "$SSH_PUBLIC_KEY_FILE" ]]; then
  fail "SSH public key not found: $SSH_PUBLIC_KEY_FILE (create one with: ssh-keygen -t ed25519)"
fi
ssh_public_key="$(< "$SSH_PUBLIC_KEY_FILE")"
# A key file saved on Windows can end in \r, which would end up inside authorized_keys.
ssh_public_key="${ssh_public_key%$'\r'}"
[[ -n "$ssh_public_key" ]] || fail "SSH public key file is empty: $SSH_PUBLIC_KEY_FILE"
[[ "$ssh_public_key" != *$'\n'* ]] || fail "SSH public key file must hold one key: $SSH_PUBLIC_KEY_FILE"

# Bash, not sed: the key comment may contain | & or \. The inner quotes keep & literal in bash 5.2+.
cloud_init="${template//"$PLACEHOLDER"/"$ssh_public_key"}"

# Without this, a stopped daemon would look like "VM missing" and trigger launches.
"$MULTIPASS" list > /dev/null 2>&1 || fail "Multipass is not responding ($MULTIPASS list failed)"

for vm in "${VMS[@]}"; do
  read -r name cpus memory disk <<< "$vm"

  if "$MULTIPASS" info "$name" > /dev/null 2>&1; then
    echo "$name already exists, skipping"
    continue
  fi

  echo "Creating $name"
  # multipass.exe is a Windows program, so the cloud-init goes in on stdin, not as a WSL path.
  printf '%s\n' "$cloud_init" |
    "$MULTIPASS" launch "$IMAGE" --name "$name" --cpus "$cpus" --memory "$memory" \
      --disk "$disk" --timeout "$LAUNCH_TIMEOUT" --cloud-init -
done

"$MULTIPASS" list
