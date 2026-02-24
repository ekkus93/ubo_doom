# Project Memory — ubo_doom

<!-- Append-only log. NEVER delete or overwrite entries. Prepend new sessions at the top. -->

---

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
