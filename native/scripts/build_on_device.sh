#!/usr/bin/env bash
set -euo pipefail
#
# build_on_device.sh — sync Doom sources to a remote host, build libubodoom.so
# natively on that host, then install the .so and service files.
#
# No local compiler or cross-toolchain needed.
#
# Prerequisites on the remote device:
#   sudo apt install build-essential libasound2-dev
#
# Usage:
#   ./native/scripts/build_on_device.sh <user@host> [remote_base]
#
# Arguments:
#   user@host     SSH target (e.g. debian@ubo-rd)
#   remote_base   Base directory on device (default: $HOME)
#
# What it does:
#   1. Checks that gcc, make and libasound2-dev are present on the device.
#   2. Rsyncs third_party/DOOM-master/linuxdoom-1.10 to ~/doom-build/ on the device.
#   3. Runs `make libubodoom.so` on the device.
#   4. Copies the resulting .so to <remote_base>/doom/libubodoom.so.
#   5. Rsyncs ubo_service/070-doom to <remote_base>/ubo_services/070-doom.
#

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <user@host> [remote_base]"
  echo "Example: $0 debian@ubo-rd"
  exit 1
fi

REMOTE="$1"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOOM_SRC="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
SERVICE_LOCAL="${ROOT_DIR}/ubo_service/070-doom"

# Resolve $HOME on the remote once so we can build paths reliably.
echo "==> Resolving remote home dir..."
REMOTE_HOME=$(ssh "${REMOTE}" 'echo $HOME')
REMOTE_BASE="${2:-${REMOTE_HOME}}"
REMOTE_BUILD_DIR="${REMOTE_HOME}/doom-build/linuxdoom-1.10"

echo "    Remote home : ${REMOTE_HOME}"
echo "    Install base: ${REMOTE_BASE}"
echo "    Build dir   : ${REMOTE_BUILD_DIR}"
echo ""

# ── 1. Dependency check ────────────────────────────────────────────────────────
echo "==> Checking remote build dependencies..."
ssh "${REMOTE}" bash <<'ENDSSH'
missing=()
command -v gcc  >/dev/null 2>&1 || missing+=(gcc)
command -v make >/dev/null 2>&1 || missing+=(make)
if ! dpkg -s libasound2-dev >/dev/null 2>&1; then
  missing+=(libasound2-dev)
fi
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: missing packages on device: ${missing[*]}"
  echo "Fix with: sudo apt install build-essential libasound2-dev"
  exit 1
fi
echo "    gcc, make, libasound2-dev — OK"
ENDSSH

# ── 2. Sync sources ─────────────────────────────────────────────────────────────
echo ""
echo "==> Syncing sources to ${REMOTE}:${REMOTE_BUILD_DIR} ..."
ssh "${REMOTE}" "mkdir -p '${REMOTE_BUILD_DIR}'"
rsync -av --delete "${DOOM_SRC}/" "${REMOTE}:${REMOTE_BUILD_DIR}/"

# ── 3. Build ────────────────────────────────────────────────────────────────────
echo ""
echo "==> Building libubodoom.so on ${REMOTE} ..."
ssh "${REMOTE}" "cd '${REMOTE_BUILD_DIR}' && make libubodoom.so"

# ── 4. Install .so ──────────────────────────────────────────────────────────────
echo ""
echo "==> Installing libubodoom.so to ${REMOTE_BASE}/doom/ ..."
ssh "${REMOTE}" "mkdir -p '${REMOTE_BASE}/doom'"
ssh "${REMOTE}" "cp -v '${REMOTE_BUILD_DIR}/libubodoom.so' '${REMOTE_BASE}/doom/libubodoom.so'"

# ── 5. Install service files ────────────────────────────────────────────────────
echo ""
echo "==> Syncing service files to ${REMOTE_BASE}/ubo_services/070-doom/ ..."
ssh "${REMOTE}" "mkdir -p '${REMOTE_BASE}/ubo_services/070-doom'"
rsync -av --delete "${SERVICE_LOCAL}/" "${REMOTE}:${REMOTE_BASE}/ubo_services/070-doom/"

echo ""
echo "Done."
echo "libubodoom.so built natively on ${REMOTE} and installed to ${REMOTE_BASE}/doom/."
echo ""
echo "Reminder: copy your IWAD to ${REMOTE_BASE}/doom/ and configure env vars."
echo "See system/env/ubo_app.env.example for the required settings."
