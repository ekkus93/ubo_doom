# ubo_doom — Ubo v2 compatibility

[![CI and Release Artifacts](https://github.com/ekkus93/ubo_doom/actions/workflows/ci-release.yml/badge.svg)](https://github.com/ekkus93/ubo_doom/actions/workflows/ci-release.yml)

Doom ported to Ubo as an **external Ubo service**. The Ubo v2 integration uses Ubo's serializable action registry and RGB888 `frame_stream` renderer; it does not import Kivy widgets or write directly to the ST7789 display.

> **Branch status:** These instructions are for `agent/ubo-v2-compatibility`, not `master`. The README migration is committed separately from the implementation. Verify that the branch contains the Ubo v2 implementation commit before deploying it; otherwise the old pre-v2 service code will not run on current Ubo.

## Architecture

- `third_party/DOOM-master/linuxdoom-1.10/`
  - Builds an embeddable `libubodoom.so`.
  - Uses a headless framebuffer backend.
  - Uses ALSA instead of OSS `/dev/dsp`.
  - Includes the C API used by the Python service for initialization, ticking, framebuffer access, and keyboard input.

- `ubo_service/070-doom/`
  - Registers a Doom launcher in Ubo's Apps menu.
  - Opens a Ubo `frame_stream` render view.
  - Converts Doom's indexed framebuffer to letterboxed 240×240 RGB888 frames.
  - Publishes frames through Ubo's Redux/gRPC event path.
  - Maps Ubo keypad events to Doom key events.
  - Pauses the game loop when the Doom render view is not active.

- `native/scripts/`
  - Contains the native build and installation helpers.

## Requirements

- Current Ubo v2 installed and running.
- A Raspberry Pi/Ubo environment supported by the current Ubo release.
- `build-essential` and `libasound2-dev`.
- A legally obtained Doom IWAD, such as `doom1.wad`, `doom.wad`, or `doom2.wad`.
- The Ubo core process must receive `UBO_SERVICES_PATH` and the `UBO_DOOM_*` variables.

The repository does **not** contain an IWAD.

## Install on the Ubo device

Run the following commands on the Ubo itself.

### 1. Clone the Ubo v2 branch

For a new checkout:

```bash
git clone \
  --branch agent/ubo-v2-compatibility \
  --single-branch \
  https://github.com/ekkus93/ubo_doom.git \
  "$HOME/work/ubo_doom"

cd "$HOME/work/ubo_doom"
```

For an existing checkout:

```bash
cd "$HOME/work/ubo_doom"
git fetch origin agent/ubo-v2-compatibility
git switch agent/ubo-v2-compatibility || \
  git switch --track origin/agent/ubo-v2-compatibility

git pull --ff-only
```

Confirm the branch before continuing:

```bash
git branch --show-current
```

Expected output:

```text
agent/ubo-v2-compatibility
```

### 2. Install native build dependencies

```bash
sudo apt update
sudo apt install -y build-essential libasound2-dev
```

### 3. Build `libubodoom.so`

```bash
cd "$HOME/work/ubo_doom"
./native/scripts/build_libubodoom.sh
```

The build should produce:

```text
native/out/libubodoom.so
```

Basic validation:

```bash
test -f native/out/libubodoom.so
file native/out/libubodoom.so
ldd native/out/libubodoom.so
```

`ldd` should resolve `libasound.so` and should not report missing libraries.

### 4. Install the library and IWAD

```bash
mkdir -p "$HOME/doom"
cp native/out/libubodoom.so "$HOME/doom/"
cp /path/to/your/doom2.wad "$HOME/doom/"
```

Replace `doom2.wad` with the actual IWAD filename you own.

Optional but recommended:

```bash
mkdir -p "$HOME/doom"
touch "$HOME/doom/doomrc.cfg"
```

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
```

### 6. Configure the Ubo systemd service

Current Ubo normally runs as the user service `ubo-app.service`.

```bash
mkdir -p "$HOME/.config/systemd/user/ubo-app.service.d"
cp \
  "$HOME/work/ubo_doom/system/systemd/ubo_app_override.conf.example" \
  "$HOME/.config/systemd/user/ubo-app.service.d/override.conf"
```

Review the resulting file:

```bash
nano "$HOME/.config/systemd/user/ubo-app.service.d/override.conf"
```

The effective configuration should contain values equivalent to:

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

Change `UBO_DOOM_IWAD` when your filename is not `doom2.wad`.

`UBO_SERVICES_PATH` is colon-separated. If you already use other external-service directories, preserve them instead of overwriting the variable:

```ini
Environment=UBO_SERVICES_PATH=%h/ubo_services:%h/another_service_directory
```

Apply the configuration:

```bash
systemctl --user daemon-reload
systemctl --user restart ubo-app
```

### 7. Verify that the service loaded

Check the unit:

```bash
systemctl --user --no-pager --full status ubo-app
```

Inspect recent logs:

```bash
journalctl --user -u ubo-app -n 200 --no-pager
```

Doom-specific filtering:

```bash
journalctl --user -u ubo-app -b --no-pager \
  | grep -iE 'doom|070-doom|traceback|error|exception'
```

The Doom tile should appear under **Apps**. Selecting it should open a 240×240 frame-stream view and start or resume Doom.

Do not treat the presence of the external-service directory alone as proof that loading succeeded. A Python import or registration failure must be visible in the journal and corrected before continuing.

## Manual Ubo startup

For development without systemd:

```bash
cd "$HOME/work/ubo_doom"
source system/env/ubo_app.env.example
ubo-app
```

The environment must be applied to the **Ubo core process that loads services**, not only to the separate GUI client.

## Environment variables

| Variable | Required | Default/example | Purpose |
|---|---:|---|---|
| `UBO_SERVICES_PATH` | Yes | `$HOME/ubo_services` | Colon-separated external-service search path. |
| `UBO_DOOM_LIB` | Yes | `$HOME/doom/libubodoom.so` | Native Doom shared library. |
| `UBO_DOOM_IWAD` | Yes | `$HOME/doom/doom2.wad` | Legally obtained IWAD. |
| `UBO_DOOM_CWD` | Recommended | `$HOME/doom` | Stable working directory for saves and runtime files. |
| `UBO_DOOM_CONFIG` | Recommended | `$HOME/doom/doomrc.cfg` | Explicit Doom configuration file. |
| `UBO_DOOM_FPS` | No | `30` | Native game-loop target rate. |
| `UBO_DOOM_RENDER_FPS` | No | `15` | Maximum frame publication rate. Keep this at or below `UBO_DOOM_FPS`. |
| `UBO_DOOM_ALSA_DEVICE` | No | `default` | ALSA PCM device override. |

Useful ALSA device candidates include:

```text
default
sysdefault:CARD=wm8960soundcard
plughw:CARD=wm8960soundcard,DEV=0
plughw:0,0
hw:0,0
```

List available playback devices with:

```bash
aplay -L
aplay -l
```

## Controls on Ubo v2

Ubo owns BACK and HOME for navigation, so Doom uses UP, DOWN, and L1–L3 for gameplay.

### Normal mode

| Button | Doom action |
|---|---|
| UP | Move forward |
| DOWN | Move backward |
| L1 | Enter alternate mode |
| L2 | Turn left |
| L3 | Turn right; select in Doom menus/intermissions; open the Doom menu from the title/demo screen |
| BACK | Leave the Doom view and return to Ubo |
| HOME | Return to Ubo home |

### Alternate mode

| Button | Doom action |
|---|---|
| UP | Move forward |
| DOWN | Move backward |
| L1 | Return to normal mode |
| L2 | Use/open a door or switch |
| L3 | Fire |
| BACK | Leave the Doom view |
| HOME | Return to Ubo home |

Alternate mode is available only during active gameplay and resets when gameplay ends or a Doom menu opens. See `docs/CONTROLS.md` for the authoritative mapping.

## Updating an installed checkout

```bash
cd "$HOME/work/ubo_doom"
git switch agent/ubo-v2-compatibility
git pull --ff-only
./native/scripts/build_libubodoom.sh
cp native/out/libubodoom.so "$HOME/doom/"
systemctl --user restart ubo-app
```

Because the service directory is symlinked, Python service updates take effect after the Ubo restart. Rebuild and recopy the native library whenever native source changes.

## Troubleshooting

### Doom tile does not appear

```bash
systemctl --user show ubo-app -p Environment
readlink -f "$HOME/ubo_services/070-doom"
journalctl --user -u ubo-app -b --no-pager \
  | grep -iE 'doom|service|traceback|error|exception'
```

Confirm that `UBO_SERVICES_PATH` reaches the Ubo core service and that `ubo_handle.py` imports successfully.

### Tile appears, but Doom does not open

```bash
test -r "$HOME/doom/libubodoom.so"
test -r "$HOME/doom/doom2.wad"
ldd "$HOME/doom/libubodoom.so"
```

Also verify that `UBO_DOOM_IWAD` matches the actual filename exactly, including capitalization.

### Black screen or frozen frame

- Confirm the branch contains the Ubo v2 frame-stream implementation.
- Confirm frame conversion produces `240 × 240 × 3 = 172800` RGB888 bytes.
- Reduce `UBO_DOOM_RENDER_FPS` to `10` while diagnosing load or transport problems.
- Inspect the Ubo journal for frame-stream or service-thread exceptions.

### No audio

```bash
aplay -l
aplay -L
```

Try a specific `UBO_DOOM_ALSA_DEVICE`, update the systemd drop-in, then restart `ubo-app`.

### Native build fails on implicit-int errors

The Ubo shared-library target must compile the original Linux Doom source in GNU89 mode. Confirm the `UBO_CFLAGS` line in the Doom Makefile includes:

```make
-std=gnu89
```

## Development checks

From the repository root:

```bash
python -m compileall -q ubo_service/070-doom
python -m pytest -q ubo_service/070-doom/tests
./native/scripts/build_libubodoom.sh
```

The native build requires `libasound2-dev`.

## Additional documentation

- `docs/ARCHITECTURE.md`
- `docs/BUILD_DOOM_LIB.md`
- `docs/CONTROLS.md`
- `docs/SETUP_UBO_APP.md`
- `docs/TROUBLESHOOTING.md`

## CI/CD

- Pull requests run Python tests and the native Linux Doom shared-library build.
- Pushes to `master` run the same CI checks.
- Tags matching `v*` or `release-*` publish release artifacts.
- Workflow: `.github/workflows/ci-release.yml`.
