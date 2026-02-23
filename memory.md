# Project Memory — ubo_doom

<!-- Append-only log. NEVER delete or overwrite entries. Prepend new sessions at the top. -->

---

## 2026-02-23T13:10:03-0800 (d3314de) — Background thread; movement direction fix

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

## 2026-02-23T12:14:37-0800 (789e17f..533df66) — Fire button; key bindings; context-aware BACK

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

## 2026-02-23T11:33:28-0800 (a890969) — First working game screen on aarch64

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

## 2026-02-22T20:10:27-0800 (53e5b84..c4abb5e) — Audio fixes; stability improvements

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

## 2026-02-21T07:31:35-0800 (bb76fbc..165b8aa) — Service scaffolding; on-device build; initial port

### What was done
- Scaffolded `ubo_service/070-doom/` service: `setup.py`, `native/doom_lib.py`, `__init__.py`.
- Fixed Python service discovery: `sys.path` insert, `format_exc` logging, symlink deploy.
- Fixed service name: `ubo-app` not `ubo_app` (systemd uses hyphen).
- Rewrote README for on-device workflow (no cross-compilation). Added `build_on_device.sh`.
- Replaced patch-based build with pre-modified `third_party/` source tree.
- Committed: `8def516` through `a890969` (many small commits)

---

## 2026-02-18T14:21:29-0800 (c0c4343..973d54b) — Project initialised

- Initial commit: project structure, LICENSES, README skeleton. Added `.gitignore`.
- Committed: `c0c4343`, `058870b`, `973d54b`

---

## Reference: current device / key values

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
