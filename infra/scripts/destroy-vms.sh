#!/usr/bin/env bash
# Deletes the 3 SkyWatch VMs, and only those. Safe to run again: missing VMs are skipped.
set -euo pipefail

MULTIPASS="multipass.exe"
VMS=(sw-server sw-worker1 sw-worker2)

for name in "${VMS[@]}"; do
  if "$MULTIPASS" info "$name" > /dev/null 2>&1; then
    echo "Deleting $name"
    "$MULTIPASS" delete --purge "$name"
  fi
  # A recreated VM gets a new SSH host key, so forget the old one.
  ssh-keygen -R "$name.mshome.net" > /dev/null 2>&1 || true
done

"$MULTIPASS" list
