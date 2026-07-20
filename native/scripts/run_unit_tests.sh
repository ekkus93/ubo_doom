#!/usr/bin/env bash
# Build and run the Ubo Doom pure-logic C unit tests.
#
#   native/scripts/run_unit_tests.sh
#
# These link only ubo_keymap.c + ubo_weapon.c with native/test/test_ubo_units.c
# -- no engine objects, no zone heap, no IWAD, no device. Fast and hermetic;
# safe to run anywhere the toolchain is present. Exits non-zero on any failed
# check. For the concurrency/memory stress path, see run_sanitizers.sh instead.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SRC="${ROOT_DIR}/third_party/DOOM-master/linuxdoom-1.10"

exec make -C "$SRC" test-units
