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
- Native C unit tests (pure logic, no engine/IWAD/device): `native/scripts/run_unit_tests.sh` (or `make test-units` in the vendored tree). Covers the Ubo-authored seams `ubo_map_key()` (`ubo_keymap.c`) and `ubo_next_owned_weapon()` (`ubo_weapon.c`), which are split out of `doom_api.c` precisely so they link without the engine. No framework — `native/test/test_ubo_units.c` is assert-style; exit code is the failure count.
- Native death/respawn regression (`libubodoom.so`): `native/scripts/run_death_repro.sh [iwad]`. Starts a **real** single-player game (`G_DeferedInitNew`), kills the player (`P_DamageMobj`), and asserts the fixed respawn behavior — engine keeps ticking while dead; FIRE while the death view is still sinking does *not* respawn (the delay); FIRE and USE both respawn once it has sunk. Links the whole engine (not just `doom_api.h`) and needs an IWAD (defaults to `$HOME/doom/doom2.wad`, audio at ALSA `null`); exit code is the failed-check count. Runner: `native/test/death_repro.c`.
- Native deployed-artifact check: `native/scripts/run_verify_deployed.sh [so] [iwad]`. `dlopen`s a **finished** `.so` (not a rebuild) and drives the same death→respawn scenario through its exported symbols — use it to confirm the shipped binary on the device (`UBO_DOOM_LIB=/home/ubo/doom/libubodoom.so native/scripts/run_verify_deployed.sh`). Resolves the `.so` from arg1→`$UBO_DOOM_LIB`→`native/out/`, IWAD from arg2→`$UBO_DOOM_IWAD`→`$HOME/doom/doom2.wad`; ALSA at `null` so it won't fight a running `ubo-app`. Runner: `native/test/verify_deployed.c`. (`death_repro.c` tests the source objects; this tests the built file.)
- Native sanitizers (memory errors / data races in `libubodoom.so`): `native/scripts/run_sanitizers.sh address|thread [ticks]` builds instrumented Doom objects + `native/test/harness.c` and stress-runs it headless (needs an IWAD; defaults to `$HOME/doom/doom2.wad`, audio at ALSA `null`). Use `thread` for the audio-thread locking, `address` for global/stack/array overruns. Note: ASan is weak for Doom's zone-allocated heap (one big `malloc`, so intra-zone overruns miss redzones). `doom_api.c` skips its SIGSEGV/SIGBUS traps under sanitizer builds so faults reach the sanitizer.

## Running on the device

- The systemd **user** unit is named `ubo-app`, but the executable is `/opt/ubo/env/bin/ubo` — **`ubo-app` is not a runnable command on v2.** Manage via `systemctl --user restart ubo-app`.
- **Logs.** Two separate sinks, and `journalctl --user -u ubo-app` is a trap — it returns "No journal files were found" because the `ubo` user can't read the journal (`Storage=volatile`, kept in RAM at `/run/log/journal`, readable only by the `adm`/`systemd-journal` groups). Use the **system** journal filtered by the user unit instead:
  - `journalctl _SYSTEMD_USER_UNIT=ubo-app.service` — full output (add `-f` to follow live, `-n 100` to tail).
  - `journalctl _SYSTEMD_USER_UNIT=ubo-app.service | grep '\[doom\]'` — Doom lines only.
  - `/opt/ubo/ubo-app.log` is **Python logging only** (the `[INFO] …` lines). The engine's native `fprintf(stdout/stderr)` — anything printed by the C code, e.g. `[doom] …` — goes to the **journal** (the process's fd 1/2 are the journald `stdout` socket), *not* to `ubo-app.log`. So to see native Doom output you must read the journal, not the file.
- Manual debug: stop the service, `source system/env/ubo_app.env.example`, then run `/opt/ubo/env/bin/ubo` (now the native stdout/stderr land in your terminal directly).
- The Python service is **symlinked** onto the device (Python edits are live), but **native changes require rebuilding and re-copying `libubodoom.so`**.
- Required env vars: `UBO_SERVICES_PATH` (colon-separated — preserve existing entries), `UBO_DOOM_LIB`, `UBO_DOOM_IWAD`. Recommended: `UBO_DOOM_CWD`, `UBO_DOOM_CONFIG` (avoid stale-config bugs).

## Conventions & gotchas

- **`memory.md` is an append-only session log.** Never overwrite or delete entries; **prepend** a new `## YYYY-MM-DDThh:mm:ss — <desc>` section at the top using the real current date.
- Commit messages follow Conventional Commits (`feat:`, `fix:`, `tidy:`, `docs:`).
- Python style: `from __future__ import annotations`, full type hints, `Final` constants, frozen dataclasses, `IntEnum`. No bare `except:`.
- BACK and HOME are owned by Ubo v2 navigation — the controller deliberately does **not** handle them.
- IWADs (`*.wad`) are not included and are gitignored — supply a legally obtained WAD.
- `.github/copilot-instructions.md` holds a longer Python/TDD policy; treat it as repo guidance, not a security boundary.
