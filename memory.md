# Project Memory — ubo_doom

<!-- Append-only log. NEVER delete or overwrite entries. Prepend new sessions at the top. -->

---

## 2026-07-20T15:45:36 — Added pure-logic C unit tests for the Ubo seams

### What
First C-side unit tests. Extracted the two Ubo-authored bits of logic that are
easy to break and expensive to catch on-device into dependency-free translation
units, then tested them without linking the engine:
- `ubo_keymap.c` / `ubo_keymap.h` — `ubo_map_key()` (was `static map_ubo_key` in
  `doom_api.c`). Pins the stable-key→doomkey table: USE→space (the respawn/use
  path), FIRE→KEY_RCTRL (never KEY_ENTER, which HU_MSGREFRESH eats), etc.
- `ubo_weapon.c` / `ubo_weapon.h` — `ubo_next_owned_weapon(cur, n, owned)`, the
  cyclic weapon-cycle scan pulled out of `ubo_weapon_next()`. Off-by-one prone;
  now tested for wrap, skip-unowned, single-owned no-op, none-owned.

`doom_api.c` now delegates to both (keeps the `g_inited`/`players[]` glue; passes
`(const int*)p->weaponowned` since `boolean` is an int-sized enum here).

### How to run
`native/scripts/run_unit_tests.sh` (or `make test-units` in the vendored tree).
Runner: `native/test/test_ubo_units.c` — no framework, assert-style, exit code =
failure count. 21 checks, all pass. Makefile links the two new .o into
`libubodoom.so`; `.so` rebuilds clean with `-Wall`, no warnings. These are the
right tool for pure logic; the death→reborn→level-reload path and audio-thread
locking stay with `run_sanitizers.sh` (stateful/concurrent).

---

## 2026-07-19T21:xx — Sanitizer pass (ASan + TSan): verified locking, fixed 2 real bugs

### Setup
- Built instrumented Doom objects + a headless C stress harness
  (`scratchpad/harness.c`, `scratchpad/run_sanitizers.sh`) that ticks the engine
  through the attract demos (which shoot → lots of S_StartSound → addsfx) with the
  audio thread pointed at ALSA `null` (spins full-speed = max contention). Dev box
  has all IWADs in ~/doom, gcc 12, 3.7 GB RAM — ASan+TSan both usable here.
- Note: ASan is weak for Doom-INTERNAL heap bugs (custom zone allocator = one big
  malloc, so intra-zone overruns don't cross redzones), but DOES catch overruns of
  true globals/statics/stack. TSan is the right tool for the locking question.

### Prerequisite fix — engine was swallowing sanitizer faults
- `doom_api.c` installs SIGSEGV/SIGBUS handlers that longjmp; they intercepted the
  faults ASan/TSan want to report. Added `UBO_SIGACTION()` macro: under
  `__SANITIZE_ADDRESS__`/`__SANITIZE_THREAD__` it's a no-op (don't trap), else it's
  plain `sigaction()`. All install/restore sites now route through it. No-op change
  in normal builds.

### Bug 1 (real, pre-existing) — global-buffer-overflow reading `sprnames`
- ASan: `R_InitSpriteDefs` (r_things.c:191) scans `while (*check != NULL)` but
  `sprnames` (info.c:40) was `[NUMSPRITES]` with 138 names and NO NULL terminator →
  reads 1 entry past the array. Benign-by-luck in normal builds (adjacent global
  happened to read as non-crashing), but a genuine OOB and a hard SIGSEGV under
  TSan's memory layout (that was the first TSan crash). This is a latent VANILLA
  bug. Fix: `sprnames[NUMSPRITES + 1]` with a trailing `NULL` (info.c + info.h).

### Bug 2 (real) — data race on the audio stop-flag
- TSan: `audio_running` written by main thread in `I_ShutdownSound` vs read by the
  audio thread loop, unsynchronized. `volatile` ≠ thread-safe. Fix: plain `int` with
  GCC atomic builtins `__atomic_load_n/ store_n` (ACQUIRE/RELEASE) via
  `AUDIO_RUNNING_LOAD()/STORE()` macros at all 6 sites. (gnu89-compatible.)

### KEY RESULT — the audio locking is correct
- After the two fixes, both ASan and TSan run **clean** (0 warnings) through 1200
  AND 3000 ticks with the audio thread hammering. TSan found NO race on the mixer
  channel arrays (`channels[]`, `channelsend[]`, vol lookups) or `mixbuffer` — the
  `audio_mutex` around `addsfx` vs `I_UpdateSound` from the prior audio-thread commit
  is sufficient. The user's "locking issues" were the blocking-ALSA-write freeze
  (already fixed); no additional lock bug exists in the audio path.
- Normal `libubodoom.so` rebuilt with all fixes → native/out (needs redeploy).
- Harness/scripts live in scratchpad (not committed); offered to add reusable
  `native/scripts/run_sanitizers.sh` + `native/test/harness.c` if wanted.

## 2026-07-19T21:04:41 — Decoupled audio onto its own thread (supersedes drop-on-full)

