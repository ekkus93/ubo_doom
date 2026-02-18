#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <user@host> [remote_base]"
  echo "Example: $0 debian@ubo-rd"
  exit 1
fi

REMOTE="$1"
REMOTE_BASE="${2:-\$HOME}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
LIB_LOCAL="${ROOT_DIR}/native/out/libubodoom.so"
SERVICE_LOCAL="${ROOT_DIR}/ubo_service/070-doom"

if [[ ! -f "${LIB_LOCAL}" ]]; then
  echo "ERROR: ${LIB_LOCAL} not found. Run build_libubodoom.sh first."
  exit 1
fi

echo "Creating remote dirs..."
ssh "${REMOTE}" "mkdir -p ${REMOTE_BASE}/doom ${REMOTE_BASE}/ubo_services/070-doom"

echo "Copying libubodoom.so..."
scp "${LIB_LOCAL}" "${REMOTE}:${REMOTE_BASE}/doom/libubodoom.so"

echo "Copying service folder..."
rsync -av --delete "${SERVICE_LOCAL}/" "${REMOTE}:${REMOTE_BASE}/ubo_services/070-doom/"

echo "Done."
echo "Reminder: copy your IWAD to ${REMOTE_BASE}/doom and set env vars (see system/env/ubo_app.env.example)."
