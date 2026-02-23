# Project Memory — ubo_doom

## 2026-02-23T19:38:40Z — Session state after commit a890969

### Device
- aarch64 Raspberry Pi 4, IP: 192.168.88.112 / ubo-rd.local
- SSH: `ubo@ubo-rd.local`
- Deploy: `scp` the .so to device, restart ubo-app service

### Current state
- Game loads, renders, animates (singletics path, 30 fps via Kivy Clock)
- BACK×3 from Ubo home screen: navigates menu → loads E1M1
- Menu navigation works (ESCAPE, L3/ALT mode arrows)
- **Fire (BACK→KEY_ENTER) and movement still not working**

### Key architecture decisions
- `singletics = true` set in `doom_init()` — makes all `NetUpdate()` calls no-ops
- `doom_tick` uses singletics path: `I_StartTic → D_ProcessEvents → G_BuildTiccmd → M_Ticker → G_Ticker → gametic++ → maketic++`
- `_tap()` in setup.py: `key_down` immediately, `key_up` delayed 2 tics via `Clock.schedule_once(lambda _dt: ..., 2.0/self._fps)`
- `ubo_library_mode` guards wipe spin-wait and `NetUpdate` inside `D_Display`
- `realtics` capped to 4 in `TryRunTics` (d_net.c) to prevent freeze after reset
- `linebuffer` uses `sizeof(*linebuffer)` not `*4` — aarch64 64-bit pointer fix (p_setup.c)
- Zone allocations aligned to 8 bytes for aarch64 (z_zone.c)

### File locations
- C source: `third_party/DOOM-master/linuxdoom-1.10/`
- Python service: `ubo_service/070-doom/`
- Build script: `native/scripts/build_libubodoom.sh`
- Library output: `native/build/libubodoom.so`

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