### Why (follow-up to the freeze fix below)
- The earlier fix (non-blocking write + drop chunk on -EAGAIN) stopped the freeze
  but, because the engine over-produces audio (~1.39× real-time), it dropped ~1/4
  of chunks → choppy SFX. User asked for the proper decoupled version.

### Design — dedicated audio output thread (`i_sound_alsa.c`)
- Sound **mixing + the blocking ALSA write** now run on their own pthread
  (`ubo_audio_thread`): loop = mix one 512-frame chunk under `audio_mutex`, then
  blocking `snd_pcm_writei` OUTSIDE the lock. The blocking write paces the loop to
  real-time (~21.5 chunks/s), so audio plays cleanly with **no drops** and the
  game/render thread never touches ALSA.
- Device kept in **blocking** mode (reverted the non-blocking change); blocking is
  now safe because it only stalls the audio thread, never the game.
- Thread-safety: the low-level mixer channel arrays (`channels[]`, `channelsend[]`,
  vol lookups) are written by the game thread only in `addsfx()` and read/advanced
  by the audio thread only in `I_UpdateSound()`. `addsfx()` now takes `audio_mutex`
  (unlocks at all 3 exits incl. the two I_Error paths). `I_StartSound`→`addsfx` is
  the sole game-thread mutator; `I_StopSound` is a no-op; `I_SoundIsPlaying` only
  reads gametic — so those need no lock.
- `doom_tick()` (doom_api.c) no longer calls `I_UpdateSound()`/`I_SubmitSound()`.
  `I_SubmitSound()` is now a no-op stub. (`d_main.c`'s copies live in D_DoomLoop,
  which library mode never enters.)
- Lifecycle: thread spawned at end of `I_InitSound` (`audio_running=1` +
  `pthread_create`); `I_ShutdownSound` sets `audio_running=0`, `snd_pcm_drop` to
  abort the in-flight blocking write, `pthread_join`, then close. `ubo_write_chunk`
  guards its recover/retry with `audio_running` so shutdown can't re-block.
- Makefile: `UBO_LIBS += -lpthread`. Added `#include <pthread.h>`, `<errno.h>`.
- Built clean (only pre-existing `rcsid` warning); `-lpthread` on link line; pthread
  syms bind to glibc; 33 Python tests still pass. New `.so` in `native/out/` (also
  bundles usergame + weapon-next). **Requires rebuild+redeploy of libubodoom.so.**
- Caveat / future: if the wm8960 hw pointer ever wedges, the audio thread blocks
  (audio dies until restart) but the game keeps running. A watchdog on the write
  could recover audio automatically — not done.

## 2026-07-19T21:04:40 — Fix long-session freeze: blocking ALSA write stalled the render thread

### Symptom
- User: "Doom plays ok for a while but after a while it crashes… I think there's a
  memory leak." On follow-up: **not** an app-wide OOM — Doom *freezes*, then "after
  pressing some buttons it sort of works, then Doom resets." One continuous session.

