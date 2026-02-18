#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOOM_DIR="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
PATCH_FILE="${ROOT_DIR}/patches/ubodoom_linuxdoom110.patch"
OUT_DIR="${ROOT_DIR}/native/out"

mkdir -p "${OUT_DIR}"

if [[ ! -d "${DOOM_DIR}" ]]; then
  echo "ERROR: Doom source not found at: ${DOOM_DIR}"
  echo "Place linuxdoom-1.10 sources there (see README)."
  exit 1
fi

# Apply patch (idempotent-ish)
cd "${DOOM_DIR}"
if patch -p1 --dry-run < "${PATCH_FILE}" >/dev/null 2>&1; then
  echo "Applying patch..."
  patch -p1 < "${PATCH_FILE}"
else
  echo "Patch appears already applied (or does not apply cleanly). Continuing..."
fi

echo "Building libubodoom.so..."
make libubodoom.so

cp -v "${DOOM_DIR}/libubodoom.so" "${OUT_DIR}/libubodoom.so"
echo "OK: ${OUT_DIR}/libubodoom.so"
