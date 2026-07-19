#!/usr/bin/env bash
# Build the Doom objects + the stress harness under a sanitizer and run it
# headless, to check libubodoom for memory errors (ASan) and data races (TSan).
#
#   native/scripts/run_sanitizers.sh thread|address [ticks]
#
# Env:
#   UBO_DOOM_IWAD        IWAD to load (default: $HOME/doom/doom2.wad)
#   UBO_DOOM_ALSA_DEVICE ALSA device (default: null — audio thread runs full-speed,
#                        max contention, no real hardware needed)
#
# Notes:
# - ASan catches overruns of Doom's global/static/stack arrays (channels[],
#   mixbuffer[], sprnames[], ...). It is weak for Doom's zone-allocated heap,
#   because the whole zone is one malloc and intra-zone overruns don't cross
#   redzones. TSan is the tool for the locking/data-race questions.
# - doom_api.c does NOT trap SIGSEGV/SIGBUS under a sanitizer build (see
#   UBO_SIGACTION), so faults reach the sanitizer with a symbolized report.
set -u

SAN="${1:-thread}"
TICKS="${2:-${TICKS:-2000}}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"
HARNESS_C="${ROOT_DIR}/native/test/harness.c"
IWAD="${UBO_DOOM_IWAD:-$HOME/doom/doom2.wad}"

case "$SAN" in
  thread)  FSAN="-fsanitize=thread";  OBJDIR="linux/ubo_tsan"; TAG="TSAN" ;;
  address) FSAN="-fsanitize=address"; OBJDIR="linux/ubo_asan"; TAG="ASAN" ;;
  *) echo "usage: $0 thread|address [ticks]"; exit 2 ;;
esac

if [[ ! -f "$IWAD" ]]; then
  echo "ERROR: IWAD not found: $IWAD (set UBO_DOOM_IWAD)"; exit 1
fi

# Throwaway cwd/config; route audio at the ALSA null device by default.
RUNDIR="$(mktemp -d "${TMPDIR:-/tmp}/ubodoom-san-${SAN}.XXXXXX")"
trap 'rm -rf "$RUNDIR"' EXIT
export UBO_DOOM_CWD="$RUNDIR"
export UBO_DOOM_CONFIG="$RUNDIR/doomrc.cfg"
export UBO_DOOM_ALSA_DEVICE="${UBO_DOOM_ALSA_DEVICE:-null}"

SANFLAGS="$FSAN -g -O1 -fno-omit-frame-pointer -fPIC -std=gnu89 -DNORMALUNIX -DLINUX"

echo "=== [$TAG] compiling instrumented Doom objects ($OBJDIR) ==="
if ! make -C "$SRC" libubodoom.so \
      UBO_O="$OBJDIR" \
      UBO_CFLAGS="$SANFLAGS" \
      UBO_LIBS="-lasound -lm -lpthread $FSAN" >"$RUNDIR/build.log" 2>&1; then
  echo "build failed:"; cat "$RUNDIR/build.log"; exit 1
fi
# We link the harness against the instrumented .o files directly; the .so that
# `make` also produced is instrumented — discard it so it can't be deployed.
rm -f "$SRC/libubodoom.so"

echo "=== [$TAG] compiling + linking harness ==="
if ! gcc $FSAN -g -O1 -fno-omit-frame-pointer -I"$SRC" \
      "$HARNESS_C" "$SRC/$OBJDIR"/*.o \
      -lasound -lm -lpthread -o "$RUNDIR/harness" >>"$RUNDIR/build.log" 2>&1; then
  echo "harness link failed:"; cat "$RUNDIR/build.log"; exit 1
fi

echo "=== [$TAG] running harness ($TICKS ticks, iwad=$IWAD, alsa=$UBO_DOOM_ALSA_DEVICE) ==="
if [ "$SAN" = thread ]; then
  export TSAN_OPTIONS="halt_on_error=0 second_deadlock_stack=1 history_size=7 report_signal_unsafe=0"
else
  # doom_api.c installs no SIGSEGV/SIGBUS handler under a sanitizer, but keep
  # allow_user_segv_handler on for safety; skip leak detection (zone is one blob).
  export ASAN_OPTIONS="halt_on_error=0 allow_user_segv_handler=1 detect_leaks=0 abort_on_error=0"
fi

LOG="$RUNDIR/sanitizer.log"
"$RUNDIR/harness" "$IWAD" "$TICKS" >"$RUNDIR/stdout.log" 2>"$LOG"
RC=$?

echo "--- harness exit: $RC ---"
if grep -qiE 'ThreadSanitizer|AddressSanitizer|data race|buffer-overflow|use-after|SEGV|lock-order|heap-use' "$LOG"; then
  echo "=== [$TAG] SANITIZER FINDINGS ==="
  cat "$LOG"
  exit 1
fi
echo "=== [$TAG] clean — no sanitizer warnings ==="
tail -3 "$LOG"