### Root cause (NOT a leak)
- Ruled out leaks: Python service has no unbounded growth (input queue drained every
  tick, `_held` bounded, frame bytes GC'd after dispatch); native per-frame paths use
  static buffers; sound is pre-cached at init; zone heap is fixed 32 MB. (The only
  real leak is `doom_reset()` leaking the 32 MB zone per crash/reopen cycle — not this
  bug, since the report is a single session.)
- Actual cause: `I_SubmitSound()` (`i_sound_alsa.c`) runs on the **same thread that
  renders**, and the PCM was opened in **blocking** mode (`snd_pcm_open(..., 0)`). The
  engine mixes one 512-frame chunk per game tic = 512/11025 ≈ 46 ms of audio, and the
  tick loop targets 30 fps ⇒ ~1.39× real-time audio production. When the wm8960 ring
  buffer saturates (or the hw pointer stalls), `snd_pcm_writei` **blocks the render
  thread** → screen freezes until the write unblocks/errors → lurch forward / "reset".
- Vanilla linuxdoom avoided this by running sound in a **separate forked `sndserver`
  process**; this port made it synchronous/inline, so audio back-pressures the game.

### Fix (native — MUST rebuild + redeploy libubodoom.so)
- `i_sound_alsa.c`: after `snd_pcm_set_params`, call `snd_pcm_nonblock(audio_pcm, 1)`.
- Rewrote `I_SubmitSound`: non-blocking `snd_pcm_writei`; on `-EAGAIN` (buffer full)
  **drop the 512-frame chunk** and return; on other errors `snd_pcm_recover` + one
  non-blocking retry; partial writes not retried. The render thread now never blocks
  in ALSA. Added `#include <errno.h>`.
- Tradeoff: because we still over-produce audio, ~1/4 of chunks get dropped → slightly
  choppy SFX. Acceptable vs. freezing. A fuller fix would decouple audio onto its own
  thread with a real-time-paced ring buffer (future work).
- Built clean via `./native/scripts/build_libubodoom.sh` (only the pre-existing unused
  `rcsid` warning). New `.so` in `native/out/` — bundles the earlier undeployed
  usergame + weapon-next native changes too, so one redeploy covers everything.

## 2026-07-19T16:22:06 — Fix "can't start game": demo misdetected as gameplay + turn-reversal

### Root cause (start-game bug)
- On the Ubo v2 controller, pressing RIGHT/FIRE (L3) at the title screen was
  supposed to send ESCAPE to open the Doom menu (the only way to start a game on
  v2, since BACK is owned by Ubo). Instead it often sent RIGHT (turn), so the menu
  never opened.
- Reason: the attract-loop demos run at `gamestate == GS_LEVEL` with
  `usergame == false` / `demoplayback == true` (see `g_game.c:1185`, `1644-1645`).
  `DoomController.update_game_state` decided "in a level" from gamestate alone, so
  a playing demo counted as gameplay → `btn_l3` took the in-level branch (turn
  right) instead of the title/demo branch (ESCAPE). Intermittent because the title
  screen alternates static title page (GS_DEMOSCREEN, worked) and demo (GS_LEVEL,
  broke).

### Fix (spans native + Python — native lib MUST be redeployed)
- `doom_api.c` / `doom_api.h`: added `int doom_get_usergame(void)` exposing
  `usergame` (already extern in `doomstat.h`).
- `native/doom_lib.py`: bound the symbol; `usergame()` method; tolerant of a stale
  `.so` via `has_usergame` (falls back to True = old behavior, no crash).
- `doom_controller.py`: `update_game_state(..., usergame)` →
  `in_level = alive and usergame and gamestate == GS_LEVEL and not menu_active`.
- `setup.py`: passes `doom.usergame()` each tick; logs a warning if the loaded
  `.so` lacks the accessor.
- Test: `test_attract_demo_opens_menu_not_turn`.

### Also fixed (pure Python, live on restart)
- Turn-reversal lag: added `LEFT↔RIGHT` to `_OPPOSITE` in `setup.py` so a quick
  reverse-turn releases the still-held opposite turn key (12-tick hold) first.
  Test: `test_reverse_turn_releases_opposite_turn_key`.

### Platform finding (why old BACK behavior can't be restored on v2)
- Ubo v2's core `000-keypad` reducer maps L1/L2/L3 → `MenuChooseByIndexEvent(0/1/2)`,
  UP/DOWN → `ApplicationScrollEvent`, and **BACK (released alone) →
  `MenuGoBackAction()` unconditionally** (no `on_application` gate). All HOME+Lx /
  BACK+Lx combos are claimed by the platform. So the app gets exactly 5 inputs
  (UP, DOWN, L1, L2, L3); the old 6th button (BACK = fire/select/menu) is gone.
  ALT mode exists to multiplex fire onto L3. User chose to keep the v2 ALT-mode
  model rather than patch the platform.
- `docs/CONTROLS.md` rewritten to the real v2 scheme (was still describing the
  pre-v2 BACK-based scheme).

### Status / TODO
- 28 pytest pass, ruff clean, `.so` rebuilds and exports `doom_get_usergame`.
- **Pending: redeploy `native/out/libubodoom.so` → device `~/doom/libubodoom.so`
  and restart `ubo-app`.** Until then the service logs "lacks doom_get_usergame"
  and keeps the broken-start behavior.

---

## 2026-02-23T16:46:08 — Final docs consistency pass (architecture + troubleshooting)

### What was done
- Updated `docs/ARCHITECTURE.md`:
  - clarified input pipeline to reflect `DoomController` as the routing state machine
  - added CI/CD pipeline summary for `.github/workflows/ci-release.yml`
- Updated `docs/TROUBLESHOOTING.md`:
  - added checks for `UBO_DOOM_LIB`
  - added guidance for `UBO_DOOM_CWD` / `UBO_DOOM_CONFIG` to avoid stale config behavior
  - added CI/CD status section (CI on PR/master, artifacts on tags)

### Status
- Core docs now consistently reflect current runtime behavior and current GitHub Actions workflow.

## 2026-02-23T16:45:16 — Documentation audit + sync with current behavior/workflow

### Root cause
- Some docs lagged behind current implementation:
  - `docs/CONTROLS.md` still described old ALT mode and BACK behavior.
  - `docs/SETUP_UBO_APP.md` omitted newer optional env vars (`UBO_DOOM_ALSA_DEVICE`, `UBO_DOOM_CWD`, `UBO_DOOM_CONFIG`).
- README had CI badge but no short section describing CI-on-checkins + artifacts-on-tags behavior.

### Fix
- Updated `docs/CONTROLS.md` to match `doom_controller.py` routing.
- Updated `docs/SETUP_UBO_APP.md` env var guidance and optional ALSA override examples.
- Added a concise `CI/CD` section to `README.md` referencing `.github/workflows/ci-release.yml` behavior.

### Status
- Core user-facing docs now align with current controls, runtime env options, and GitHub Actions workflow.

## 2026-02-23T16:43:05 — Added GitHub Actions badge to README

### What was done
- Added a status badge near the top of `README.md` linked to:
  - `https://github.com/ekkus93/ubo_doom/actions/workflows/ci-release.yml`
- Badge reflects state of the combined CI/release workflow used for normal check-ins and tagged releases.

### Status
- README now provides visible CI/CD health signal on the repo front page.

## 2026-02-23T16:41:30 — Added GitHub Actions CI for check-ins + release artifacts for tags

### What was done
- Added workflow: `.github/workflows/ci-release.yml`.
- Configured CI to run on pull requests and pushes to `master`:
  - Build native `libubodoom.so` via `native/scripts/build_libubodoom.sh`
  - Run Python controller tests: `ubo_service/070-doom/tests/test_doom_controller.py`
- Configured tag behavior (`v*`, `release-*`) to also produce and publish release artifacts:
  - `dist/libubodoom.so`
  - `dist/ubo_service_070-doom.tar.gz`
  - `dist/system_env_and_systemd_examples.tar.gz`
  - Uploads both as workflow artifacts and GitHub Release assets.

### Status
- Normal check-ins now run CI only.
- Tagged releases run CI plus artifact publication.

## 2026-02-23T16:38:32 — Removed obsolete patch artifact; aligned docstrings with current build flow

### Root cause
- Repository no longer uses patch-application during build/deploy; sources are pre-modified in `third_party/DOOM-master/linuxdoom-1.10`.
- Legacy wording in Python docstrings still implied `libubodoom.so` was generated from `ubodoom_linuxdoom110.patch`.

### Fix
- Deleted obsolete file: `patches/ubodoom_linuxdoom110.patch`.
- Updated docstring language in:
  - `ubo_service/070-doom/setup.py`
  - `ubo_service/070-doom/native/doom_lib.py`
  to describe build output as coming from the pre-modified third-party source tree.

### Status
- Repository wording and file layout now match the active build scripts/workflow.

## 2026-02-23T16:28:43 — Fixed second silent-audio root cause in `I_StartSound`

### Root cause
- In `i_sound_alsa.c`, `I_StartSound()` still used `#ifdef SNDSERV` branching.
- Because `SNDSERV` is defined in Doom headers, the function returned via the legacy sndserver path and did not enqueue sounds into internal mixer channels (`addsfx`) when sndserver was not active.
- Result: `I_UpdateSound()` had no active channels to mix, so gameplay remained silent.

### Fix
- Updated `I_StartSound()` to always use ALSA backend behavior:
  - enqueue with `addsfx(id, vol, steptable[pitch], sep)`
  - return the resulting handle.
- Removed legacy sndserver text-protocol branch from this ALSA file path.

### Deploy
- Rebuilt and deployed to `ubo@192.168.88.112`.
- Restarted `ubo-app` to load updated `libubodoom.so`.

### Status
- Combined with prior `I_SubmitSound` fix, this restores full ALSA in-process mixing/output pipeline for Doom.
- User validation pending.

## 2026-02-23T16:28:43 — Fixed root cause for silent Doom audio (SNDSERV submit path)

### Root cause
- In `i_sound_alsa.c`, `I_InitSound()` opened ALSA PCM successfully, but `I_SubmitSound()` still used a `#ifdef SNDSERV` branch writing to legacy `audio_fd` (sndserver path) when `SNDSERV` is defined in Doom headers.
- Result: Doom mixed audio was not submitted to the opened ALSA PCM device, causing silent gameplay audio despite valid mixer levels/device routing.

### Fix
- Updated `third_party/DOOM-master/linuxdoom-1.10/i_sound_alsa.c`:
  - `I_SubmitSound()` now always writes via `snd_pcm_writei(audio_pcm, ...)`.
  - `I_ShutdownSound()` now always drains/closes `audio_pcm`.
  - Removed legacy `audio_fd`-based SNDSERV conditional behavior from these two runtime paths.

### Deploy
- Rebuilt and deployed on `ubo@192.168.88.112` with `build_on_device.sh`.
- Restarted `ubo-app` to load the new `libubodoom.so`.

### Status
- This addresses the core mismatch between ALSA init and submit paths; user validation of in-game sound pending.

## 2026-02-23T16:28:43 — Applied live ALSA override on device for Doom audio

### What was done
- Updated live user override on `ubo@192.168.88.112`:
  - `~/.config/systemd/user/ubo-app.service.d/override.conf`
  - Added `Environment=UBO_DOOM_ALSA_DEVICE=plughw:CARD=wm8960soundcard,DEV=0`
- Reloaded/restarted service:
  - `systemctl --user daemon-reload`
  - `systemctl --user restart ubo-app`

### Verification
- Confirmed effective unit environment includes:
  - `UBO_DOOM_ALSA_DEVICE=plughw:CARD=wm8960soundcard,DEV=0`
- Recent log tail showed Doom input/runtime logs; ALSA init lines are expected when Doom session initializes sound path.

### Current status
- Device is configured to prefer WM8960 playback endpoint for Doom ALSA output.
- User needs to launch Doom and trigger in-game sound to validate audible output.

### Follow-up update
- Switched live override from `plughw:CARD=wm8960soundcard,DEV=0` to
  `sysdefault:CARD=wm8960soundcard` to use the shared ALSA path.
- Confirmed effective unit environment reflects the new value.
- Ran `speaker-test` on `sysdefault:CARD=wm8960soundcard` successfully (device opens and tone stream runs).

## 2026-02-23T16:28:43 — Fix no-sound cases with ALSA device fallback + override

### Root cause
- Doom ALSA init attempted only `snd_pcm_open(..., "default", ...)` once.
- On some device states/configs, `default` is unavailable or not the active playback endpoint, resulting in silent Doom.

### Fix applied
- Updated `third_party/DOOM-master/linuxdoom-1.10/i_sound_alsa.c`:
  - Added `UBO_DOOM_ALSA_DEVICE` environment override support.
  - Added fallback open attempts in order: override, `default`, `sysdefault:CARD=wm8960soundcard`, `plughw:CARD=wm8960soundcard,DEV=0`, `plughw:0,0`, `hw:0,0`.
  - Added per-device init logging for open attempts/success/failure.

### Configuration updates
- Added `UBO_DOOM_ALSA_DEVICE` to:
  - `system/env/ubo_app.env.example`
  - `system/systemd/ubo_app_override.conf.example`
  - `ubo_service/070-doom/config/doom.env.example`
- Updated troubleshooting docs to use env override instead of editing C backend.

### Status
- Functional change is in native ALSA init path; runtime behavior now tolerates missing `default` by trying fallback devices.

## 2026-02-23T16:28:43 — Locked audio architecture to Option 3 (direct ALSA)

### Decision
- User selected Option 3: keep Doom audio direct to ALSA, with no ubo_app sound-stream integration changes.

### Repository updates
- Synced documentation/comments to match runtime behavior:
  - `ubo_service/070-doom/setup.py` audio section now states Doom owns ALSA output while active.
  - `docs/ARCHITECTURE.md` audio pipeline now explicitly documents Option 3 / direct ALSA and no ubo_app stream path.
  - `README.md` wording adjusted to avoid implying ubo-managed audio restoration.

### Status
- No functional audio-path code changes were made.
- Current behavior remains: Doom writes PCM directly via ALSA in `i_sound_alsa.c`.

## 2026-02-23T15:58:25 — Restore movement speed to +25/-25

### Change
- Updated movement experiment values back to faster defaults:
  - `g_game.c` keyboard forward contribution: `+25/-25`
  - `doom_api.c` deterministic post-build override: `cmd->forwardmove = 25/-25`

### Context
- User reported the logic appears correct and requested increased movement speed.
- Signedness fix (`signed char` in `ticcmd_t`) remains in place to preserve negative values on this target.

### Deploy
- Rebuilt/deployed to `ubo@192.168.88.112` and restarted `ubo-app`.

## 2026-02-23T15:45:02 — Root cause confirmed: sign loss in `ticcmd_t.forwardmove`

### Finding
- Verified target compiler defines `__CHAR_UNSIGNED__ = 1` on device.
- `ticcmd_t.forwardmove` and `ticcmd_t.sidemove` were declared as plain `char`.
- On this target, negative values (e.g. `-7`) can be reinterpreted as positive bytes,
  explaining UP/DOWN behaving similarly.

### Fix
- Updated `third_party/DOOM-master/linuxdoom-1.10/d_ticcmd.h`:
  - `forwardmove` and `sidemove` changed from `char` to `signed char`.

### Deploy
- Rebuilt/deployed to `ubo@192.168.88.112` and restarted `ubo-app`.

### Status
- Sign handling is now explicit and portable across toolchains where plain `char` is unsigned.
- User validation pending on hardware controls.

## 2026-02-23T15:45:02 — Force UP/DOWN forwardmove to +15/-15 (experiment)

### Request
- User requested deterministic movement test: UP should map to `fwd=15`, DOWN to `fwd=-15`.

### What was changed
- `third_party/DOOM-master/linuxdoom-1.10/g_game.c`
  - Changed keyboard branches in `G_BuildTiccmd()`:
    - `gamekeydown[key_up]` → `forward += 15`
    - `gamekeydown[key_down]` → `forward -= 15`
- `third_party/DOOM-master/linuxdoom-1.10/doom_api.c`
  - Added hard post-build override immediately after `G_BuildTiccmd(cmd)`:
    - UP only  → `cmd->forwardmove = 15`
    - DOWN only → `cmd->forwardmove = -15`
    - both pressed → `cmd->forwardmove = 0`
  - This guarantees deterministic values regardless of internal mouse/joystick contributions.

### Deploy
- Rebuilt and deployed on device:
  - `./native/scripts/build_on_device.sh ubo@192.168.88.112`
  - restarted `ubo-app`.

### Status
- Experiment is live on device and ready for user validation.

## 2026-02-23T15:45:02 — Deploy + verify canonical cwd/config enforcement on device

### What was done
- Ran native on-device build/deploy successfully:
  - `./native/scripts/build_on_device.sh ubo@192.168.88.112`
  - Installed `/home/ubo/doom/libubodoom.so`
  - Synced `/home/ubo/ubo_services/070-doom/`
- Restarted service: `systemctl --user restart ubo-app`.

### Verification results
- Doom service registration still healthy in log:
  - `[doom] calling init_service()`
  - `[doom] init_service() completed OK`
- Confirmed deployed native library includes new logic strings:
  - `UBO_DOOM_CWD`
  - `UBO_DOOM_CONFIG`
  - `[doom] failed to chdir to UBO_DOOM_CWD=%s`
- Confirmed deployed service file contains `_resolve_launch_paths()` and launch-path env exports.

### Current status
- Patch is deployed and present on device.
- Runtime line `[doom] launch paths: ...` is emitted only when the Doom page is opened (during `DoomPage._init_doom`), so that specific log confirmation is pending user launching Doom once.

## 2026-02-23T15:45:02 — Enforce canonical Doom config path + launch cwd

### Root cause
- Embedded Doom init was only passing `-iwad`; linuxdoom then defaulted config to `$HOME/.doomrc`
  (`d_main.c` → `basedefault`), so runtime behavior depended on ambient HOME/cwd and stale host config.
- No explicit launch cwd was enforced, so filesystem behavior could vary by service startup context.

### Fixes applied
- `ubo_service/070-doom/setup.py`
  - Added `_resolve_launch_paths()` to canonicalize:
    - IWAD path (absolute)
    - launch cwd (`UBO_DOOM_CWD` or IWAD parent)
    - config path (`UBO_DOOM_CONFIG` or `<cwd>/doomrc.cfg`)
  - Exports canonical `UBO_DOOM_CWD` / `UBO_DOOM_CONFIG` env values before `doom_init()`.
  - Ensures launch/config parent directories exist.
  - Logs launch paths at init for diagnostics.
- `third_party/DOOM-master/linuxdoom-1.10/doom_api.c`
  - `doom_init()` now reads `UBO_DOOM_CWD` and `chdir()`s before engine startup.
  - Appends `-config <UBO_DOOM_CONFIG>` to `myargv` when provided.
  - Increased internal argv buffer size to safely hold extra args.
- `ubo_service/070-doom/config/doom.env.example`
  - Documented new optional `UBO_DOOM_CWD` and `UBO_DOOM_CONFIG` variables.

### Validation
- `pytest -q tests/test_doom_controller.py` → **58 passed**.
- Note: native C changes require rebuild/redeploy of `libubodoom.so` on target.

### Current status / pending
- Canonical config location + launch cwd enforcement is implemented in code.
- Pending on-device rebuild/deploy and runtime verification that Doom now ignores stale `$HOME/.doomrc`
  and always uses the configured `UBO_DOOM_CONFIG`.

## 2026-02-23T14:44:46 (90d3254) — Restore BACK×N navigation; correct go_back branch order

### Root cause
Previous fix (412b126) sent ESCAPE in ALL non-level states, which opened the Doom menu
from the title screen but then also sent ESCAPE when the menu was already open — preventing
forward navigation (confirming New Game, episode, skill).

### Correct go_back() routing
```
in_level=True    → FIRE         (shoot weapon)
menu_active=True → MENU_SELECT  (confirm/navigate forward in open menu)
otherwise        → ESCAPE       (opens main menu from title/demo screen)
```
No ping-pong: title→ESCAPE opens menu→`menu_active=True`, then MENU_SELECT confirms items
forward. State never alternates because MENU_SELECT doesn't close the menu.

### Tests
58 passed. Key new tests: `test_title_screen_then_menu_does_not_ping_pong`,
`test_repeated_go_back_in_menu_always_menu_selects`,
`test_repeated_go_back_on_title_screen_always_escapes`.

---

## 2026-02-23T14:39:37 (412b126) — Fix go_back ping-pong: always ESCAPE when not in-level

### Root cause
`go_back()` had three branches: FIRE (in-level), ESCAPE (menu active), MENU_SELECT/ENTER (other).
The "other" branch fired on the title screen, opened the main menu with ENTER, then the next
BACK press sent ESCAPE to close it, toggling indefinitely. New Game could never be reached.

### Fix
Removed the MENU_SELECT branch entirely. `go_back()` is now two cases only:
- `_in_level=True` → FIRE
- everything else → ESCAPE (title screen, menus, intermissions, finales)

ESCAPE opens the Doom menu from the title screen, goes up one level in open menus, and
advances intermissions/finales — correct in all states. L3 handles menu confirm (MENU_SELECT).

### Tests
58 passed. Added: `test_default_state_sends_escape`, `test_intermission_sends_escape`,
`test_never_sends_menu_select`, `test_repeated_go_back_on_title_screen_always_escapes`.

---

## 2026-02-23T14:31:12 (717fafd) — Extract DoomController; add unit tests; fix menuactive() race condition

### Root causes fixed
- **Race condition in go_back() / _btn_l3()**: both were calling `doom.menuactive()` directly
  from the Kivy main thread, which races with the tick thread. Fixed by caching `_menu_active`
  in `update_game_state()` (tick thread only) and reading only the cached value on the main thread.
- **No unit tests**: all control logic was embedded in `DoomPage` (Kivy + ctypes + ubo_app),
  making it impossible to test without the full device stack. Every bug was a deploy-and-poke
  cycle on hardware.

### What was done
- Extracted all input-routing state machine into `ubo_service/070-doom/doom_controller.py`:
  - `DoomController(tap_fn)` — pure Python, no Kivy/DoomLib/ubo_app dependencies
  - Owns: `_in_level`, `_menu_active`, `_alt_mode`
  - Methods: `go_up`, `go_down`, `go_back`, `btn_l2`, `btn_l3`, `toggle_mode`, `exit_level`,
    `update_game_state`
  - `update_game_state()` derives both bools from a single coherent snapshot (tick thread)
    and returns True when the game just left a level
- Refactored `setup.py`: `DoomPage` is now a thin shell; all input logic delegates to controller
- Added `ubo_service/070-doom/pyproject.toml` with pytest config
- Added `ubo_service/070-doom/tests/test_doom_controller.py`: 56 tests, 0.17s, no hardware
  - Covers: movement, go_back routing, btn_l2/l3 routing, toggle_mode, exit_level,
    update_game_state transitions, ping-pong regression, ALT mode lifecycle

### Status
- 56/56 tests passing locally
- Python-only deploy: `rsync -avz ubo_service/070-doom/ ubo@192.168.88.112:~/ubo_services/070-doom/`
- C diagnostics (fprintf in doom_api.c / g_game.c) still active — remove when controls confirmed OK
- Pending: run pytest in CI; commit

---

## 2026-02-23T13:10:03 (d3314de) — Background thread; movement direction fix

### What was done
- Moved the Doom tick loop off the Kivy main thread onto a dedicated `doom-tick` background
  thread. Key events are published via `queue.Queue`, drained each tick, and held/released
  with a countdown in `_held`. This eliminated WiFi/SSH starvation caused by the tick
  blocking Kivy's event loop.
- Halved LCD SPI write rate: render only on `frame % 2 == 0` (~15fps) to reduce DMA
  contention between the SPI controller and the WiFi SDIO bus on the RPi4.
- Removed all diagnostic `fprintf` spam from `g_game.c` and `doom_api.c`.
- Fixed "DOWN moves player forward" bug with three changes:
  1. **cancel-opposite** (setup.py tick queue drain): when UP or DOWN arrives, immediately
     release the opposite direction if it's still held. Prevents `gamekeydown[key_up]` and
     `gamekeydown[key_down]` from both being true simultaneously.
  2. **key_up on close** (setup.py `on_close()`): call `doom.key_up()` for every key still
     in `_held` before clearing it. Previously the tick thread could exit mid-hold, leaving
     `gamekeydown[KEY_UPARROW] = true` permanently in C until the next `G_InitNew`.
  3. **key_speed = 0** (doom_api.c `doom_init()`): lock run-modifier key to 0 (never sent).
     Default was `KEY_RSHIFT=182`; now always walk speed (`forwardmove[0]=25`).
- Fixed copilot-instructions.md Memory file section: clarified append-only policy.
- Committed: `d3314de`

### Pending
- User confirmation that movement is fixed on device.

---

## 2026-02-23T12:14:37 (789e17f..533df66) — Fire button; key bindings; context-aware BACK

### What was done
- **Diagnosed fire button failure**: `#define HU_MSGREFRESH KEY_ENTER` in `hu_stuff.h` —
  `HU_Responder` consumed every `KEY_ENTER` before it reached `G_Responder`/`gamekeydown`.
- Fixed fire: mapped `UBO_KEY_FIRE` → `KEY_RCTRL` (0x9d=157).
- Fixed stale key bindings from `~/.doomrc` on device (had `key_right=0`, `key_left=0`):
  force `key_fire/right/left/up/down` in `doom_init()` after `D_DoomMain()`. Deleted `~/.doomrc`.
- Added `hold_ticks` param to `_tap()`. L2/L3 use `hold_ticks=12` to exceed `SLOWTURNTICS=10`.
- Fixed menu regression (RCTRL doesn't select menu items):
  - Added `UBO_KEY_MENU_SELECT=8` → `KEY_ENTER` (safe in menus; `HU_MSGREFRESH` only
    intercepts KEY_ENTER when a HUD refresh message is active).
  - Added `doom_get_gamestate()` and `doom_get_menuactive()` to `doom_api.c/h` and `doom_lib.py`.
  - Made `go_back()` context-aware: `GS_LEVEL + !menuactive` → FIRE; else MENU_SELECT.
- Doom reaches game screen; player can fire weapon.
- Committed: `ce93461` (fire fix), `533df66` (context-aware BACK)

---

## 2026-02-23T11:33:28 (a890969) — First working game screen on aarch64

### What was done
- Doom initialises cleanly from `libubodoom.so` and reaches title screen.
- Pressing BACK ×3 navigates menus and loads E1M1 without crashing.
- Game screen renders; player POV with weapon visible; game loop runs at 30fps.
- **64-bit aarch64 porting fixes** applied:
  - `z_zone.c`: align allocations to 8 bytes (was 4) for aarch64 pointer alignment.
  - `p_setup.c`: `P_GroupLines` linebuffer alloc uses `sizeof(*linebuffer)` not `*4`.
  - `i_system.c`: `mb_used` default 16 → 32 MB.
  - `R_InitColormaps`: cast to `(byte*)` not `(int)` — pointer truncation on 64-bit.
  - Multiple SIGSEGV fixes in `R_Init*` texture loading.
- **Library mode robustness**:
  - `I_Error`: replaced `exit()` with `setjmp/longjmp` (`ubo_error_jmp`).
  - `SIGSEGV/SIGBUS`: caught with `sigsetjmp` in `doom_tick()`; engine marked dead; host stays alive.
  - `doom_init()` runs `D_DoomMain` on a background thread (avoids freezing Kivy UI).
  - `d_net.c`: cap `realtics` to 4 to prevent freeze spike after `doom_reset`.
  - `d_main.c`: skip `NetUpdate()` and wipe spin-wait in library mode (`ubo_library_mode`).
  - `singletics = true` set in `doom_init()` — all `NetUpdate()` calls become no-ops.
  - Tick path: `I_StartTic → D_ProcessEvents → G_BuildTiccmd → M_Ticker → G_Ticker`.
  - `doom_reset()` clears `wadfiles[]`, `gametic`, `maketic`.
- Fire still broken (KEY_ENTER stolen by HU_MSGREFRESH — fixed in session 2).
- Committed: `a890969`

---

## 2026-02-22T20:10:27 (53e5b84..c4abb5e) — Audio fixes; stability improvements

### What was done
- Fixed silent audio: `I_UpdateSound()` was guarded by `SNDINTR` (never defined).
  Now called unconditionally in `doom_tick()`.
- Fixed `Z_Malloc OOM`: zone heap 6 MB → 16 MB for aarch64 (8-byte pointers in zone blocks).
- Fixed audio mute regression: removed OUTPUT channel mute from `setup.py` (was silencing Doom's ALSA).
- Removed `doom_shutdown()` call on navigation away — engine cannot be re-initialised mid-process.
- Fixed unmute ordering: unmute only after `doom_init()` succeeds.
- Fixed 64-bit ALSA struct layout and SNDSERV detection in `doom_init()`.
- Pre-cached all SFX in `I_InitSound()` to avoid per-tick file I/O.
- Committed: `53e5b84`, `a6014d9`, `81ab351`, `2b93301`, `92f4933`, `e33bf9f`, `c4abb5e`

---

## 2026-02-21T07:31:35 (bb76fbc..165b8aa) — Service scaffolding; on-device build; initial port

### What was done
- Scaffolded `ubo_service/070-doom/` service: `setup.py`, `native/doom_lib.py`, `__init__.py`.
- Fixed Python service discovery: `sys.path` insert, `format_exc` logging, symlink deploy.
- Fixed service name: `ubo-app` not `ubo_app` (systemd uses hyphen).
- Rewrote README for on-device workflow (no cross-compilation). Added `build_on_device.sh`.
- Replaced patch-based build with pre-modified `third_party/` source tree.
- Committed: `8def516` through `a890969` (many small commits)

---

## 2026-02-18T14:21:29 (c0c4343..973d54b) — Project initialised

- Initial commit: project structure, LICENSES, README skeleton. Added `.gitignore`.
- Committed: `c0c4343`, `058870b`, `973d54b`

---

## 2026-02-23T13:46:53 — Reference: current device / key values

- Device: aarch64 RPi4, `ubo@192.168.88.112` (use IP when Doom running — mDNS unreliable under load)
- Deploy C+Python: `./native/scripts/build_on_device.sh ubo@192.168.88.112`
- Deploy Python only: `rsync -avz ubo_service/070-doom/ ubo@192.168.88.112:~/ubo_services/070-doom/`
- Restart: `ssh ubo@192.168.88.112 'systemctl --user restart ubo-app'`
- Logs: `ssh ubo@192.168.88.112 'tail -f /tmp/ubo-app.log'`
- KEY_UPARROW=0xad=173, KEY_DOWNARROW=0xaf=175, KEY_LEFTARROW=0xac=172, KEY_RIGHTARROW=0xae=174
- KEY_RCTRL=0x9d=157, KEY_ENTER=0x0d=13
- NUMKEYS=256, forwardmove[0]=25 (walk), forwardmove[1]=50 (run, disabled)
- SLOWTURNTICS=10 → use hold_ticks=12 for full turn speed
- GS_LEVEL=0, GS_INTERMISSION=1, GS_FINALE=2, GS_DEMOSCREEN=3
- UboKey: UP=1→UPARROW, DOWN=2→DOWNARROW, LEFT=3→LEFTARROW, RIGHT=4→RIGHTARROW,
          FIRE=5→RCTRL, USE=6→Space, ESCAPE=7→ESC, MENU_SELECT=8→ENTER
