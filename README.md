# ubo_doom — Ubo v2 compatibility

Doom ported to current Ubo as an external service. The Ubo v2 integration registers a serializable app action and publishes 240×240 RGB888 frames through Ubo's `frame_stream` renderer. It does not import Kivy or write directly to the ST7789 display.

These instructions apply to the `agent/ubo-v2-compatibility` branch.

## Requirements

- Current Ubo v2 installed and running
- `build-essential` and `libasound2-dev`
- A legally obtained Doom IWAD such as `doom1.wad`, `doom.wad`, or `doom2.wad`

This repository does not include an IWAD.

## Install

Run these commands on the Ubo device.

### 1. Clone or update the compatibility branch

New checkout:

```bash
git clone \
  --branch agent/ubo-v2-compatibility \
  --single-branch \
  https://github.com/ekkus93/ubo_doom.git \
  "$HOME/work/ubo_doom"

cd "$HOME/work/ubo_doom"
```

Existing checkout:

```bash
cd "$HOME/work/ubo_doom"
git fetch origin
git switch agent/ubo-v2-compatibility
git pull --ff-only
```

Confirm the branch and latest commit:

```bash
git branch --show-current
git log -1 --oneline
```

### 2. Install native build dependencies

```bash
sudo apt update
sudo apt install -y build-essential libasound2-dev
```

### 3. Build the shared library

```bash
cd "$HOME/work/ubo_doom"
./native/scripts/build_libubodoom.sh
```

Validate it:

```bash
test -f native/out/libubodoom.so
file native/out/libubodoom.so
ldd native/out/libubodoom.so
```

`ldd` must not report any missing libraries.

### 4. Install the library and IWAD

```bash
mkdir -p "$HOME/doom"
cp native/out/libubodoom.so "$HOME/doom/"
cp /path/to/your/doom2.wad "$HOME/doom/"
touch "$HOME/doom/doomrc.cfg"
```

Replace `doom2.wad` with the exact filename of the IWAD you own.

### 5. Deploy the external service

```bash
mkdir -p "$HOME/ubo_services"
ln -sfn \
  "$HOME/work/ubo_doom/ubo_service/070-doom" \
  "$HOME/ubo_services/070-doom"
```

Validate the link:

```bash
readlink -f "$HOME/ubo_services/070-doom"
test -f "$HOME/ubo_services/070-doom/ubo_handle.py"
test -f "$HOME/ubo_services/070-doom/setup.py"
```

### 6. Configure the Ubo user service

Current Ubo normally runs through the user-level systemd unit `ubo-app.service`.

```bash
mkdir -p "$HOME/.config/systemd/user/ubo-app.service.d"
cp \
  "$HOME/work/ubo_doom/system/systemd/ubo_app_override.conf.example" \
  "$HOME/.config/systemd/user/ubo-app.service.d/override.conf"
```

Review the override:

```bash
nano "$HOME/.config/systemd/user/ubo-app.service.d/override.conf"
```

It should contain values equivalent to:

```ini
[Service]
Environment=UBO_SERVICES_PATH=%h/ubo_services
Environment=UBO_DOOM_LIB=%h/doom/libubodoom.so
Environment=UBO_DOOM_IWAD=%h/doom/doom2.wad
Environment=UBO_DOOM_CWD=%h/doom
Environment=UBO_DOOM_CONFIG=%h/doom/doomrc.cfg
Environment=UBO_DOOM_FPS=30
Environment=UBO_DOOM_RENDER_FPS=15
Environment=UBO_DOOM_ALSA_DEVICE=default
```

Change `UBO_DOOM_IWAD` if your IWAD filename is different. `UBO_SERVICES_PATH` is colon-separated, so preserve any other external service directories already configured.

Apply and restart:

```bash
systemctl --user daemon-reload
systemctl --user restart ubo-app
systemctl --user --no-pager --full status ubo-app
```

Doom should appear directly under **Apps**.

## Important: unit name versus executable name

`ubo-app` is the **systemd unit name**. It is not the installed shell command.

Current Ubo installs the executable at:

```text
/opt/ubo/env/bin/ubo
```

For normal operation, use systemd:

```bash
systemctl --user restart ubo-app
systemctl --user status ubo-app
```

Do not run `ubo-app` in a terminal; that executable does not exist in current Ubo v2.

## Manual startup for debugging

Running Ubo manually is only for debugging. Stop the managed instance first to avoid duplicate core, GUI, and network processes:

```bash
systemctl --user stop ubo-app

cd "$HOME/work/ubo_doom"
source system/env/ubo_app.env.example

/opt/ubo/env/bin/ubo
```

Press `Ctrl+C` when finished, then restore normal operation:

```bash
systemctl --user start ubo-app
```

Verify the executable before manual startup:

```bash
ls -l /opt/ubo/env/bin/ubo
/opt/ubo/env/bin/ubo --help
```

The environment variables must reach the Ubo core process that loads external services.

## Environment variables

