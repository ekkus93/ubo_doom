#!/usr/bin/env bash
# Verify a finished libubodoom.so by dlopen'ing the actual .so file and driving
# the real death -> respawn behaviour through its exported symbols.
#
#   native/scripts/run_verify_deployed.sh [so] [iwad]
#
# Unlike run_death_repro.sh (which links freshly built objects = tests the
# source), this tests a SHIPPED binary. Point it at the file the device service
# loads to confirm the deployed artifact:
#
#   UBO_DOOM_LIB=/home/ubo/doom/libubodoom.so native/scripts/run_verify_deployed.sh
#
# Resolution order for the .so:  arg1 -> $UBO_DOOM_LIB -> native/out/libubodoom.so
# Resolution order for the IWAD: arg2 -> $UBO_DOOM_IWAD -> $HOME/doom/doom2.wad
#
# Env:
#   UBO_DOOM_ALSA_DEVICE  ALSA device (default: null -- headless, avoids fighting
#                         a running ubo-app for the sound card)
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
VERIFY_C="${ROOT_DIR}/native/test/verify_deployed.c"

SO="${1:-${UBO_DOOM_LIB:-${ROOT_DIR}/native/out/libubodoom.so}}"
IWAD="${2:-${UBO_DOOM_IWAD:-$HOME/doom/doom2.wad}}"

if [[ ! -f "$SO" ]];   then echo "ERROR: .so not found: $SO (arg1 or UBO_DOOM_LIB)"; exit 1; fi
if [[ ! -f "$IWAD" ]]; then echo "ERROR: IWAD not found: $IWAD (arg2 or UBO_DOOM_IWAD)"; exit 1; fi

RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/ubodoom-verify.XXXXXX")"
trap 'rm -rf "$RUNDIR"' EXIT
export UBO_DOOM_CWD="$RUNDIR"
export UBO_DOOM_CONFIG="$RUNDIR/doomrc.cfg"
export UBO_DOOM_ALSA_DEVICE="${UBO_DOOM_ALSA_DEVICE:-null}"

# The verifier only needs Doom headers for types; it dlopen's the .so (-ldl),
# it does not link engine objects.
echo "=== compiling verifier ==="
if ! gcc -g -O1 -DNORMALUNIX -DLINUX -I"$SRC" "$VERIFY_C" -ldl -o "$RUNDIR/verify_deployed"; then
  echo "verifier build failed"; exit 1
fi

echo "=== running (so=$SO, iwad=$IWAD, alsa=$UBO_DOOM_ALSA_DEVICE) ==="
"$RUNDIR/verify_deployed" "$SO" "$IWAD" 2>&1 | grep -v '^\[doom\]'
RC="${PIPESTATUS[0]}"
echo "--- verifier exit: $RC ---"
exit "$RC"
