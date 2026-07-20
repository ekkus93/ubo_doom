#!/usr/bin/env bash
# Build and run the death/respawn regression harness against libubodoom.
#
#   native/scripts/run_death_repro.sh [iwad]
#
# Starts a REAL single-player game, kills the player, and asserts the fixed
# death->respawn behaviour: engine keeps ticking while dead; FIRE while the death
# view is still sinking does NOT respawn (delay); FIRE and USE both respawn once
# the view has sunk. Exits non-zero if any check fails.
#
# Env:
#   UBO_DOOM_IWAD        IWAD to load (default: $HOME/doom/doom2.wad)
#   UBO_DOOM_ALSA_DEVICE ALSA device (default: null -- headless, no hardware)
#
# Needs a legally obtained IWAD (gitignored), like the sanitizer harness. Unlike
# the pure-logic unit tests, this links the whole engine and drives a real game.
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
HARNESS_C="${ROOT_DIR}/native/test/death_repro.c"
IWAD="${1:-${UBO_DOOM_IWAD:-$HOME/doom/doom2.wad}}"
OBJDIR="${SRC}/linux/ubo"

if [[ ! -f "$IWAD" ]]; then
  echo "ERROR: IWAD not found: $IWAD (set UBO_DOOM_IWAD or pass as arg1)"; exit 1
fi

# Ensure the (non-instrumented) engine objects exist; harness links them.
echo "=== building engine objects ==="
if ! make -C "$SRC" libubodoom.so >/dev/null 2>&1; then
  echo "build failed:"; make -C "$SRC" libubodoom.so; exit 1
fi

RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/ubodoom-death.XXXXXX")"
trap 'rm -rf "$RUNDIR"' EXIT
export UBO_DOOM_CWD="$RUNDIR"
export UBO_DOOM_CONFIG="$RUNDIR/doomrc.cfg"
export UBO_DOOM_ALSA_DEVICE="${UBO_DOOM_ALSA_DEVICE:-null}"

echo "=== compiling + linking harness ==="
if ! gcc -g -O1 -DNORMALUNIX -DLINUX -I"$SRC" \
      "$HARNESS_C" "$OBJDIR"/*.o \
      -lasound -lm -lpthread -o "$RUNDIR/death_repro"; then
  echo "harness link failed"; exit 1
fi

echo "=== running (iwad=$IWAD, alsa=$UBO_DOOM_ALSA_DEVICE) ==="
# Drop the noisy engine debug lines ([doom] ...); keep the check output.
"$RUNDIR/death_repro" "$IWAD" 2>&1 | grep -v '^\[doom\]'
RC="${PIPESTATUS[0]}"
echo "--- harness exit: $RC ---"
exit "$RC"