| Variable | Required | Example | Purpose |
|---|---:|---|---|
| `UBO_SERVICES_PATH` | Yes | `$HOME/ubo_services` | Colon-separated external-service paths |
| `UBO_DOOM_LIB` | Yes | `$HOME/doom/libubodoom.so` | Native Doom shared library |
| `UBO_DOOM_IWAD` | Yes | `$HOME/doom/doom2.wad` | Doom IWAD |
| `UBO_DOOM_CWD` | Recommended | `$HOME/doom` | Save/config working directory |
| `UBO_DOOM_CONFIG` | Recommended | `$HOME/doom/doomrc.cfg` | Doom configuration file |
| `UBO_DOOM_FPS` | No | `30` | Native game-loop rate |
| `UBO_DOOM_RENDER_FPS` | No | `15` | Maximum frame publication rate |
| `UBO_DOOM_ALSA_DEVICE` | No | `default` | ALSA playback device |

## Controls

Ubo owns BACK and HOME for navigation (BACK leaves Doom, HOME returns to the Ubo
home screen), so Doom is driven with the remaining five inputs. Turning is always
live so you can turn and shoot at once; the DOWN button is multiplexed and **L1
(MODE) cycles what it does**. The active mode is shown as a small color-coded tag
in the top-left of the Doom image.

See [`docs/CONTROLS.md`](docs/CONTROLS.md) for the full description.

### Gameplay

| Button | Doom action |
|---|---|
| UP | Move forward |
| L2 | Turn left |
| L3 | Turn right |
| L1 (MODE) | Cycle what DOWN does: **FIRE → USE → BACK → WEAPON → MENU** (wraps) |
| DOWN | Perform the current mode's action (see below) |

DOWN by mode:

| Mode | DOWN does |
|---|---|
| FIRE (default) | Fire |
| USE | Use — open doors, flip switches |
| BACK | Move backward |
| WEAPON | Switch to your next owned weapon |
| MENU | Open Doom's own (ESC) menu — New Game, Options, Quit |

While DOWN is set to FIRE / USE / WEAPON / MENU you cannot move backward — turn
180° and walk forward instead. The mode resets to FIRE whenever you leave a level.

**Reaching Doom's menu:** the Ubo **BACK** button leaves the Doom app entirely
(Ubo v2 owns BACK/HOME for navigation), so it can't open Doom's in-game menu. Use
the **MENU** mode instead: cycle L1 to MENU, press DOWN to open the menu, then
drive it with UP/DOWN (cursor) and L3 (select). Press **L1** to back out / close
the menu and resume — L1 doubles as "back" whenever a menu is open.

### Respawning after death

When you die, the view drops to the floor. After about a second, press **DOWN**
(FIRE — the default mode) or **USE** to respawn, which restarts the current level.
Because FIRE is the default, a plain DOWN press brings you back — no mode cycling
needed. The short delay is deliberate: it stops a fire button still held at the
moment of death from skipping the death view.

### Menus (title screen, Doom menu, intermission)

| Button | Doom action |
|---|---|
| UP / DOWN | Move the menu cursor |
| L3 | Title/demo: open the Doom menu; menu: select; intermission/finale: continue |

To start a game from the title screen: press **L3** to open the menu, **UP/DOWN**
to choose, then **L3** to select.

## Updating

```bash
cd "$HOME/work/ubo_doom"
git switch agent/ubo-v2-compatibility
git pull --ff-only
./native/scripts/build_libubodoom.sh
cp native/out/libubodoom.so "$HOME/doom/"
systemctl --user restart ubo-app
```

The Python service directory is symlinked, but native source changes still require rebuilding and copying `libubodoom.so`.

## Troubleshooting

### Doom tile does not appear

```bash
systemctl --user show ubo-app -p Environment --no-pager
readlink -f "$HOME/ubo_services/070-doom"
journalctl --user -u ubo-app -b -n 250 --no-pager
```

Confirm that `UBO_SERVICES_PATH` reaches the Ubo process and that `ubo_handle.py` and `setup.py` are complete and importable.

### Doom flashes white and returns to the menu

This means the render view opened but Doom initialization failed or the native library terminated the Ubo core process.

Check files and dependencies:

```bash
ls -l "$HOME/doom"
ldd "$HOME/doom/libubodoom.so"
```

Run the native wrapper in a standalone process to expose crashes or native exits:

```bash
cd "$HOME/work/ubo_doom/ubo_service/070-doom"

export UBO_DOOM_LIB="$HOME/doom/libubodoom.so"
export UBO_DOOM_IWAD="$HOME/doom/doom2.wad"
export UBO_DOOM_CWD="$HOME/doom"
export UBO_DOOM_CONFIG="$HOME/doom/doomrc.cfg"

PYTHONFAULTHANDLER=1 /opt/ubo/env/bin/python -u - <<'PY'
import os
from pathlib import Path
from native.doom_lib import DoomLib

lib = DoomLib(Path(os.environ["UBO_DOOM_LIB"]))
lib.init(os.environ["UBO_DOOM_IWAD"])
print("init succeeded")
print(lib.framebuffer_info())
lib.tick()
print("tick succeeded")
lib.shutdown()
PY

echo "exit status: $?"
```

### No audio

```bash
aplay -l
aplay -L
```

Set `UBO_DOOM_ALSA_DEVICE` to an available playback device and restart `ubo-app`.

### Development checks

```bash
python -m compileall -q ubo_service/070-doom
python -m pytest -q ubo_service/070-doom/tests
./native/scripts/build_libubodoom.sh
```
