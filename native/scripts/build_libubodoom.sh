#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DOOM_DIR="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
OUT_DIR="${ROOT_DIR}/native/out"

mkdir -p "${OUT_DIR}"

if [[ ! -d "${DOOM_DIR}" ]]; then
  echo "ERROR: Doom source not found at: ${DOOM_DIR}"
  echo "Place linuxdoom-1.10 sources there (see README)."
  exit 1
fi

# Source files are pre-patched directly in third_party/
cd "${DOOM_DIR}"

echo "Building libubodoom.so..."
make libubodoom.so

cp -v "${DOOM_DIR}/libubodoom.so" "${OUT_DIR}/libubodoom.so"
echo "OK: ${OUT_DIR}/libubodoom.so"
