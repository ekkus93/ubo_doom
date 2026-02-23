# Project Memory — ubo_doom

## 2026-02-23T20:33:14Z — Session state after commit 533df66

### Device
- aarch64 Raspberry Pi 4, IP: 192.168.88.112 / ubo-rd.local
- SSH: `ubo@ubo-rd.local`
- Deploy C: `./native/scripts/build_on_device.sh ubo@ubo-rd.local`
- Deploy Python: `scp ubo_service/070-doom/setup.py ubo@ubo-rd.local:~/ubo_services/070-doom/ && scp ubo_service/070-doom/native/doom_lib.py ubo@ubo-rd.local:~/ubo_services/070-doom/native/doom_lib.py`
- Restart: `ssh ubo@ubo-rd.local 'systemctl --user restart ubo-app'`
- Logs: `/tmp/ubo-app.log`

### Current state (what works)
- Game loads, renders, animates (singletics path, 30 fps via Kivy Clock)
- Movement: UP=forward, DOWN=backward, L2=turn left, L3=turn right, ALT+UP/DOWN=turn
- BACK in-game → fires weapon (KEY_RCTRL)
- BACK in menus / intermission / demo → sends KEY_ENTER to navigate/select
- L2/L3 use hold_ticks=12 so they exceed SLOWTURNTICS=10 for full-speed turning
- Key bindings forced in doom_init(): key_fire=KEY_RCTRL, arrows=KEY_LEFTARROW etc. (immune to .doomrc)
- .doomrc deleted from device; no longer a threat to key bindings

### Root cause history (for reference)
- Fire never worked: `#define HU_MSGREFRESH KEY_ENTER` in hu_stuff.h — HU_Responder ate every KEY_ENTER
- Fix: UBO_KEY_FIRE → KEY_RCTRL (0x9d = 157)
- Menu regression: KEY_RCTRL doesn't navigate menus
- Fix: context-aware BACK — gamestate()==0 && !menuactive() → FIRE, else MENU_SELECT (KEY_ENTER)
- key_right/key_left were 0: ~/.doomrc on device had zeroed them; fixed by forcing in doom_init + deleting .doomrc
- Timer race on key_up: Clock.schedule_once could land in same D_ProcessEvents drain; fixed with _held dict countdown in _tick()

### Key architecture decisions
- `singletics = true` set in `doom_init()` — makes all `NetUpdate()` calls no-ops
- `doom_tick` uses singletics path: `I_StartTic → D_ProcessEvents → G_BuildTiccmd → M_Ticker → G_Ticker → gametic++ → maketic++`
- `_tap(key, hold_ticks=2)` in setup.py: `key_down` immediately, `key_up` sent by `_tick()` when `_held[key]` countdown hits 0
- `ubo_library_mode` guards wipe spin-wait and `NetUpdate` inside `D_Display`
- `realtics` capped to 4 in `TryRunTics` (d_net.c) to prevent freeze after reset
- `linebuffer` uses `sizeof(*linebuffer)` not `*4` — aarch64 64-bit pointer fix (p_setup.c)
- Zone allocations aligned to 8 bytes for aarch64 (z_zone.c)
- GS_LEVEL = 0 (confirmed from logs)
- KEY_RCTRL = 0x9d = 157
- SLOWTURNTICS = 10 in g_game.c → must hold for >10 ticks for full turn speed

### UboKey enum (doom_api.h + doom_lib.py)
- UBO_KEY_UP=1 → KEY_UPARROW
- UBO_KEY_DOWN=2 → KEY_DOWNARROW
- UBO_KEY_LEFT=3 → KEY_LEFTARROW
- UBO_KEY_RIGHT=4 → KEY_RIGHTARROW
- UBO_KEY_FIRE=5 → KEY_RCTRL (fire weapon in-game)
- UBO_KEY_USE=6 → Space
- UBO_KEY_ESCAPE=7 → KEY_ESCAPE
- UBO_KEY_MENU_SELECT=8 → KEY_ENTER (for menu navigation only)

### Exported C functions (doom_api.c / doom_api.h)
- doom_init, doom_tick, doom_shutdown
- doom_key_down, doom_key_up
- doom_get_rgba_ptr, doom_get_rgba_width, doom_get_rgba_height
- doom_is_alive, doom_reset
- doom_get_gamestate() → int (0=GS_LEVEL, 1=GS_INTERMISSION, 2=GS_FINALE, 3=GS_DEMOSCREEN)
- doom_get_menuactive() → int (1 if menu overlay active)

### File locations
- C source: `third_party/DOOM-master/linuxdoom-1.10/`
- Python service: `ubo_service/070-doom/`
- Build scripts: `native/scripts/`
- Library output (on device): `~/doom/libubodoom.so`

### Diagnostics still present (cleanup needed)
- `fprintf` in doom_api.c `doom_key_down`/`doom_key_up` — logs ubo_key and doom_key to stderr
- `fprintf` in g_game.c `G_Responder` — logs every keydown with gamestate/menuactive
- `fprintf` in g_game.c `G_BuildTiccmd` — logs every 30 ticks + FIRE detection
- These are intentional for now; remove once controls are confirmed stable


### Next debugging step — fire button
Hypothesis: `G_BuildTiccmd` may be called before key events from the previous Python `_tap()` call are processed, or the events are being consumed. 

Plan:
1. Add `fprintf(stderr, "[doom] G_BuildTiccmd: gamekeydown[%d]=%d\n", key_fire, gamekeydown[key_fire])` to `G_BuildTiccmd` in g_game.c to confirm whether the key is ever seen
2. Check if `gamestate == GS_LEVEL` when in-game (G_Responder at line 535 checks this)
3. Check `menuactive` value when BACK is pressed (M_Responder consumes KEY_ENTER when menuactive=1)
4. Verify `go_back()` in setup.py returns True — prevents UboPageWidget from navigating away, but does it also block the event from reaching doom?

### Diagnostic code still present (to remove when fire is fixed)
- `p_setup.c`: `Z_CheckHeap()` + `fprintf` after each `P_Load*` call, `#include <stdio.h>`
- `z_zone.c`: `fprintf(stderr, "[doom] Z_Init: ...")` in `Z_Init`, `#include <stdio.h>`

### Key mappings (from doom_api.c / setup.py)
```
UboKey.UP      → KEY_UPARROW  (movement)
UboKey.DOWN    → KEY_DOWNARROW
UboKey.L2      → KEY_RIGHTARROW (strafe/turn right)
UboKey.L3      → KEY_LEFTARROW
UboKey.FIRE    → KEY_ENTER (= key_fire default = 13)
BACK button    → calls go_back() → _tap(UboKey.FIRE)
```

### Build + deploy commands
```bash
# Build on host (cross-compile or on device)
cd native && ./scripts/build_libubodoom.sh

# Deploy
scp native/build/libubodoom.so pi@192.168.88.112:~/
ssh pi@192.168.88.112 "sudo cp ~/libubodoom.so /opt/ubo/lib/ && sudo systemctl restart ubo-app"
```
