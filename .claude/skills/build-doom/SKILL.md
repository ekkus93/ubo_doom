---
name: build-doom
description: Build the native libubodoom.so shared library from the vendored Doom source. Use when the user asks to build, compile, or rebuild the native Doom library.
---

Build the native Doom shared library:

1. Run `./native/scripts/build_libubodoom.sh` from the repo root. This runs `make libubodoom.so` in `third_party/DOOM-master/linuxdoom-1.10/` and copies the result to `native/out/`.
2. If the build fails on a compiler error, remember the C code must be **GNU89-compatible** (`-std=gnu89`): all locals declared at the top of a block, no C99 mid-block declarations. Fix any offending declaration and rebuild.
3. Requires system packages `build-essential` and `libasound2-dev` — if `libasound`/ALSA headers are missing, tell the user to `sudo apt install libasound2-dev`.
4. Report the path to the built `.so` (`native/out/libubodoom.so`) and whether the build succeeded.
