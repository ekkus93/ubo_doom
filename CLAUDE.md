# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

A headless port of id Software's `linuxdoom-1.10` that runs as an external service on the **Ubo Pod v2** (Raspberry Pi device, 240×240 ST7789 LCD, keypad, wm8960 sound card). The C code builds into a shared library `libubodoom.so` that renders Doom into an in-memory 320×200 RGBA framebuffer. A Python service (`ubo_service/070-doom/`) loads the `.so` via `ctypes`, downscales frames to 240×240 RGB888, and publishes them through Ubo's `frame_stream` renderer. The service does **not** import Kivy or touch the ST7789 directly.

## Architecture

- `third_party/DOOM-master/linuxdoom-1.10/` — vendored Doom, **pre-patched in place**. Ubo-specific files: `doom_api.c/.h` (embedding API), `i_video_ubo.c` (headless video backend), `i_sound_alsa.c` (ALSA sound). The build swaps original `i_video.o`/`i_sound.o` for these.
- `ubo_service/070-doom/` — the Ubo external service (`070-` prefix is Ubo's load-order convention). `setup.py` (integration + tick thread), `doom_controller.py` (input state machine), `doom_video.py` (frame scaling), `native/doom_lib.py` (ctypes wrapper).
- `native/scripts/` — build/install scripts. `native/out/` — build output (gitignored).

## Build

- Build the native lib: `./native/scripts/build_libubodoom.sh` (runs `make libubodoom.so` in the vendored tree, copies `.so` to `native/out/`).
- Requires system packages `build-essential` and `libasound2-dev`.
- **C code must be GNU89-compatible** (`-std=gnu89`): declare all locals at the top of a block, no C99 mid-block declarations. Breaking this fails the build.
- On-device build/install helpers (SSH): `native/scripts/build_on_device.sh <user@host>`, `install_to_device.sh <user@host>`.

## Test

- Dev tooling (pytest, numpy, ruff) lives in a repo-root venv: `.venv/` (gitignored). Use `.venv/bin/python` and `.venv/bin/ruff` — the Pi's system Python is externally managed (PEP 668) and can't install these.
- pytest suite (pure-Python, no `.so` or device needed): `cd ubo_service/070-doom && ../../.venv/bin/python -m pytest`.
- Config lives in `ubo_service/070-doom/pyproject.toml` (`pythonpath=["."]`, so tests use bare imports like `from doom_controller import ...`).
- Quick compile check: `.venv/bin/python -m compileall -q ubo_service/070-doom`.
- Lint the service (ruff, config in the service `pyproject.toml`): `cd ubo_service/070-doom && ../../.venv/bin/ruff check .`.
- Native sanitizers (memory errors / data races in `libubodoom.so`): `native/scripts/run_sanitizers.sh address|thread [ticks]` builds instrumented Doom objects + `native/test/harness.c` and stress-runs it headless (needs an IWAD; defaults to `$HOME/doom/doom2.wad`, audio at ALSA `null`). Use `thread` for the audio-thread locking, `address` for global/stack/array overruns. Note: ASan is weak for Doom's zone-allocated heap (one big `malloc`, so intra-zone overruns miss redzones). `doom_api.c` skips its SIGSEGV/SIGBUS traps under sanitizer builds so faults reach the sanitizer.

## Running on the device

- The systemd **user** unit is named `ubo-app`, but the executable is `/opt/ubo/env/bin/ubo` — **`ubo-app` is not a runnable command on v2.** Manage via `systemctl --user restart ubo-app`, logs via `journalctl --user -u ubo-app`.
- Manual debug: stop the service, `source system/env/ubo_app.env.example`, then run `/opt/ubo/env/bin/ubo`.
- The Python service is **symlinked** onto the device (Python edits are live), but **native changes require rebuilding and re-copying `libubodoom.so`**.
- Required env vars: `UBO_SERVICES_PATH` (colon-separated — preserve existing entries), `UBO_DOOM_LIB`, `UBO_DOOM_IWAD`. Recommended: `UBO_DOOM_CWD`, `UBO_DOOM_CONFIG` (avoid stale-config bugs).

## Conventions & gotchas

- **`memory.md` is an append-only session log.** Never overwrite or delete entries; **prepend** a new `## YYYY-MM-DDThh:mm:ss — <desc>` section at the top using the real current date.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `tidy:`, `docs:`).
- Python style: `from __future__ import annotations`, full type hints, `Final` constants, frozen dataclasses, `IntEnum`. No bare `except:`.
- BACK and HOME are owned by Ubo v2 navigation — the controller deliberately does **not** handle them.
- IWADs (`*.wad`) are not included and are gitignored — supply a legally obtained WAD.
- `.github/copilot-instructions.md` holds a longer Python/TDD policy; treat it as repo guidance, not a security boundary.
